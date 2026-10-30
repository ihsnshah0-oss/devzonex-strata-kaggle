"""Live sector feed from the official DPS portal (dps.psx.com.pk/sector-summary).

Lifts the per-page session token (window.__ps._k), then pulls the
/sector-summary/sectorwise HTML fragment with it — the same call the PSX
portal makes. Returns sector aggregates (advance/decline/turnover/market cap)
plus every listed stock per sector (LDCP, OHLC, current, change, volume).
"""
import html as _html
import re
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://dps.psx.com.pk"


def _num(s):
    s = _html.unescape(s).replace(",", "").replace("%", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean(s):
    return _html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def fetch_sectorwise(timeout: int = 30):
    """Return (sectors, stocks) from the DPS sector-summary endpoint.

    sectors: {SECTOR_NAME_UPPER: {code, adv, dec, unch, turnover, mcap_bn}}
    stocks:  {SECTOR_NAME_UPPER: [{sym,name,ldcp,open,high,low,close,chg,pct,vol}]}
    """
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    page = sess.get(BASE + "/sector-summary", timeout=timeout).text
    m = re.search(r'"_k"\s*:\s*"([^"]+)"', page)
    if not m:
        raise RuntimeError("DPS token not found")
    tok = m.group(1)
    r = sess.get(BASE + "/sector-summary/sectorwise", timeout=timeout, headers={
        "X-Req-Id": tok,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/sector-summary",
        "Accept": "text/html, */*; q=0.01",
    })
    if r.status_code != 200 or "<table" not in r.text:
        raise RuntimeError("DPS sectorwise HTTP %s" % r.status_code)
    h = r.text

    # 1) sector summary table (first table)
    first = re.search(r"<table[^>]*>.*?</table>", h, re.S).group(0)
    sectors = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", first, re.S)[1:]:
        tds = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) >= 7 and tds[1]:
            sectors[tds[1].upper()] = {
                "code": tds[0],
                "adv": int(_num(tds[2]) or 0),
                "dec": int(_num(tds[3]) or 0),
                "unch": int(_num(tds[4]) or 0),
                "turnover": _num(tds[5]),          # PKR value traded
                "mcap_bn": _num(tds[6]),           # market cap, PKR billions
            }

    # 2) per-sector stock tables: <div ... data-code="0801"><h3>NAME</h3>...<table>
    stocks = {}
    for m in re.finditer(
            r'data-code="(\d+)">\s*<h3>(.*?)</h3>(.*?)(?=<div class="sectorSummary__companies__table"|<div class="modal|$)',
            h, re.S):
        code, name, body = m.group(1), _clean(m.group(2)).upper(), m.group(3)
        rows = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            tds = [_clean(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(tds) >= 10:
                rows.append({
                    "sym": tds[0], "name": tds[1],
                    "ldcp": _num(tds[2]), "open": _num(tds[3]),
                    "high": _num(tds[4]), "low": _num(tds[5]),
                    "close": _num(tds[6]), "chg": _num(tds[7]),
                    "pct": _num(tds[8]), "vol": _num(tds[9]),
                })
        if rows:
            stocks[name] = rows
    return sectors, stocks


if __name__ == "__main__":
    sectors, stocks = fetch_sectorwise()
    print("sectors:", len(sectors), "| stock tables:", len(stocks),
          "| total quotes:", sum(len(v) for v in stocks.values()))
    for k in list(sectors)[:3]:
        print(" ", k, sectors[k], "stocks:", len(stocks.get(k, [])))
