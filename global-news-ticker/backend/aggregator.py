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

# Shared session with a browser-like User-Agent (bypasses basic bot blocks)
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (compatible; GlobalNewsMonitor/1.0) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
})

# ---------------------------------------------------------------------------
# Feed catalogue — edit URLs here if a feed moves
# ---------------------------------------------------------------------------
FEEDS = [
    # ── USA ─────────────────────────────────────────────────────────────────
    {
        "source": "New York Times",
        "region": "USA",
        "type": "Mainstream",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    },
    {
        "source": "AP News",          # Reuters entfernt – kostenlose Feeds eingestellt
        "region": "USA",
        "type": "Mainstream",
        "url": "https://feeds.apnews.com/rss/apf-topnews",
    },
    {
        "source": "Wall Street Journal",
        "region": "USA",
        "type": "Mainstream",
        "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    },
    {
        "source": "The Intercept",
        "region": "USA",
        "type": "Alternative",
        "url": "https://theintercept.com/feed/?rss",
    },
    {
        "source": "ProPublica",
        "region": "USA",
        "type": "Alternative",
        "url": "https://www.propublica.org/feeds/propublica/main",
    },
    # ── Südamerika ───────────────────────────────────────────────────────────
    {
        "source": "Clarín",
        "region": "Südamerika",
        "type": "Mainstream",
        "url": "https://www.clarin.com/rss/lo-ultimo/",
    },
    {
        "source": "Infobae",          # O Globo liefert 0 Artikel – Ersatz
        "region": "Südamerika",
        "type": "Mainstream",
        "url": "https://www.infobae.com/feeds/rss/",
    },
    {
        "source": "France24 ES",      # Telesur-Ersatz (stabiler Feed)
        "region": "Südamerika",
        "type": "Mainstream",
        "url": "https://www.france24.com/es/rss",
    },
    {
        "source": "El Faro",
        "region": "Südamerika",
        "type": "Alternative",
        "url": "https://elfaro.net/rss",
    },
    {
        "source": "InSight Crime",
        "region": "Südamerika",
        "type": "Alternative",
        "url": "https://insightcrime.org/feed/",
    },
    # ── Russland ─────────────────────────────────────────────────────────────
    {
        "source": "TASS",
        "region": "Russland",
        "type": "Mainstream",
        "url": "http://tass.com/rss/v2.xml",
    },
    {
        "source": "RIA Novosti",
        "region": "Russland",
        "type": "Mainstream",
        "url": "https://ria.ru/export/rss2/archive/index.xml",
    },
    {
        "source": "Kommersant",
        "region": "Russland",
        "type": "Mainstream",
        "url": "https://www.kommersant.ru/RSS/news.xml",
    },
    {
        "source": "Meduza",
        "region": "Russland",
        "type": "Alternative",
        "url": "https://meduza.io/rss/en/all",
    },
    {
        "source": "The Moscow Times",
        "region": "Russland",
        "type": "Alternative",
        "url": "https://www.themoscowtimes.com/rss/news",
    },
    # ── China ────────────────────────────────────────────────────────────────
    {
        "source": "Xinhua",
        "region": "China",
        "type": "Mainstream",
        "url": "http://www.xinhuanet.com/english/rss/worldrss.xml",
    },
    {
        "source": "Global Times",
        "region": "China",
        "type": "Mainstream",
        "url": "https://www.globaltimes.cn/rss/outbrain.xml",
    },
    {
        "source": "South China Morning Post",
        "region": "China",
        "type": "Mainstream",
        "url": "https://www.scmp.com/rss/91/feed",
    },
    {
        "source": "China Digital Times",
        "region": "China",
        "type": "Alternative",
        "url": "https://chinadigitaltimes.net/feed/",
    },
    {
        "source": "Sixth Tone",       # Caixin paywalled – Ersatz
        "region": "China",
        "type": "Alternative",
        "url": "https://www.sixthtone.com/rss",
    },
    # ── Indien ───────────────────────────────────────────────────────────────
    {
        "source": "Times of India",
        "region": "Indien",
        "type": "Mainstream",
        "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    },
    {
        "source": "The Hindu",
        "region": "Indien",
        "type": "Mainstream",
        "url": "https://www.thehindu.com/feeder/default.rss",
    },
    {
        "source": "The Wire",
        "region": "Indien",
        "type": "Alternative",
        "url": "https://thewire.in/rss",
    },
    {
        "source": "Scroll.in",
        "region": "Indien",
        "type": "Alternative",
        "url": "https://scroll.in/feed",
    },
    {
        "source": "The Print",        # The Caravan kaputt – stabiler Ersatz
        "region": "Indien",
        "type": "Alternative",
        "url": "https://theprint.in/feed/",
    },
]

_TAG_RE = re.compile(r"<[^>]+>")
TRANSLATE_BATCH = 40


def _translate_batch(texts: list[str]) -> list[str]:
    if not texts:
        return []
    try:
        results = GoogleTranslator(source="auto", target="de").translate_batch(texts)
        return [r if r else t for r, t in zip(results, texts)]
    except Exception as exc:
        log.warning("Translation batch failed: %s", exc)
        return texts


def translate_titles(articles: list[dict]) -> None:
    titles = [a["title"] for a in articles]
    translated: list[str] = []
    for i in range(0, len(titles), TRANSLATE_BATCH):
        batch = titles[i : i + TRANSLATE_BATCH]
        translated.extend(_translate_batch(batch))
        if i + TRANSLATE_BATCH < len(titles):
            time.sleep(0.3)
    for article, de_title in zip(articles, translated):
        article["title"] = de_title
    log.info("Translated %d titles to German", len(translated))


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    return " ".join(text.split())


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
    url = cfg["url"]
    try:
        # Fetch via requests for better encoding handling and HTTP error detection
        resp = _SESSION.get(url, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()

        # Pass raw bytes so feedparser detects encoding from XML declaration / BOM
        parsed = feedparser.parse(resp.content)

        # Accept bozo feeds if they still have entries (minor XML issues are common)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"Unparseable feed: {parsed.bozo_exception}")

        for entry in parsed.entries:
            pub_dt = _parse_date(entry)
            raw_summary = entry.get("summary") or entry.get("description") or ""
            articles.append(
                {
                    "title": (entry.get("title") or "").strip(),
                    "link": (entry.get("link") or "").strip(),
                    "source": cfg["source"],
                    "region": cfg["region"],
                    "type": cfg["type"],
                    "published": pub_dt.isoformat() if pub_dt else None,
                    "summary": _truncate(_strip_html(raw_summary)),
                    "_pub_dt": pub_dt,
                }
            )
        log.info("  OK  %-28s  %d articles", cfg["source"], len(articles))
    except Exception as exc:
        log.warning("  ERR %-28s  %s", cfg["source"], exc)
    return articles


def aggregate() -> None:
    log.info("=== Aggregation cycle started ===")
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    all_articles: list[dict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_feed, cfg): cfg for cfg in FEEDS}
        for fut in concurrent.futures.as_completed(futures):
            all_articles.extend(fut.result())

    # Deduplicate by link (keep first occurrence)
    seen: set[str] = set()
    unique: list[dict] = []
    for art in all_articles:
        link = art["link"]
        if link and link not in seen:
            seen.add(link)
            unique.append(art)

    # Split dated / undated — keep undated articles at the bottom
    dated = [a for a in unique if a["_pub_dt"] and a["_pub_dt"] >= cutoff]
    undated = [a for a in unique if not a["_pub_dt"]]
    dated.sort(key=lambda a: a["_pub_dt"], reverse=True)  # type: ignore[arg-type]
    combined = dated + undated

    # Translate all titles to German
    log.info("Translating %d titles …", len(combined))
    translate_titles(combined)

    # Strip internal helper field before serialising
    output = [{k: v for k, v in a.items() if k != "_pub_dt"} for a in combined]

    # Atomic write: write to .tmp then rename
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
