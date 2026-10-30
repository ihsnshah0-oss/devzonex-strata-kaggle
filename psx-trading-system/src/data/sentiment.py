"""Free, offline, finance-tuned sentiment scorer (no downloads, no API keys).

Replaces paid social-sentiment APIs in v1. Reddit public JSON is used
opportunistically (no key needed); everything degrades gracefully.
"""
import re
import time
from pathlib import Path

import requests

POS = set("""surge rally gain gains profit profits growth record upgrade upgrades
outperform overweight buy bullish breakout dividend bonus payout expansion approve
approved discovery recover recovery rebound strong beat beats positive jump jumps
soar all-time high outperformer reward rewards cut-rate rate-cut bullishness
bull-run outperforming milestone achievement achievement growth-story""".split())

NEG = set("""fall falls drop drops plunge crash loss losses decline declines downgrade
downgrades underperform underweight sell bearish breakdown default risk risky
fraud probe penalty fine scandal deficit circular-debt debt weak miss misses
negative slump slide slides crash crash-fears rate-hike hike hike-fears crisis
default recession fear fears selloff sell-off bankrupt bankruptcy suspension
halt investigation circular debt default delay delayed shortfall""".split())

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (PSX-Live-Research; personal/educational use)"}


def score_text(text: str) -> float:
    """Lexicon polarity in [-1, 1]."""
    if not text:
        return 0.0
    words = re.findall(r"[a-z\-]+", text.lower())
    if not words:
        return 0.0
    p = sum(1 for w in words if w in POS)
    n = sum(1 for w in words if w in NEG)
    if p == 0 and n == 0:
        return 0.0
    return round((p - n) / max(len(words) ** 0.5, 4) / 2, 4)


def label(score: float) -> str:
    if score >= 0.25:
        return "Positive"
    if score >= 0.07:
        return "Mildly positive"
    if score <= -0.25:
        return "Negative"
    if score <= -0.07:
        return "Mildly negative"
    return "Neutral"


def analyze_items(items: list[dict]) -> dict:
    scores = [score_text(f"{i.get('title', '')} {i.get('summary', '')}") for i in items]
    avg = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {"score": avg, "label": label(avg), "count": len(scores),
            "positive": sum(1 for s in scores if s > 0.07),
            "negative": sum(1 for s in scores if s < -0.07),
            "neutral": sum(1 for s in scores if -0.07 <= s <= 0.07)}


def reddit_mentions(symbol: str, limit: int = 15) -> list[dict]:
    """DISABLED — Reddit blocks unauthenticated data-center/home scraping
    (403/bot-detection), so this call only ever produced empty results and
    log noise. Sentiment now comes purely from the free RSS feeds, which
    work reliably. Kept as a stub (no network) so callers keep working."""
    return []
    # (dead code below preserved for reference only)
    p = CACHE / f"reddit_{symbol.upper()}.json"
    try:
        import json
        if p.exists() and (time.time() - p.stat().st_mtime) < 6 * 3600:
            return json.loads(p.read_text())
    except Exception:
        pass
    out: list[dict] = []
    try:
        for sub in ("FIREPakistan", "PakistanFinance", "stocks"):
            url = (f"https://www.reddit.com/r/{sub}/search.json?q={symbol}"
                   f"&restrict_sr=1&sort=new&limit={limit}")
            r = requests.get(url, headers=UA, timeout=10)
            if r.status_code != 200:
                continue
            for c in r.json().get("data", {}).get("children", []):
                d = c.get("data", {})
                out.append({"title": d.get("title", ""),
                            "summary": (d.get("selftext", "") or "")[:400],
                            "link": "https://www.reddit.com" + str(d.get("permalink", "")),
                            "source": f"r/{sub}", "score": d.get("score", 0)})
    except Exception:
        pass
    try:
        import json
        p.write_text(json.dumps(out[:30], default=str))
    except Exception:
        pass
    return out[:30]
