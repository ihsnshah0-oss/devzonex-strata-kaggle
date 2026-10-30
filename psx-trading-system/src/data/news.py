"""Free business-news ingestion via public RSS feeds.

Replaces paid wires (Bloomberg / FinHub / Reuters) with zero-cost,
keyless Pakistani business press RSS.
"""
import json
import time
from pathlib import Path

import requests

try:                      # optional: news is a live feature, not a core one
    import feedparser
except Exception:         # pragma: no cover - minimal installs
    feedparser = None

# Verified working (Sept 2026). Business Recorder & Profit publish no public
# RSS, so they are intentionally excluded; add them here if they add one.
FEEDS = {
    "Dawn Business": "https://www.dawn.com/feed/business",
    "Express Tribune": "https://tribune.com.pk/feed/business",
    "The News": "https://www.thenews.com.pk/rss",
    "Dunya News": "https://dunyanews.tv/en/feed",
    "ARY Business": "https://arynews.tv/category/business/feed/",
}

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120 Safari/537.36")}


def _fetch_feed(name: str, url: str, timeout: int = 12) -> list[dict]:
    if feedparser is None:      # no RSS parser installed — nothing to fetch
        return []
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        if r.status_code != 200 or not r.content:
            return []
        parsed = feedparser.parse(r.content)
        items = []
        for e in parsed.entries[:40]:
            items.append({
                "title": getattr(e, "title", ""),
                "link": getattr(e, "link", ""),
                "published": getattr(e, "published", ""),
                "summary": (getattr(e, "summary", "") or "")[:500],
                "source": name,
            })
        return items
    except Exception:
        return []


MARKET_KEYWORDS = (
    "psx", "kse", "stock", "share", "market", "index", "invest", "trade", "trading",
    "rupee", "dollar", "rate", "bank", "sbp", "imf", "budget", "tax", "gdp",
    "inflation", "profit", "dividend", "ipo", "bond", "sukuk", "t-bill", "forex",
    "remittance", "export", "import", "oil", "gas", "cement", "bank", "fertilizer",
    "pharma", "technology", "dividend", "buyback", "merger", "acquis",
)


def _market_rank(item: dict) -> int:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return sum(1 for k in MARKET_KEYWORDS if k in text)


def get_market_news(limit: int = 30, max_age_min: int = 30) -> list[dict]:
    p = CACHE / "news_market.json"
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_min * 60:
        try:
            return json.loads(p.read_text())[:limit]
        except Exception:
            pass
    items: list[dict] = []
    for name, url in FEEDS.items():
        items.extend(_fetch_feed(name, url))
    # finance-relevant stories first (some feeds mix general news in)
    items.sort(key=_market_rank, reverse=True)
    try:
        p.write_text(json.dumps(items[:120]))
    except Exception:
        pass
    return items[:limit]


def _keywords(symbol: str, company: str = "") -> set[str]:
    kws = {symbol.lower()}
    for tok in company.lower().replace("limited", " ").replace("pakistan", " ").split():
        if len(tok) > 3:
            kws.add(tok)
    return kws


def get_stock_news(symbol: str, company: str = "", limit: int = 15) -> list[dict]:
    """Market news filtered to items mentioning the company (plus sector)."""
    all_items = get_market_news(limit=120)
    kws = _keywords(symbol, company)
    hits = [i for i in all_items
            if any(k in (i["title"] + " " + i["summary"]).lower() for k in kws)]
    return hits[:limit]
