#!/usr/bin/env python3
"""Global News Monitor — RSS Aggregator Backend"""

import json
import logging
import re
import time
import concurrent.futures
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
import schedule
from deep_translator import GoogleTranslator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

OUTPUT_FILE = Path("/app/data/news.json")
MAX_AGE_HOURS = 48
FETCH_WORKERS = 10
FETCH_TIMEOUT = 15

_title_cache: dict[str, str] = {}

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
})

# ---------------------------------------------------------------------------
# Feed catalogue
# ---------------------------------------------------------------------------
FEEDS = [
    # ── USA ─────────────────────────────────────────────────────────────────
    {"source": "New York Times",    "region": "USA",        "type": "Mainstream",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"source": "BBC World",         "region": "USA",        "type": "Mainstream",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"source": "Wall Street Journal","region": "USA",       "type": "Mainstream",
     "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
    {"source": "The Intercept",     "region": "USA",        "type": "Alternative",
     "url": "https://theintercept.com/feed/?rss"},
    {"source": "ProPublica",        "region": "USA",        "type": "Alternative",
     "url": "https://www.propublica.org/feeds/propublica/main"},
    # ── Südamerika ───────────────────────────────────────────────────────────
    {"source": "Clarín",            "region": "Südamerika", "type": "Mainstream",
     "url": "https://www.clarin.com/rss/lo-ultimo/"},
    {"source": "MercoPress",        "region": "Südamerika", "type": "Mainstream",
     "url": "https://en.mercopress.com/rss"},
    {"source": "France24 ES",       "region": "Südamerika", "type": "Mainstream",
     "url": "https://www.france24.com/es/rss"},
    {"source": "InSight Crime",     "region": "Südamerika", "type": "Alternative",
     "url": "https://insightcrime.org/feed/"},
    {"source": "NACLA",             "region": "Südamerika", "type": "Alternative",
     "url": "https://nacla.org/taxonomy/term/2/feed"},
    # ── Russland ─────────────────────────────────────────────────────────────
    {"source": "TASS",              "region": "Russland",   "type": "Mainstream",
     "url": "http://tass.com/rss/v2.xml"},
    {"source": "RIA Novosti",       "region": "Russland",   "type": "Mainstream",
     "url": "https://ria.ru/export/rss2/archive/index.xml"},
    {"source": "Kommersant",        "region": "Russland",   "type": "Mainstream",
     "url": "https://www.kommersant.ru/RSS/news.xml"},
    {"source": "Meduza",            "region": "Russland",   "type": "Alternative",
     "url": "https://meduza.io/rss/en/all"},
    {"source": "The Moscow Times",  "region": "Russland",   "type": "Alternative",
     "url": "https://www.themoscowtimes.com/rss/news"},
    # ── China ────────────────────────────────────────────────────────────────
    {"source": "Xinhua",            "region": "China",      "type": "Mainstream",
     "url": "http://www.xinhuanet.com/english/rss/worldrss.xml"},
    {"source": "Global Times",      "region": "China",      "type": "Mainstream",
     "url": "https://www.globaltimes.cn/rss/outbrain.xml"},
    {"source": "South China Morning Post", "region": "China", "type": "Mainstream",
     "url": "https://www.scmp.com/rss/91/feed"},
    {"source": "China Digital Times","region": "China",     "type": "Alternative",
     "url": "https://chinadigitaltimes.net/feed/"},
    {"source": "Sixth Tone",        "region": "China",      "type": "Alternative",
     "url": "https://www.sixthtone.com/rss"},
    # ── Indien ───────────────────────────────────────────────────────────────
    {"source": "Times of India",    "region": "Indien",     "type": "Mainstream",
     "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"},
    {"source": "The Hindu",         "region": "Indien",     "type": "Mainstream",
     "url": "https://www.thehindu.com/feeder/default.rss"},
    {"source": "NDTV",              "region": "Indien",     "type": "Alternative",
     "url": "https://feeds.feedburner.com/ndtvnews-top-stories"},
    {"source": "Hindustan Times",   "region": "Indien",     "type": "Alternative",
     "url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"},
    {"source": "Economic Times",    "region": "Indien",     "type": "Alternative",
     "url": "https://economictimes.indiatimes.com/rssfeedsdefault.cms"},
]

# ---------------------------------------------------------------------------
# Urgency detection (on translated German titles)
# ---------------------------------------------------------------------------
_URGENT_WORDS = {
    "krieg", "kriegserklärung", "invasion", "einmarsch", "angriff", "anschlag",
    "attentat", "explosion", "bombenanschlag", "raketenangriff", "beschuss",
    "erdbeben", "tsunami", "katastrophe", "massenerschießung", "schießerei",
    "absturz", "kollaps", "zusammenbruch", "notstand", "evakuierung",
    "tote", "todesopfer", "getötet", "umgekommen", "massenvernichtung",
    "eskalation", "vergeltung", "drohnenangriff", "luftangriff",
    "terroranschlag", "terrorattacke", "geiselnahme", "entführung",
    "staatsstreich", "putsch", "zusammenstoß", "nuklear", "chemiewaffe",
    "breaking", "urgent", "alert",
}

_WORD_RE = re.compile(r"\b\w+\b")


def _is_urgent(title: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(title)}
    return bool(words & _URGENT_WORDS)


# ---------------------------------------------------------------------------
# Trending / cross-source coverage detection
# ---------------------------------------------------------------------------
_DE_STOPWORDS = {
    "aber", "alle", "allem", "allen", "aller", "alles", "also", "am", "an",
    "auch", "auf", "aus", "bei", "bin", "bis", "bitte", "da", "damit",
    "dann", "das", "dass", "dem", "den", "der", "des", "die", "dies",
    "durch", "ein", "eine", "einem", "einen", "einer", "eines", "er",
    "es", "für", "gegen", "hat", "haben", "hier", "ihm", "ihn", "ihr",
    "im", "in", "ins", "ist", "ja", "jetzt", "kann", "kein", "keine",
    "mit", "nach", "nicht", "noch", "nun", "nur", "oder", "sein", "seit",
    "sich", "sie", "sind", "so", "soll", "über", "und", "uns", "unter",
    "vom", "von", "vor", "war", "was", "wenn", "wird", "wie", "wird",
    "wir", "zu", "zum", "zur", "zwischen", "mehr", "beim", "einer",
    "worden", "wurden", "werden", "einer", "einem", "have", "that",
    "this", "with", "from", "will", "been", "have", "says", "said",
}


def _title_keywords(title: str) -> frozenset[str]:
    words = _WORD_RE.findall(title.lower())
    return frozenset(w for w in words if len(w) >= 4 and w not in _DE_STOPWORDS)


def _compute_coverage(articles: list[dict]) -> None:
    """Add coverage_count and trending fields to each article in-place."""
    kws = [_title_keywords(a["title"]) for a in articles]
    for i, art in enumerate(articles):
        if len(kws[i]) < 2:
            art["coverage_count"] = 1
            art["trending"] = False
            continue
        sources_covering = {art["source"]}
        for j, other in enumerate(articles):
            if i == j or other["source"] in sources_covering:
                continue
            if len(kws[i] & kws[j]) >= 2:
                sources_covering.add(other["source"])
        art["coverage_count"] = len(sources_covering)
        art["trending"] = len(sources_covering) >= 3


# ---------------------------------------------------------------------------
# Translation (with in-memory cache)
# ---------------------------------------------------------------------------
TRANSLATE_BATCH = 50


def _translate_batch(texts: list[str]) -> list[str]:
    if not texts:
        return []
    try:
        results = GoogleTranslator(source="auto", target="de").translate_batch(texts)
        return [r if r else t for r, t in zip(results, texts)]
    except Exception as exc:
        log.warning("Translation batch failed: %s", exc)
        return list(texts)


def translate_titles(articles: list[dict]) -> None:
    uncached = [(i, a["title"]) for i, a in enumerate(articles)
                if a["title"] and a["title"] not in _title_cache]
    if uncached:
        indices, titles = zip(*uncached)
        titles = list(titles)
        batches = [titles[i:i + TRANSLATE_BATCH] for i in range(0, len(titles), TRANSLATE_BATCH)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(_translate_batch, batches))
        translated: list[str] = []
        for r in results:
            translated.extend(r)
        for orig, de in zip(titles, translated):
            _title_cache[orig] = de
        log.info("Translated %d new titles (cache: %d)", len(uncached), len(_title_cache))
    else:
        log.info("All %d titles from cache", len(articles))
    for article in articles:
        article["title"] = _title_cache.get(article["title"], article["title"])


# ---------------------------------------------------------------------------
# Feed fetching
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return " ".join(_TAG_RE.sub("", text).split())


def _truncate(text: str, limit: int = 320) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(cfg: dict) -> list[dict]:
    articles = []
    try:
        resp = _SESSION.get(cfg["url"], timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "html" in ct and "xml" not in ct and "rss" not in ct:
            raise ValueError(f"Server returned HTML (Content-Type: {ct})")
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"Unparseable: {parsed.bozo_exception}")
        for entry in parsed.entries:
            pub_dt = _parse_date(entry)
            raw_summary = entry.get("summary") or entry.get("description") or ""
            articles.append({
                "title":    (entry.get("title") or "").strip(),
                "link":     (entry.get("link") or "").strip(),
                "source":   cfg["source"],
                "region":   cfg["region"],
                "type":     cfg["type"],
                "published": pub_dt.isoformat() if pub_dt else None,
                "summary":  _truncate(_strip_html(raw_summary)),
                "_pub_dt":  pub_dt,
            })
        log.info("  OK  %-28s  %d articles", cfg["source"], len(articles))
    except Exception as exc:
        log.warning("  ERR %-28s  %s", cfg["source"], exc)
    return articles


# ---------------------------------------------------------------------------
# Main aggregation cycle
# ---------------------------------------------------------------------------
def aggregate() -> None:
    log.info("=== Aggregation cycle started ===")
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    all_articles: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_feed, cfg): cfg for cfg in FEEDS}
        for fut in concurrent.futures.as_completed(futures):
            all_articles.extend(fut.result())

    seen: set[str] = set()
    unique: list[dict] = []
    for art in all_articles:
        if art["link"] and art["link"] not in seen:
            seen.add(art["link"])
            unique.append(art)

    dated   = [a for a in unique if a["_pub_dt"] and a["_pub_dt"] >= cutoff]
    undated = [a for a in unique if not a["_pub_dt"]]
    dated.sort(key=lambda a: a["_pub_dt"], reverse=True)  # type: ignore[arg-type]
    combined = dated + undated

    log.info("Translating %d titles …", len(combined))
    translate_titles(combined)

    # Post-translation enrichment
    for art in combined:
        art["urgent"] = _is_urgent(art["title"])
    _compute_coverage(combined)
    urgent_count   = sum(1 for a in combined if a["urgent"])
    trending_count = sum(1 for a in combined if a["trending"])
    log.info("Urgent: %d  Trending: %d", urgent_count, trending_count)

    output = [{k: v for k, v in a.items() if k != "_pub_dt"} for a in combined]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_FILE)
    log.info("=== Done: %d articles -> %s ===", len(output), OUTPUT_FILE)


def main() -> None:
    log.info("Global News Monitor — backend starting")
    aggregate()
    schedule.every(30).minutes.do(aggregate)
    while True:
        schedule.run_pending()
        time.sleep(15)


if __name__ == "__main__":
    main()
