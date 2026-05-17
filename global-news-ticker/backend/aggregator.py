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
import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

OUTPUT_FILE = Path("/app/data/news.json")
MAX_AGE_HOURS = 48
FETCH_WORKERS = 10

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
        "source": "Reuters",
        "region": "USA",
        "type": "Mainstream",
        "url": "http://feeds.reuters.com/reuters/worldnews",
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
        "source": "O Globo",
        "region": "Südamerika",
        "type": "Mainstream",
        "url": "https://oglobo.globo.com/rss.xml",
    },
    {
        "source": "Telesur",
        "region": "Südamerika",
        "type": "Mainstream",
        "url": "https://www.telesurenglish.net/rss/",
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
        "source": "Caixin Global",
        "region": "China",
        "type": "Alternative",
        "url": "https://www.caixinglobal.com/rss/rss.xml",
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
        "url": "https://www.thehindu.com/featureline/feed/rss/",
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
        "source": "The Caravan",
        "region": "Indien",
        "type": "Alternative",
        "url": "https://caravanmagazine.in/feed",
    },
]

_TAG_RE = re.compile(r"<[^>]+>")


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
    try:
        parsed = feedparser.parse(
            cfg["url"],
            request_headers={"User-Agent": "GlobalNewsMonitor/1.0"},
        )
        if parsed.bozo and not parsed.entries:
            raise ValueError(str(parsed.bozo_exception))

        for entry in parsed.entries:
            pub_dt = _parse_date(entry)
            raw_summary = (
                entry.get("summary") or entry.get("description") or ""
            )
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
