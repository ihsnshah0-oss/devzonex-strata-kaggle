"""Data layer: PSX market data with an offline-first ladder.

Order of preference for every read:

    1. fresh disk cache          (fast, and what the UI wants 99% of the time)
    2. portal mirror SQLite      (data/portal.db — real dps.psx.com.pk data,
                                  up to ten years of bars, no network needed)
    3. live network              (psxdata → DPS portal, Yahoo .KA as last resort)
    4. stale disk cache          (better a two-day-old price than a blank tab)

`network_up()` probes dps.psx.com.pk once and remembers the answer for
`NET_TTL` seconds, so an offline laptop pays a single failed probe instead of
a 30-second timeout on every request.

Everything cached here is also written back to `data/cache/`, so two runs in a
row never repeat the same network call.
"""
import json
import re
import socket
import ssl
import time
from datetime import date, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from . import mirror

try:
    import psxdata
    _HAS_PSXDATA = True
except Exception:
    _HAS_PSXDATA = False

BASE = Path(__file__).resolve().parents[2]
CACHE = BASE / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (PSX-Live-Research; personal/educational use)"}
# Pakistan Standard Time is a fixed UTC+5 with no daylight saving, so a plain
# fixed offset beats pulling in a tz database.
PKT = timezone(timedelta(hours=5), name="PKT")

# ── network gate ────────────────────────────────────────────────────
NET_TTL = 600.0          # remember "up"/"down" for 10 minutes
PROBE_TIMEOUT = 4.0
_NET = {"ok": None, "checked": 0.0, "error": None}


