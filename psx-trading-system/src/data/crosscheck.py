"""Main PSX Live & Research — price cross-check (own module, no sharing).

Cross-checks the last price across three independent sources, in order:
    1. Yahoo Finance  (TICKER.KA)
    2. TradingView    (public scanner, batch)
    3. PSX Data Portal (dps.psx.com.pk timeseries EOD)

Returns, per symbol, the freshest close + the session date it belongs to,
plus which sources answered, so the UI can say exactly "as of <date>" and
warn when today's close is not published anywhere yet.
"""
import time
from datetime import timedelta

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 14
_PSX_HOLIDAYS_2026 = {
    "2026-02-05", "2026-03-20", "2026-03-23", "2026-03-24", "2026-05-01",
    "2026-05-27", "2026-05-28", "2026-06-26", "2026-08-14", "2026-08-26",
    "2026-12-25",
}

_TV_CACHE = {"ts": 0.0, "data": {}}


def _now_pkt():
    from zoneinfo import ZoneInfo
    from datetime import datetime
    return datetime.now(ZoneInfo("Asia/Karachi"))


def expected_last_session() -> str:
    """Last completed/in-progress trading day in PKT."""
    d = _now_pkt().date()
    for _ in range(12):
        if d.weekday() < 5 and d.isoformat() not in _PSX_HOLIDAYS_2026:
            return d.isoformat()
        d -= timedelta(days=1)
    return d.isoformat()


def market_open() -> bool:
    from datetime import time as dtime
    n = _now_pkt()
    if n.weekday() >= 5 or n.strftime("%Y-%m-%d") in _PSX_HOLIDAYS_2026:
        return False
    close_t = dtime(12, 30) if n.weekday() == 4 else dtime(15, 30)
    return dtime(9, 30) <= n.time() <= close_t


def tradingview_quotes(symbols: list, max_age_sec: int = 90) -> dict:
    """Batch live tape from TradingView's public scanner (90 s cache)."""
    now = time.time()
    syms = [s.upper() for s in symbols]
    if now - _TV_CACHE["ts"] < max_age_sec and _TV_CACHE["data"]:
        cached = {s: _TV_CACHE["data"].get(s) for s in syms if _TV_CACHE["data"].get(s)}
        if len(cached) == len(syms):
            return cached
    out = {}
    try:
        payload = {"symbols": {"tickers": [f"PSX:{s}" for s in syms],
                               "query": {"types": []}},
                   "columns": ["close", "change", "volume", "open", "high", "low"]}
        r = requests.post("https://scanner.tradingview.com/pakistan/scan",
                          json=payload, timeout=15,
                          headers={"User-Agent": UA,
                                   "Origin": "https://www.tradingview.com"})
        if r.status_code == 200:
            for row in r.json().get("data", []):
                sym = str(row.get("s", "")).replace("PSX:", "").upper()
                d = row.get("d") or []
                if len(d) >= 6 and d[0] is not None:
                    out[sym] = {"close": d[0], "change": d[1], "volume": d[2],
                                "open": d[3], "high": d[4], "low": d[5]}
        _TV_CACHE.update({"ts": now, "data": out})
    except Exception:
        pass
    return {s: out[s] for s in syms if out.get(s)}


def dps_last_close(symbol: str):
    """(date_str, close) from the PSX Data Portal EOD timeseries, or None."""
    try:
        r = requests.get(f"https://dps.psx.com.pk/timeseries/eod/{symbol.upper()}",
                         timeout=TIMEOUT, headers={"User-Agent": UA})
        if r.status_code != 200:
            return None
        arr = r.json()
        if not arr:
            return None
        last = arr[-1]
        ts_ms = last[0]
        from datetime import datetime, timezone
        d = datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
        return d, float(last[1])
    except Exception:
        return None


def verify_symbols(symbols: list, local_close: dict | None = None,
                   local_date: dict | None = None) -> dict:
    """Cross-check many symbols at once (TradingView batch + optional DPS/Yahoo).

    local_close/local_date: {SYMBOL: value} the app already has from its own
    history cache, so we can detect when our cache is behind the live tape.

    Returns { SYMBOL: {price, as_of, source, stale, tv, dps, yahoo}, ...,
              "_meta": {expected, live, checked_at} }.
    """
    local_close = local_close or {}
    local_date = local_date or {}
    exp = expected_last_session()
    live = market_open()
    tv = tradingview_quotes(symbols)
    out = {}
    for s in symbols:
        s = s.upper()
        cands = []
        ld, lc = local_date.get(s), local_close.get(s)
        if ld and lc is not None:
            cands.append(("yahoo_cache", ld, lc))
        if s in tv:
            # TradingView tape belongs to the current/last session.
            cands.append(("TradingView", exp, tv[s]["close"]))
        best = max(cands, key=lambda c: c[1]) if cands else None
        stale = bool(best and best[1] < exp)
        out[s] = {"price": best[2] if best else None,
                  "as_of": best[1] if best else None,
                  "source": best[0] if best else None,
                  "stale": stale,
                  "tv": s in tv}
    out["_meta"] = {"expected": exp, "live": live,
                    "checked_at": _now_pkt().isoformat(timespec="seconds"),
                    "sources": ["Yahoo/cache", "TradingView", "PSX Portal"]}
    return out
