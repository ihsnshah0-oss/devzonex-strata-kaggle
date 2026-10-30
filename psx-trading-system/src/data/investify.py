"""Investify.pk ingestion — free, keyless.

Two feeds scraped from the public site (no API key needed):

1. /announcements — PSX company filings (board meetings, results, payouts,
   AGMs, management changes...) with smart summaries + original DPS PDF links.
2. /news — aggregated Pakistani business press (Dawn, Tribune, Recorder,
   Mettis, Profit) with links back to the ORIGINAL publisher articles.

Data is cached for a few minutes so repeated dashboard refreshes don't
hammer their site.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.investify.pk"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
      "Accept": "text/html"}

PUBLISHERS = {"dawn": "Dawn", "tribune": "Express Tribune", "recorder": "Business Recorder",
              "mettis": "Mettis Global", "profit": "Profit (Dawn)"}


def _get(url: str, timeout: int = 20) -> str | None:
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


def _parse_ann_date(txt: str) -> str:
    """'Sep 21, 2026, 3:26 PM' -> ISO string ('' if unknown)."""
    try:
        return datetime.strptime(txt.strip(), "%b %d, %Y, %I:%M %p").isoformat()
    except Exception:
        return ""


# ── announcements ────────────────────────────────────────────────────────
def fetch_announcements(force: bool = False, max_age_min: int = 10) -> list[dict]:
    p = CACHE / "investify_announcements.json"
    if not force and p.exists() and (time.time() - p.stat().st_mtime) < max_age_min * 60:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    html = _get(f"{BASE}/announcements")
    out: list[dict] = []
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select('h3 a[href^="/announcements/"]'):
                m = re.match(r"/announcements/([A-Z]+)/", a.get("href", ""))
                if not m:
                    continue
                card = a.find_parent("div", class_="cursor-pointer")
                if card is None:
                    card = a.find_parent("div")
                    card = card.find_parent("div") if card else None
                if card is None:
                    continue
                company = ""
                sp = card.find("span", class_=re.compile("truncate"))
                if sp:
                    company = sp.get_text(strip=True)
                badges = card.find_all("span", class_=re.compile(r"rounded-full.*text-\[11px\]"))
                category = badges[0].get_text(strip=True) if badges else ""
                sentiment = badges[1].get_text(strip=True) if len(badges) > 1 else ""
                date_txt = ""
                for spn in card.find_all("span", class_=re.compile("text-lightText")):
                    t = spn.get_text(strip=True)
                    if re.search(r"[A-Z][a-z]{2} \d", t):
                        date_txt = t
                        break
                pdf = ""
                pa = card.find("a", href=re.compile(r"dps\.psx\.com\.pk/download"))
                if pa:
                    pdf = pa["href"]
                out.append({
                    "symbol": m.group(1),
                    "company": company,
                    "category": category,
                    "sentiment": sentiment,
                    "title": a.get_text(strip=True),
                    "summary": (card.find("p").get_text(strip=True)
                                if card.find("p") else ""),
                    "link": BASE + a["href"],
                    "pdf": pdf,
                    "when": date_txt,
                    "when_iso": _parse_ann_date(date_txt),
                })
        except Exception:
            pass
    if out:
        try:
            p.write_text(json.dumps(out))
        except Exception:
            pass
        return out
    # site down → serve last good cache, whatever its age
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return []


# ── aggregated news ──────────────────────────────────────────────────────
_STORY_RE = re.compile(r'\{\\"l\\":\\".*?\\"t\\":\\".*?\\"\}')


def fetch_news(force: bool = False, max_age_min: int = 15) -> list[dict]:
    p = CACHE / "investify_news.json"
    if not force and p.exists() and (time.time() - p.stat().st_mtime) < max_age_min * 60:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    html = _get(f"{BASE}/news")
    out: list[dict] = []
    if html:
        seen = set()
        for raw in _STORY_RE.findall(html):
            try:
                j = json.loads(raw.replace('\\"', '"'))
            except Exception:
                continue
            sid = j.get("sid")
            if not j.get("t") or not j.get("l") or sid in seen:
                continue
            seen.add(sid)
            pub = PUBLISHERS.get((j.get("p") or "").lower(), (j.get("p") or "").upper())
            out.append({
                "title": j["t"],
                "link": j["l"],                      # ORIGINAL publisher article
                "published": j.get("d", ""),         # e.g. "21-09-2026 12:50"
                "summary": (j.get("ol") or "")[:500],
                "source": f"Investify · {pub}",
            })
    if out:
        try:
            p.write_text(json.dumps(out))
        except Exception:
            pass
        return out
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return []


def announcements_for(symbol: str, limit: int = 10) -> list[dict]:
    return [a for a in fetch_announcements() if a["symbol"] == symbol.upper()][:limit]
