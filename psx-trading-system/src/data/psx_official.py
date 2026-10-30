"""Official PSX website data feeds (free, keyless, public pages).

Two user-provided sources are wired in here (verified 2026-10-03):

1. https://www.psx.com.pk/market-summary/
   Server-rendered page refreshed every ~5 min. Gives the *official* market
   internals: advance/decline counts, total volume, traded value, trade
   count, session status and headline index levels.

2. https://financials.psx.com.pk/  (POST /annQtrStmts.php)
   PSX's official financial-reports portal:
     - name=get_comp_data  & smbCode=SYM  → full filing history for a
       company (annual + quarterly) with direct PDF download links
       (https://financials.psx.com.pk/lib/DownloadPDF.php?id=...).
     - name=get_yearly_data & year=YYYY   → market-wide calendar of the
       latest annual / quarterly report filings per company.

Everything is cached on disk with a TTL and falls back to a stale cache
when the sites are unreachable, so the dashboard never breaks on them.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

import requests

from .psx_client import _norm  # strip XD/XR/XB suffixes

BASE = Path(__file__).resolve().parents[2]
CACHE = BASE / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/120.0 Safari/537.36 (PSX-Live-Research; "
                     "personal/educational use)")}

MARKET_SUMMARY_URL = "https://www.psx.com.pk/market-summary/"
FINANCIALS_API = "https://financials.psx.com.pk/annQtrStmts.php"
PDF_BASE = "https://financials.psx.com.pk/lib/DownloadPDF.php?id="

_IDX_PRETTY = {"KSE100": "KSE-100", "KSE30": "KSE-30", "KMI30": "KMI-30",
               "ALLSHR": "KSE All-Share"}


# ── tiny cache helpers ──────────────────────────────────────────────
def _cache_get(name: str, ttl_sec: int, allow_stale: bool = False):
    p = CACHE / name
    if p.exists():
        try:
            fresh = (time.time() - p.stat().st_mtime) < ttl_sec
            if fresh or allow_stale:
                return json.loads(p.read_text())
        except Exception:
            pass
    return None


def _cache_put(name: str, obj) -> None:
    try:
        (CACHE / name).write_text(json.dumps(obj, default=str))
    except Exception:
        pass


# ── 1. official market overview (psx.com.pk/market-summary) ─────────
def get_market_overview(max_age_min: int = 5) -> dict:
    """Official market internals: breadth, turnover, status, indices.

    Returns {} only when there is no cache at all and the site is down.
    """
    cached = _cache_get("official_overview.json", max_age_min * 60)
    if cached:
        return cached
    try:
        html = requests.get(MARKET_SUMMARY_URL, headers=UA, timeout=20).text
        txt = re.sub(r"<[^>]+>", "|", html)
        txt = re.sub(r"\|+", "|", txt)

        def num(pat) -> float | None:
            m = re.search(pat, txt)
            return float(m.group(1).replace(",", "")) if m else None

        ov: dict = {"source": "psx.com.pk/market-summary"}
        m = re.search(r"\|(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)\|", txt)
        ov["as_of"] = m.group(1) if m else None
        m = re.search(r"Status:\|?\s*([A-Za-z\- ]+)\|", txt)
        ov["status"] = m.group(1).strip() if m else None
        ov["volume"] = num(r"Volume:\|?\s*([\d,]+)")
        ov["value"] = num(r"Value:\|?\s*([\d,]+)")
        ov["trades"] = num(r"Trades:\|?\s*([\d,]+)")
        breadth = {"advanced": num(r"Advanced:\|?\s*([\d,]+)"),
                   "declined": num(r"Declined:\|?\s*([\d,]+)"),
                   "unchanged": num(r"Unchanged:\|?\s*([\d,]+)"),
                   "total": num(r"Total:\|?\s*([\d,]+)")}
        ov["breadth"] = {k: (int(v) if v is not None else None)
                         for k, v in breadth.items()}

        # indices block: NAME | value | change | (pct%). The raw table has
        # empty cells (arrows/images) between fields, so collapse the
        # whitespace-only cells first; use the LAST "Indices" marker because
        # the nav menu also contains that word.
        txt2 = txt
        for _ in range(4):
            txt2 = re.sub(r"\|\s*\|", "|", txt2)
        indices: list[dict] = []
        i = txt2.rfind("Indices|")
        seg = txt2[i:i + 3000] if i >= 0 else ""
        for name, val, chg, pct in re.findall(
                r"\|([A-Z][A-Z0-9]+)\|+([\d,]+(?:\.\d+)?)\|+"
                r"([+-]?[\d,]+(?:\.\d+)?)\|+\(([+-]?[\d.]+)%\)", seg):
            try:
                indices.append({
                    "name": _IDX_PRETTY.get(name, name),
                    "value": float(val.replace(",", "")),
                    "change": float(chg.replace(",", "")),
                    "pct": float(pct)})
            except ValueError:
                continue
        ov["indices"] = indices[:8]
        _cache_put("official_overview.json", ov)
        return ov
    except Exception:
        stale = _cache_get("official_overview.json", 10**9, allow_stale=True)
        return stale or {}


# ── 2. per-company filings history (financials.psx.com.pk) ──────────
def get_company_filings(symbol: str, limit: int = 40,
                        max_age_hours: int = 24) -> list[dict]:
    """Official filing history (annual + quarterly) with PDF links."""
    sym = _norm(str(symbol).upper().strip())
    cached = _cache_get(f"filings_{sym}.json", max_age_hours * 3600)
    if cached:
        return cached[:limit]
    try:
        r = requests.post(FINANCIALS_API,
                          data={"name": "get_comp_data", "smbCode": sym},
                          headers=UA, timeout=25)
        rows = r.json()
    except Exception:
        stale = _cache_get(f"filings_{sym}.json", 10**9, allow_stale=True)
        return (stale or [])[:limit]

    out: list[dict] = []
    for row in rows or []:
        try:
            html_cell = row.get("Reports", "")
            m = re.search(r"DownloadPDF\.php\?id=([^\"'&]+)", html_cell)
            t = re.search(r">([^<]+)</a>", html_cell)
            out.append({
                "type": (t.group(1).strip() if t else "Report"),
                "period_ended": row.get("period_ended") or None,
                "posted": row.get("posting_date") or None,
                "pdf_url": (PDF_BASE + m.group(1)) if m else None,
            })
        except Exception:
            continue
    # newest first (posting date, then period)
    out.sort(key=lambda f: (f.get("posted") or "", f.get("period_ended") or ""),
             reverse=True)
    _cache_put(f"filings_{sym}.json", out)
    return out[:limit]


# ── 3. market-wide recent-filings calendar (financials.psx.com.pk) ──
def get_recent_filings(limit: int = 30, max_age_hours: int = 6) -> list[dict]:
    """Latest official annual/quarterly report filings across PSX, newest first."""
    year = date.today().year
    cached = _cache_get(f"filings_calendar_{year}.json", max_age_hours * 3600)
    rows = cached
    if rows is None:
        try:
            r = requests.post(FINANCIALS_API,
                              data={"name": "get_yearly_data", "year": year},
                              headers=UA, timeout=30)
            raw = r.json()
            rows = []
            for x in raw or []:
                a, q = (x.get("annual_reports") or "").strip(), \
                       (x.get("quarter_reports") or "").strip()
                last = max([d for d in (a, q) if d], default=None)
                if not last:
                    continue
                rows.append({"symbol": x.get("Symbol"),
                             "company": x.get("Company_name"),
                             "last_annual": a or None,
                             "last_quarter": q or None,
                             "last_filed": last})
            rows.sort(key=lambda r: r["last_filed"], reverse=True)
            _cache_put(f"filings_calendar_{year}.json", rows)
        except Exception:
            rows = []
    return rows[:limit]