def network_up(force: bool = False) -> bool:
    """True when dps.psx.com.pk answers a TLS handshake.

    One probe per NET_TTL. Set PSX_OFFLINE=1 in the environment to skip the
    network entirely (useful on a plane, or when you only have the mirror).
    """
    import os
    if os.environ.get("PSX_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        return False
    now = time.time()
    if not force and _NET["ok"] is not None and (now - _NET["checked"]) < NET_TTL:
        return bool(_NET["ok"])
    ok = False
    err = None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection(("dps.psx.com.pk", 443), timeout=PROBE_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname="dps.psx.com.pk"):
                ok = True
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    _NET.update(ok=ok, checked=now, error=err)
    return ok


def network_state() -> dict:
    """For the UI: is the portal reachable, when did we last check."""
    checked = _NET["checked"]
    return {
        "up": bool(_NET["ok"]),
        "checked_ago_sec": None if not checked else round(time.time() - checked, 1),
        "error": _NET["error"],
        "ttl_sec": NET_TTL,
    }


def _mirror_fresh_enough(max_age_days: float = 2.0) -> bool:
    """True when the mirror is recent enough to trust over live data."""
    if not mirror.available():
        return False
    age = mirror.age_days()
    return age is not None and age <= max_age_days


# ── tiny cache helpers ──────────────────────────────────────────────
def _json_get(name: str, ttl_sec: int):
    p = CACHE / name
    if p.exists() and (time.time() - p.stat().st_mtime) < ttl_sec:
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _json_get_any(name: str):
    """Stale-tolerant read: ignores the timestamp entirely."""
    try:
        p = CACHE / name
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


def _json_put(name: str, obj) -> None:
    try:
        (CACHE / name).write_text(json.dumps(obj, default=str))
    except Exception:
        pass


def resolve_symbol(symbol: str) -> str:
    """Map a base symbol to the variant actually trading today.

    PSX renames stocks around entitlements (BOP → BOPXD ex-dividend, etc.).
    This checks the live snapshot so 'BOP' keeps working and flips back
    automatically when the plain symbol resumes.
    """
    sym = str(symbol).upper().strip()
    try:
        names = set(get_market_snapshot()["symbol"].astype(str).str.upper())
        if sym in names:
            return sym
        for cand in (sym + "XD", sym + "XR", sym + "XB", _norm(sym)):
            if cand in names:
                return cand
    except Exception:
        pass
    return sym


# ── live quotes ─────────────────────────────────────────────────────
def get_quote(symbol: str) -> dict:
    """Latest quote for one symbol: cache → mirror → live (15-min cache)."""
    symbol = resolve_symbol(symbol.upper().strip())
    cached = _json_get(f"quote_{symbol}.json", 15 * 60)
    if cached:
        return cached

    # The mirror is refreshed once a day by the portal ingest; intraday prices
    # only exist live, so prefer live when it is both reachable and newer.
    live_first = network_up() and not _mirror_fresh_enough(0.5)
    if live_first and _HAS_PSXDATA:
        try:
            row = psxdata.quote(symbol)
            d = row.iloc[0].to_dict() if hasattr(row, "iloc") else dict(row)
            out = {k: (None if pd.isna(v) else v) for k, v in d.items()}
            out["symbol"] = symbol
            out["source"] = "DPS live quote"
            _json_put(f"quote_{symbol}.json", out)
            return out
        except Exception:
            pass

    q = mirror.quote(_norm(symbol))
    if q:
        _json_put(f"quote_{symbol}.json", q)
        return q

    if _HAS_PSXDATA and network_up():
        row = psxdata.quote(symbol)
        d = row.iloc[0].to_dict() if hasattr(row, "iloc") else dict(row)
        out = {k: (None if pd.isna(v) else v) for k, v in d.items()}
        out["symbol"] = symbol
        _json_put(f"quote_{symbol}.json", out)
        return out

    stale = _json_get_any(f"quote_{symbol}.json")
    if stale:
        return stale
    raise RuntimeError(f"No quote for {symbol} (mirror and portal both empty)")


# ── EOD history (backtests, charts, indicators) ─────────────────────
def _read_fresh_csv(p: Path, max_age_hours: int, min_rows: int = 50):
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_hours * 3600:
        try:
            df = pd.read_csv(p, parse_dates=["date"])
            if len(df) >= min_rows:
                return df
        except Exception:
            pass
    return None


def _last_trading_date_pkt():
    """Latest date for which an EOD bar should exist by now (PKT logic).
    Sessions close 15:30 Mon-Thu and 16:30 Friday. A short buffer after the
    close gives DPS time to publish the day's bar before we expect it."""
    from datetime import datetime
    now = datetime.now(PKT)
    d = now.date()
    mins = now.hour * 60 + now.minute
    close_min = 16 * 60 + 45 if now.weekday() == 4 else 15 * 60 + 45
    if now.weekday() < 5 and mins >= close_min:
        return d
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def get_history(symbol: str, start: str | None = None,
               end: str | None = None, max_age_hours: int = 12,
               lite: bool = False) -> pd.DataFrame:
    """Ascending OHLCV dataframe.

    Ladder: fresh cache → portal mirror → live (psxdata → Yahoo) → stale cache.
    `lite=True` keeps ~520 days (enough for SMA200 / 52-week) and is what the
    screener uses so its first run stays fast.
    """
    import contextlib
    import io
    symbol = resolve_symbol(symbol.upper().strip())
    base = _norm(symbol)
    end = end or date.today().isoformat()
    if start is None:
        start = (date.today() - timedelta(days=520)).isoformat() if lite else "2019-01-01"
    p = CACHE / f"eod_{symbol}{'_lite' if lite else ''}.csv"
    plain = CACHE / f"eod_{symbol}.csv"
    df = _read_fresh_csv(p, max_age_hours)
    if df is not None and not lite:
        # Self-heal: if the cache was written before the session ended it may be
        # missing the latest day. After close, force a refetch once the cache is
        # >15 min old (throttled so holidays don't hammer the source).
        try:
            last = pd.to_datetime(df["date"].max()).date()
            if last < _last_trading_date_pkt() and (time.time() - p.stat().st_mtime) > 900:
                df = None
        except Exception:
            pass
    if df is not None:
        return df

    # ── 2) portal mirror: ten years of verified bars, no network needed ──
    def _from_mirror() -> pd.DataFrame | None:
        try:
            if not mirror.has_history(base):
                return None
            m = mirror.history(base, start=None if not lite else start, end=None)
            if m is None or m.empty:
                return None
            if lite:
                m = m.tail(520).reset_index(drop=True)
            return m
        except Exception:
            return None

    live_first = network_up() and not _mirror_fresh_enough(2.0)
    if live_first:
        df = _live_history(symbol, base, start, end, contextlib, io)
        if df is None or df.empty:
            df = _from_mirror()
    else:
        df = _from_mirror()
        if df is None or df.empty:
            df = _live_history(symbol, base, start, end, contextlib, io)

    if df is None or df.empty:
        # 4) last resort: any cache, however old
        df = _read_fresh_csv(plain, 10 ** 7)
        if df is None or df.empty:
            df = _read_fresh_csv(p, 10 ** 7)
    if df is None or df.empty:
        raise ValueError(f"No history for {symbol}")

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    try:
        df.to_csv(p, index=False)
    except Exception:
        pass
    return df


def _live_history(symbol: str, base: str, start: str, end: str,
                  contextlib, io) -> pd.DataFrame | None:
    """psxdata first, Yahoo `.KA` second. Returns None when both fail."""
    if _HAS_PSXDATA and network_up():
        # History sometimes lives under a different variant than the live quote
        # (e.g. quotes=BOPXD but history=BOP). Try each until one returns data.
        for cand in dict.fromkeys([symbol, base, base + "XD", base + "XR", base + "XB"]):
            try:
                with contextlib.redirect_stdout(io.StringIO()):  # silence chatter
                    d = psxdata.stocks(cand, start=start, end=end)
                if d is not None and len(d) >= 30:
                    return d
            except Exception:
                continue
    if network_up():
        try:
            import yfinance as _yf
            from datetime import timedelta as _td
            yend = (pd.to_datetime(end) + _td(days=2)).date().isoformat()
            for cand in dict.fromkeys([base, symbol]):
                h = _yf.Ticker(f"{cand}.KA").history(start=start, end=yend,
                                                     interval="1d",
                                                     auto_adjust=False)
                if h is not None and len(h) >= 30:
                    h = h.reset_index()
                    cols = {"Date": "date", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"}
                    h = h.rename(columns=cols)[list(cols.values())]
                    h["date"] = pd.to_datetime(h["date"]).dt.tz_localize(None)
                    h["volume"] = pd.to_numeric(h["volume"], errors="coerce").fillna(0)
                    return h
        except Exception:
            pass
    return None


# ── whole-market snapshot (screener fuel) ───────────────────────────
def get_market_snapshot(max_age_min: int = 15) -> pd.DataFrame:
    """One row per listed instrument: price, change, mcap, P/E, yield…

    Never raises when the mirror or a cache exists — the screener, pulse,
    universe and heatmap all depend on this being available offline.
    """
    p = CACHE / "screener.csv"
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_min * 60:
        try:
            df = pd.read_csv(p)
            if len(df):
                return df
        except Exception:
            pass

    live_first = network_up() and not _mirror_fresh_enough(0.5)
    if live_first and _HAS_PSXDATA:
        try:
            df = psxdata.screener()
            if df is not None and len(df):
                df["source"] = "DPS live screener"
                _safe_to_csv(df, p)
                return df
        except Exception:
            pass

    m = mirror.snapshot()
    if m is not None and len(m):
        _safe_to_csv(m, p)
        return m

    if _HAS_PSXDATA and network_up():
        try:
            df = psxdata.screener()
            if df is not None and len(df):
                _safe_to_csv(df, p)
                return df
        except Exception:
            pass

    try:  # 4) stale cache, however old
        if p.exists():
            df = pd.read_csv(p)
            if len(df):
                return df
    except Exception:
        pass
    raise RuntimeError("No market snapshot available (no mirror, cache or network)")


def _safe_to_csv(df: pd.DataFrame, p: Path) -> None:
    try:
        df.to_csv(p, index=False)
    except Exception:
        pass


def _norm(sym: str) -> str:
    """Strip entitlement suffixes (XD/XR/XB) for stable matching."""
    s = str(sym).upper().strip()
    for suf in ("XD", "XR", "XB"):
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


def get_kse100(max_age_hours: int = 24) -> list[str]:
    cached = _json_get("kse100.json", max_age_hours * 3600)
    if cached:
        return cached
    syms: list[str] = []
    if mirror.available():
        syms = sorted({_norm(s) for s in mirror.members("KSE100")})
    if not syms and network_up() and _HAS_PSXDATA:
        try:
            idx = psxdata.indices("KSE100")
            if hasattr(idx, "columns") and "symbol" in idx.columns:
                raw = idx["symbol"].astype(str).tolist()
            else:
                raw = list(idx)
            syms = sorted({_norm(s) for s in raw})
        except Exception:
            syms = []
    if not syms:
        syms = _json_get_any("kse100.json") or []
    if syms:
        _json_put("kse100.json", syms)
    return syms


def get_allshr(max_age_hours: int = 24) -> list[str]:
    """Constituents of the KSE All-Share Index (ALLSHR), normalized.
    The whole system (universe, screener, search) is restricted to these."""
    cached = _json_get("allshr.json", max_age_hours * 3600)
    if cached:
        return cached
    syms: list[str] = []
    if mirror.available():
        # "Listed In" on a company page only names the indexes the portal lists
        # for that scrip, so ALLSHR alone under-reports. Union it with the index
        # memberships we hold, then with yesterday's universe from the cache.
        pool = set(mirror.listed_in("ALLSHR"))
        for code in ("KSE100", "KMI30"):
            pool.update(mirror.members(code))
        cached_prev = set(_json_get_any("allshr.json") or [])
        syms = sorted({_norm(s) for s in (pool | cached_prev)})
    if not syms and network_up() and _HAS_PSXDATA:
        try:
            idx = psxdata.tickers(index="ALLSHR")
            syms = sorted({_norm(s) for s in idx})
        except Exception:
            syms = []
    if not syms:
        syms = _json_get_any("allshr.json") or []
    if syms:
        _json_put("allshr.json", syms)
    return syms


def _sectors_from_summary_page() -> pd.DataFrame:
    """Fallback sector fetch — used when psxdata's own token flow gets a
    403 on the data endpoint ("PSX auth error").

    Since Sep-2026 PSX rejects the sector table AJAX call unless it carries
    the X-Req-Id token that PSX embeds in every HTML page. This fallback:
      1. loads the public Sector Summary page
         (https://dps.psx.com.pk/sector-summary) — a plain page, opens even
         when the AJAX endpoint is blocked,
      2. lifts the token out of that page,
      3. pulls the sectorwise table WITH the token attached.
    Returns the same columns as psxdata.sectors().
    """
    from psxdata.constants import REQUEST_HEADERS, TOKEN_HEADER
    from psxdata.parsers.html import parse_html_table
    from psxdata.parsers.normalizers import coerce_numeric
    from psxdata.scrapers.token import extract_token

    s = requests.Session()
    s.headers.update(REQUEST_HEADERS)
    page = s.get("https://dps.psx.com.pk/sector-summary", timeout=30)
    page.raise_for_status()
    tok = extract_token(page.text)
    hdrs = {TOKEN_HEADER: tok,
            "Referer": "https://dps.psx.com.pk/sector-summary"} if tok else {}
    r = s.get("https://dps.psx.com.pk/sector-summary/sectorwise",
              headers=hdrs, timeout=30)
    r.raise_for_status()
    rows = parse_html_table(r.text)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ("advance", "decline", "unchanged", "turnover", "market_cap_b"):
        if col in df.columns:
            df[col] = df[col].apply(coerce_numeric)
    return df


def get_sectors(max_age_min: int = 60) -> pd.DataFrame:
    """Sector aggregates: cache → mirror (computed from snapshots) → live."""
    p = CACHE / "sectors.csv"
    if p.exists() and (time.time() - p.stat().st_mtime) < max_age_min * 60:
        try:
            df = pd.read_csv(p)
            if len(df):
                return df
        except Exception:
            pass
    df = pd.DataFrame()
    if mirror.available():
        try:
            df = mirror.sectors()
        except Exception:
            df = pd.DataFrame()
    if (df is None or df.empty) and network_up() and _HAS_PSXDATA:
        try:
            df = psxdata.sectors()
        except Exception:
            df = pd.DataFrame()
    if (df is None or df.empty) and network_up():
        # 403 "PSX auth error" path: grab the token from the Sector Summary
        # page itself and retry the table with it.
        try:
            df = _sectors_from_summary_page()
        except Exception:
            df = pd.DataFrame()
    if df is None:
        df = pd.DataFrame()
    if not df.empty:
        _safe_to_csv(df, p)
    else:  # 4) stale cache
        try:
            if p.exists():
                df = pd.read_csv(p)
        except Exception:
            pass
    return df


# ── index levels (best-effort, two free fallbacks) ──────────────────
def _dps_homepage_indices() -> list[dict]:
    html = requests.get("https://dps.psx.com.pk/", headers=UA, timeout=15).text
    # Structured cards: topIndices__item__name / __val / __change / __changep
    pat = re.compile(
        r"topIndices__item__name\">([^<]+)</div>.*?topIndices__item__val\">"
        r"([\d,\.]+)</div>.*?topIndices__item__change\">.*?([+-]?[\d,\.]+)"
        r"</div>.*?topIndices__item__changep\">\(([+-]?[\d\.]+)%\)",
        re.S)
    pretty = {"KSE100": "KSE-100", "KSE30": "KSE-30", "KMI30": "KMI-30",
              "ALLSHR": "KSE All-Share", "BKTI": "Banking Index"}
    out = []
    for name, val, chg, pct in pat.findall(html):
        try:
            out.append({"name": pretty.get(name.strip(), name.strip()),
                        "value": float(val.replace(",", "")),
                        "change": float(chg.replace(",", "")),
                        "pct": float(pct), "source": "dps.psx.com.pk"})
        except ValueError:
            continue
    order = {"KSE-100": 0, "KSE-30": 1, "KMI-30": 2, "KSE All-Share": 3}
    return sorted(out, key=lambda r: order.get(r["name"], 9))[:6]


def _yahoo_index() -> list[dict]:
    import yfinance as yf
    t = yf.Ticker("^KSE100")
    h = t.history(period="5d")
    if h is None or len(h) < 2:
        return []
    c = h["Close"].iloc[-1]
    p = h["Close"].iloc[-2]
    chg = float(c - p)
    return [{"name": "KSE-100", "value": round(float(c), 2),
             "change": round(chg, 2), "pct": round(chg / float(p) * 100, 2),
             "source": "Yahoo Finance"}]


def get_index_levels() -> list[dict]:
    """Index levels: cache → mirror → DPS homepage → Yahoo → stale cache."""
    cached = _json_get("indices.json", 15 * 60)
    if cached:
        return cached
    if mirror.available():
        try:
            out = mirror.indices()
            if out:
                _json_put("indices.json", out)
                return out
        except Exception:
            pass
    if network_up():
        for fn in (_dps_homepage_indices, _yahoo_index):
            try:
                out = fn()
                if out:
                    _json_put("indices.json", out)
                    return out
            except Exception:
                continue
    return _json_get_any("indices.json") or []


def data_sources() -> dict:
    """Everything the UI needs to explain where the numbers came from."""
    m = mirror.meta()
    return {
        "mirror": m,
        "network": network_state(),
        "cache_files": len(list(CACHE.glob("*"))),
        "psxdata_installed": _HAS_PSXDATA,
    }


def clear_cache() -> None:
    for f in CACHE.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass
