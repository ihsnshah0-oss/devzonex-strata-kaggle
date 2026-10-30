"""PSX Official Desk — wires the exchange's public pages into the app.

Each entry in LINKS is one official source the user asked to review, plus the
app section it feeds. Where a page actually serves parseable data
(eligible-scrips, monthly-reports archives, sector-summary) we scrape it; the
rest are surfaced as one-click official links next to the section they back.
DPS pages need the per-session token lifted from window.__ps._k (same trick as
dps_sectors.py).
"""
import json
import re
import time
import html as _html
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DPS = "https://dps.psx.com.pk"
CACHE = Path(__file__).resolve().parents[2] / "cache"
CACHE.mkdir(exist_ok=True)

LINKS = [
    {"url": DPS + "/sector-summary", "name": "Sector Summary",
     "wired": "Sectors tab — official sector tape (adv/dec, turnover, mcap)", "live": True},
    {"url": DPS + "/historical", "name": "Historical EOD Data",
     "wired": "Charts / backtest / indicators — daily OHLCV history", "live": True},
    {"url": DPS + "/announcements/companies", "name": "Company Announcements",
     "wired": "Dashboard → News & Announcements feed + 🔔 bell", "live": True},
    {"url": DPS + "/announcements/psx", "name": "PSX Announcements",
     "wired": "Dashboard → News & Announcements feed (exchange notices)", "live": True},
    {"url": DPS + "/eligible-scrips", "name": "Eligible Scrips",
     "wired": "Reports → PSX Desk (T+0/margin eligible symbols)", "live": True},
    {"url": DPS + "/monthly-reports", "name": "Monthly Reports",
     "wired": "Reports → PSX Desk (archive downloads)", "live": True},
    {"url": DPS + "/analysis-reports", "name": "Analysis Reports",
     "wired": "Reports → PSX Desk link (research publications)", "live": False},
    {"url": DPS + "/progress-report", "name": "Progress Report",
     "wired": "Reports → PSX Desk link (market development stats)", "live": False},
    {"url": DPS + "/graphical-view", "name": "Graphical View",
     "wired": "Heatmap / Sectors companion link (official charts)", "live": False},
    {"url": DPS + "/indices-div-discount", "name": "Indices (Div. Discounted)",
     "wired": "Dashboard indices companion link", "live": False},
    {"url": DPS + "/downloads", "name": "Downloads",
     "wired": "Reports → PSX Desk link (daily/other downloads)", "live": False},
    {"url": "https://www.psx.com.pk/market-summary/", "name": "Market Summary",
     "wired": "Dashboard companion link (official daily summary)", "live": False},
    {"url": "https://financials.psx.com.pk/", "name": "Company Financials",
     "wired": "Stocks tab → 📑 Financials button (official statements PDF)", "live": False},
]


def _session():
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    page = sess.get(DPS + "/eligible-scrips", timeout=20).text
    m = re.search(r'"_k"\s*:\s*"([^"]+)"', page)
    if not m:
        raise RuntimeError("no token")
    sess.headers.update({"X-Req-Id": m.group(1),
                         "X-Requested-With": "XMLHttpRequest",
                         "Referer": DPS + "/"})
    return sess


def _cached(key, fn, ttl):
    p = CACHE / f"desk_{key}.json"
    try:
        if p.exists() and time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text())
    except Exception:
        pass
    out = fn()
    try:
        p.write_text(json.dumps(out, default=str))
    except Exception:
        pass
    return out


def _eligible(sess):
    h = sess.get(DPS + "/eligible-scrips", timeout=25).text
    groups, cur = [], "Eligible scrips"
    for mhead in re.finditer(r"<h\d[^>]*>(.*?)</h\d>|<table.*?</table>", h, re.S):
        seg = mhead.group(0)
        if seg.startswith("<h"):
            cur = _html.unescape(re.sub(r"<[^>]+>", "", seg)).strip() or cur
            continue
        syms = re.findall(r'href="/company/([A-Z0-9.\-]+)"', seg) or \
            re.findall(r'<td[^>]*>\s*([A-Z0-9][A-Z0-9.\-]{1,12})\s*</td>', seg)
        if syms:
            groups.append({"group": cur, "count": len(set(syms)),
                           "symbols": sorted(set(syms))[:400]})
    return groups


def _monthly(sess):
    h = sess.get(DPS + "/monthly-reports/archives", timeout=25).text
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", h, re.S):
        m = re.search(r"<td><b>(.*?)</b></td>", row, re.S)
        if not m:
            continue
        links = [{"label": _html.unescape(a[1]).strip(), "href": DPS + a[0]}
                 for a in re.findall(r'<a href="([^"]+)">([^<]*)</a>', row)]
        out.append({"month": _html.unescape(m.group(1)).strip(), "links": links})
    return out[:8]   # page is newest-first


def _month_indices(sess):
    import datetime as _dt
    now = _dt.date.today()
    for delta in range(0, 4):
        y, m = now.year, now.month - delta
        while m < 1:
            m += 12; y -= 1
        tag = f"{y}-{m:02d}"
        try:
            h = sess.get(f"{DPS}/monthly-reports/indices/{tag}", timeout=20).text
        except Exception:
            continue
        rows = re.findall(
            r"<td>(\d{4}-\d{2}-\d{2})</td>\s*<td class=\"right\">([\d,.]+)</td>\s*"
            r"<td class=\"right[^\"]*\">(?:<i[^>]*></i>)?\s*(-?[\d,.]+)</td>", h)
        if rows:
            d, kse, chg = rows[-1]
            return {"month": tag, "date": d,
                    "kse100": float(kse.replace(",", "")),
                    "change": float(chg.replace(",", ""))}
    return {}


def fetch_desk(ttl_hours: int = 6) -> dict:
    def _all():
        try:
            sess = _session()
        except Exception:
            return {"eligible": [], "monthly": []}
        try:
            elig = _eligible(sess)
        except Exception:
            elig = []
        try:
            mon = _monthly(sess)
        except Exception:
            mon = []
        try:
            idx = _month_indices(sess)
        except Exception:
            idx = {}
        return {"eligible": elig, "monthly": mon, "indices": idx}
    data = _cached("main", _all, ttl_hours * 3600)
    return {"links": LINKS, "eligible": data.get("eligible", []),
            "monthly": data.get("monthly", []),
            "indices": data.get("indices", {}),
            "fetched_at": time.strftime("%Y-%m-%d %H:%M PKT")}


if __name__ == "__main__":
    d = fetch_desk(ttl_hours=0)
    print("eligible groups:", [(g["group"], g["count"]) for g in d["eligible"]][:5])
    print("monthly:", [m["month"] for m in d["monthly"]][:5])
