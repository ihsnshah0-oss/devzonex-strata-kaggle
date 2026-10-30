"""FastAPI backend — serves the dashboard + JSON API.

Run:  uvicorn src.app.server:app --host 0.0.0.0 --port 8111
Then open http://<laptop-ip>:8111 on your phone (same Wi-Fi).
"""
import sys
import math as _math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STATIC = Path(__file__).parent / "static"

# Pakistan time is fixed UTC+5 (no daylight saving), so no tz database needed.
PKT = timezone(timedelta(hours=5), name="PKT")
SIGNALS_META = ROOT / "data" / "cache" / "signals_meta.json"

# Strategy Fit Guide generator state (background thread, see /api/fit-guide)
import threading as _threading
_FIT_LOCK = _threading.Lock()
_FIT_STATE = {"status": "idle", "last_run": None, "error": None}


def _now_pkt() -> datetime:
    return datetime.now(PKT)


def _read_meta() -> dict:
    try:
        import json
        return json.loads(SIGNALS_META.read_text())
    except Exception:
        return {}


def _write_meta(patch: dict) -> None:
    try:
        import json
        meta = _read_meta()
        meta.update(patch)
        SIGNALS_META.write_text(json.dumps(meta))
    except Exception:
        pass


def _market_status(now: datetime) -> tuple[str, str]:
    """PSX regular-market hours (psx.com.pk): Mon-Thu one session 9:30-15:30;
    Friday has TWO sessions (9:17-12:00 and 14:30-16:30) with a midday break."""
    mins = now.hour * 60 + now.minute
    wd = now.weekday()
    if wd >= 5:
        return "CLOSED", "Weekend — market reopens Monday 9:15 PKT"
    if wd == 4:  # Friday: morning session + afternoon session
        if mins < 9 * 60 + 15:
            return "CLOSED", "Pre-open — Friday morning session opens 9:15 PKT"
        if mins < 12 * 60:
            return "OPEN", "Friday morning session 9:15–12:00 PKT"
        if mins < 14 * 60 + 30:
            return "CLOSED", "Friday midday break — afternoon session reopens 2:30 PM PKT"
        if mins < 16 * 60 + 30:
            return "OPEN", "Friday afternoon session 2:30–4:30 PM PKT"
        return "CLOSED", "Post-close — market reopens Monday 9:15 PKT"
    # Monday to Thursday: single continuous session
    if 9 * 60 + 30 <= mins < 15 * 60 + 30:
        return "OPEN", "Regular session 9:30–15:30 PKT (Mon–Thu)"
    if mins < 9 * 60 + 30:
        return "CLOSED", "Pre-open — market opens 9:30 PKT"
    return "CLOSED", "Post-close — market reopens next working day 9:30 PKT"

from src.analysis import full_report as frep  # noqa: E402
from src.analysis import money as money_mod  # noqa: E402
from src.analysis import indicators as ind  # noqa: E402
from src.analysis import llm as llmmod  # noqa: E402
from src.analysis import researcher as R  # noqa: E402
from src.analysis import risk as riskmod  # noqa: E402
from src.analysis import strategy as strat  # noqa: E402
from src.backtest import engine as bt  # noqa: E402
from src.data import fundamentals as fundmod  # noqa: E402
from src.data import investify as invmod  # noqa: E402
from src.data import news as newsmod  # noqa: E402
from src.data import psx_client as psx  # noqa: E402
from src.data import psx_official as pso  # noqa: E402
from src.data import appconfig as appcfg  # noqa: E402
from src.data import sentiment as sent  # noqa: E402
from src.paper import ledger  # noqa: E402
from src.screener import engine as screen  # noqa: E402
from src.app import report_pdf as pdfmod  # noqa: E402

# ── JSON safety net ─────────────────────────────────────────────────
# Market data is full of blanks: a symbol with no previous close has no change,
# a sector without market cap has no weight. Pandas represents those as NaN/inf,
# and `json.dumps` refuses to serialise them ("Out of range float values"),
# which used to turn a harmless blank into a 500. Scrub at the boundary once
# instead of trusting every endpoint to be careful.
def _json_safe(obj):
    if isinstance(obj, float):
        return obj if _math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    try:  # numpy scalars, Decimal, timestamps → JSON-friendly primitives
        import numpy as _np
        if isinstance(obj, _np.floating):
            f = float(obj)
            return f if _math.isfinite(f) else None
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.bool_):
            return bool(obj)
    except Exception:
        pass
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return super().render(_json_safe(content))


app = FastAPI(title="PSX Live & Research", version="1.1",
              default_response_class=SafeJSONResponse)

# Let the standalone PSX_Heatmap.html (opened from disk, origin "null")
# read the local API. Local education app, no auth — safe to open up.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])


def _watchlist() -> list[dict]:
    return appcfg.get_watchlist()


def _wmap() -> dict:
    return {w["symbol"].upper(): w for w in _watchlist()}


# ── basics ──────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "watchlist": [w["symbol"] for w in _watchlist()]}


@app.get("/api/quote")
def daily_quote():
    """A fresh trading lesson — random pick on every call."""
    import random
    from src.analysis import landing as landmod
    text, author, lesson = random.choice(landmod.QUOTES)
    return {"text": text, "author": author, "lesson": lesson}


@app.get("/api/watchlist-meta")
def watchlist_meta():
    return {"watchlist": _watchlist()}


# ── market pulse ────────────────────────────────────────────────────
@app.get("/api/landing")
def landing():
    """Stalwart-style landing payload: pulse-ring state, headline, quote,
    bento metrics, composite trend, alerts feed, sector heatmap."""
    from src.analysis import landing as landmod
    return landmod.build()


@app.get("/api/pulse")
def pulse():
    snap = psx.get_market_snapshot().copy()
    snap["change_pct"] = __import__("pandas").to_numeric(snap["change_pct"], errors="coerce")
    adv = int((snap["change_pct"] > 0).sum())
    dec = int((snap["change_pct"] < 0).sum())
    unc = int((snap["change_pct"] == 0).sum())
    tradable = snap[snap["price"] > 0].copy()

    def top(df, n=6):
        return [{k: (None if str(v) == "nan" else v) for k, v in r.items()}
                for r in df.head(n).to_dict(orient="records")]

    gainers = top(tradable.sort_values("change_pct", ascending=False))
    losers = top(tradable.sort_values("change_pct", ascending=True))
    active = top(tradable.sort_values("volume_avg_30d", ascending=False))
    try:  # official PSX market internals (best-effort, never blocks pulse)
        official = pso.get_market_overview()
    except Exception:
        official = {}
    indices = psx.get_index_levels()
    # merge extra official indices (sector/dividend ones the DPS widget lacks)
    if official.get("indices"):
        have = {i["name"] for i in indices}
        for i in official["indices"]:
            if i["name"] not in have:
                indices.append({**i, "source": "psx.com.pk"})
    return {"indices": indices, "breadth": {
        "advancing": adv, "declining": dec, "unchanged": unc, "total": len(snap)},
        "gainers": gainers, "losers": losers, "most_active": active,
        "official": official,
        "note": "Most-active ranked by 30-day average volume"}


# ── watchlist ───────────────────────────────────────────────────────
def _wl_rows(items):
    """Build full rows (snapshot + fundamentals + mcap + 5d/21d chg) for watch items."""
    from concurrent.futures import ThreadPoolExecutor

    def _posf(v):
        try:
            f = float(v)
        except Exception:
            return None
        if f != f or f in (float("inf"), float("-inf")) or f <= 0:
            return None
        return f

    # market-cap fallback for stocks whose fundamentals lack it
    try:
        snap = psx.get_market_snapshot()
        snap_mcap = {}
        for _, r in snap.iterrows():
            v = _posf(r.get("market_cap"))
            if v:
                snap_mcap[str(r["symbol"]).upper()] = v
    except Exception:
        snap_mcap = {}

    def one(w):
        sym = w["symbol"].upper()
        try:
            h = psx.get_history(sym)
            s = ind.snapshot(h)
            fund = fundmod.get_fundamentals(sym, w.get("name", ""))
            cl = h["close"]

            def pc(n):
                try:
                    if len(cl) > n and float(cl.iloc[-1 - n]) > 0:
                        return round((float(cl.iloc[-1]) / float(cl.iloc[-1 - n]) - 1) * 100, 2)
                except Exception:
                    pass
                return None

            return {"symbol": sym, "name": w.get("name", sym),
                    "sector": w.get("sector", ""), "snapshot": s,
                    "pe": fund.get("pe_ratio"), "yield": fund.get("dividend_yield"),
                    "mcap": _posf(fund.get("market_cap")) or snap_mcap.get(sym),
                    "day_chg": fund.get("change_pct"),
                    "chg5": pc(5), "chg21": pc(21)}
        except Exception as e:
            return {"symbol": sym, "name": w.get("name", sym), "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, items))
    return rows


@app.get("/api/watchlist")
def watchlist(list_name: str | None = Query(default=None, alias="list")):
    items = _watchlist()
    if list_name and list_name.strip().lower() != "master":
        wl = next((l for l in appcfg.get_lists()
                   if l["name"].lower() == list_name.strip().lower()), None)
        if wl:
            keep = set(wl["symbols"])
            items = [w for w in items if w["symbol"].upper() in keep]
    rows = _wl_rows(items)
    try:
        if any("error" not in r for r in rows):
            _write_meta({"watchlist_signals_at": _now_pkt().isoformat(timespec="seconds")})
    except Exception:
        pass
    # ── PRICE CROSS-CHECK (every watchlist load): Yahoo cache → TradingView
    #    → PSX Data Portal. Patches the shown close when our history cache is
    #    a session behind, and reports exactly which date prices are from. ──
    verify = {"error": "cross-check unavailable"}
    try:
        from src.data import crosscheck as xc
        ok_rows = [r for r in rows if "error" not in r]
        local_close = {r["symbol"]: (r.get("snapshot") or {}).get("close") for r in ok_rows}
        local_date = {r["symbol"]: str((r.get("snapshot") or {}).get("date") or "")[:10]
                      for r in ok_rows}
        vv = xc.verify_symbols([r["symbol"] for r in ok_rows], local_close, local_date)
        meta = vv.pop("_meta", {})
        mismatches, patched = [], []
        for r in ok_rows:
            v = vv.get(r["symbol"]) or {}
            snap = r.get("snapshot") or {}
            if v.get("price") is None:
                continue
            ours = snap.get("close")
            our_d = str(snap.get("date") or "")[:10]
            if v.get("as_of") and v["as_of"] > our_d:
                tvq = xc.tradingview_quotes([r["symbol"]]).get(r["symbol"]) or {}
                snap["close"] = round(float(v["price"]), 2)
                snap["date"] = v["as_of"]
                for k in ("open", "high", "low"):
                    if tvq.get(k):
                        snap[k] = tvq[k]
                r["px_src"] = v["source"]
                patched.append(r["symbol"])
            elif ours and abs(float(v["price"]) - float(ours)) / float(ours) > 0.01:
                mismatches.append(r["symbol"])
            r["px_verify"] = {"as_of": v.get("as_of"), "stale": v.get("stale"),
                              "source": v.get("source")}
        all_dates = [x.get("as_of") for x in vv.values()
                     if isinstance(x, dict) and x.get("as_of")]
        verify = {**meta,
                  "as_of": max(all_dates) if all_dates else None,
                  "stale": any(x.get("stale") for x in vv.values() if isinstance(x, dict)),
                  "patched": patched, "mismatches": mismatches}
    except Exception as e:
        verify = {"error": str(e)[:120]}
    return {"rows": rows, "flags": appcfg.get_flags(), "verify": verify}


@app.get("/api/watchlist/report.pdf")
def watchlist_pdf():
    """One-page printable sheet of the Master watchlist."""
    from . import watchlist_pdf as wlpdf
    rows = [r for r in _wl_rows(_watchlist()) if "error" not in r]
    return Response(wlpdf.build(rows), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=master_watchlist.pdf"})


# ── 🔥 index wheels: live KSE-100 constituents (TradingView tape, cached) ──
_WHEEL_CACHE = {"ts": 0.0, "data": None}
_WHEEL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

@app.get("/api/heatmap/kse100")
def heatmap_kse100():
    """KSE-100 treemap data (size = market cap, colour = day change).

    Built from the portal mirror. The previous build asked TradingView for the
    same numbers; that meant an empty heatmap whenever the third party was
    unreachable — which is exactly when you want your own copy most.
    """
    import time as _t
    from src.data import kse100 as k100
    from src.data import mirror
    now = _t.time()
    if _WHEEL_CACHE["data"] and now - _WHEEL_CACHE["ts"] < 120:
        return _WHEEL_CACHE["data"]
    rows, index = [], None
    members = list(k100.SYMBOLS)
    try:
        snap = mirror.snapshot()
    except Exception:
        snap = None
    if snap is not None and not snap.empty:
        by_symbol = snap.set_index("symbol")
        try:
            members = mirror.members("KSE100") or members
        except Exception:
            pass
        try:
            weekly = mirror.week_changes()
        except Exception:
            weekly = {}
        for sym in members:
            if sym not in by_symbol.index:
                continue
            r = by_symbol.loc[sym]
            if getattr(r, "ndim", 1) > 1:
                r = r.iloc[0]
            close = _f(r.get("price"))
            if not close:
                continue
            label = k100.SECTOR_OF.get(sym) or str(r.get("sector_label") or "Other")
            rows.append({
                "s": sym,
                "sec": label,
                "c": close,
                "chg": _f(r.get("change_pct")),
                "w": weekly.get(sym),
                "mcap": _f(r.get("market_cap")),
                "vol": _f(r.get("volume")),
            })
        try:
            levels = mirror.indices()
        except Exception:
            levels = []
        kse = next((i for i in levels if i["code"] == "KSE100"), None)
        if kse:
            index = {"close": kse["value"], "chg": kse["pct"]}
    out = {"ok": True, "rows": rows, "index": index,
           "count": len(rows), "total": len(members),
           "source": "PSX Data Portal mirror",
           "as_of": _now_pkt().isoformat(timespec="seconds")}
    if rows:
        _WHEEL_CACHE.update({"ts": now, "data": out})
    return out


# ──  SECTORS tab: aggregate all 36 PSX sectors from the live tape ───────
_SEC_CACHE = {"ts": 0.0, "data": None}
_DPS_SEC, _DPS_STK, _DPS_TS = {}, {}, 0.0
_SEC_COLS = ["close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y",
             "Perf.YTD", "price_52_week_high", "price_52_week_low", "market_cap_basic",
             "price_earnings_ttm", "earnings_per_share_basic_ttm", "total_revenue",
             "net_income", "total_assets", "float_shares_outstanding", "debt_to_equity"]

@app.on_event("startup")
def _boot_agents():
    from src.agents.analysis import register_agents
    register_agents()


@app.get("/api/agents")
def agents_status():
    from src.agents import agent_status
    return {"ok": True, "agents": agent_status()}


@app.get("/api/stock/{symbol}/deep")
def stock_deep(symbol: str):
    from src.agents.analysis import deep_pack
    return deep_pack(symbol)


@app.get("/api/desk")
def desk():
    from src.data import psx_desk as deskmod
    return deskmod.fetch_desk()



# ── sector tape: one row per symbol, built from the portal mirror ────
# The Sectors tab needs close, day/week/month/quarter/half/year/YTD returns,
# 52-week range, market cap, sales, PAT and free float per symbol. All of that
# is in the mirror, so no third-party scanner is involved (the old build called
# TradingView in 180-symbol chunks with a 25s timeout — slow, and not PSX data).
_TAPE_CACHE = {"ts": 0.0, "rows": {}}
_TAPE_TTL = 900.0


def _sector_tape(symbols) -> dict:
    """{symbol: [close, chg%, w1, 1m, 3m, 6m, 1y, ytd, h52, l52, mcap, …]}"""
    import time as _t
    now = _t.time()
    if _TAPE_CACHE["rows"] and now - _TAPE_CACHE["ts"] < _TAPE_TTL:
        return _TAPE_CACHE["rows"]
    rows: dict = {}
    try:
        import pandas as pd
        from src.data import mirror
        if not mirror.available():
            return {}
        snap = mirror.snapshot()
        if snap.empty:
            return {}
        snap = snap.set_index("symbol")
        for sym in symbols:
            if sym not in snap.index:
                continue
            r = snap.loc[sym]
            if hasattr(r, "iloc") and getattr(r, "ndim", 1) > 1:  # duplicate rows
                r = r.iloc[0]
            perf = mirror.performance(sym) or {}
            fin = mirror.financials(sym)
            sales = pat = None
            if not fin.empty:
                ann = fin[(fin["quarter"].isna()) & (fin["fiscal_year"].notna())]
                if not ann.empty:
                    last_year = ann["fiscal_year"].max()
                    ann = ann[ann["fiscal_year"] == last_year]
                    for metric, target in (("revenue", "sales"), ("net_income", "pat")):
                        v = ann[ann["metric"] == metric]["value"]
                        if len(v) and v.iloc[0] == v.iloc[0]:
                            val = float(v.iloc[0]) * 1000.0
                            if target == "sales":
                                sales = val
                            else:
                                pat = val
            rows[sym] = [
                _f(r.get("price")),                      # 0 close
                _f(r.get("change_pct")),                 # 1 day %
                perf.get("chg_1w"),                      # 2 1 week
                perf.get("chg_1m"),                      # 3 1 month
                perf.get("chg_3m"),                      # 4 3 months
                perf.get("chg_6m"),                      # 5 6 months
                perf.get("chg_1y"),                      # 6 1 year
                _f(r.get("ytd_change_pct")),             # 7 YTD
                perf.get("high_52w") or _f(r.get("high_52w")),   # 8
                perf.get("low_52w") or _f(r.get("low_52w")),     # 9
                _f(r.get("market_cap")),                 # 10 market cap
                None, None,                              # 11, 12 unsupported
                sales,                                   # 13 sales
                pat,                                     # 14 PAT
                None,                                    # 15 total assets
                _f(r.get("free_float")),                 # 16 free float shares
                None,                                    # 17 debt / equity
            ]
    except Exception:
        return {}
    _TAPE_CACHE.update({"ts": now, "rows": rows})
    return rows


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


@app.get("/api/sectors")
def sectors_data():
    import time as _t
    from src.data import psx_sectors as psec
    now = _t.time()
    if _SEC_CACHE["data"] and now - _SEC_CACHE["ts"] < 300:
        return _SEC_CACHE["data"]
    # official DPS sector feed (best-effort; TV aggregates remain as fallback)
    global _DPS_SEC, _DPS_STK, _DPS_TS
    if now - _DPS_TS > 120 and psx.network_up():
        try:
            from src.data import dps_sectors as _dps
            _DPS_SEC, _DPS_STK = _dps.fetch_sectorwise()
            _DPS_TS = now
        except Exception:
            pass
    quotes = _sector_tape(psec.ALL_SYMBOLS)

    def num(d, i):
        try:
            v = d[i]
            return float(v) if v is not None else None
        except Exception:
            return None
    tv_mcap = {}
    for sym, d in quotes.items():
        mc = num(d, 10)
        if mc:
            tv_mcap[sym] = mc
    out_secs, total_mcap = [], 0.0
    for sec, rows in psec.SECTORS.items():
        mcap = chg_w = w_w = m_w = q_w = s_w = y_w = yt_w = 0.0
        h52 = l52 = 0.0
        sales = pat = assets = shares = ff = 0.0
        n = 0
        wsum = 0.0
        de_w = 0.0
        for sym, _name in rows:
            d = quotes.get(sym)
            if not d:
                continue
            close = num(d, 0) or 0
            if not close:
                continue
            n += 1
            mc = num(d, 10) or 0
            w = mc
            mcap += mc
            chg_w += (num(d, 1) or 0) * w
            w_w += (num(d, 2) or 0) * w
            m_w += (num(d, 3) or 0) * w
            q_w += (num(d, 4) or 0) * w
            s_w += (num(d, 5) or 0) * w
            y_w += (num(d, 6) or 0) * w
            yt_w += (num(d, 7) or 0) * w
            h52 += num(d, 8) or 0
            l52 += num(d, 9) or 0
            sales += num(d, 13) or 0
            pat += num(d, 14) or 0
            ta = num(d, 15)
            if ta:
                assets += ta
            sh = mc / close
            shares += sh
            ffv = num(d, 16)
            if ffv:
                ff += ffv
            de = num(d, 17)
            if de is not None:
                wsum += w
                de_w += de * w
        if not n:
            # listed but no live tape data (e.g. suspended closed-end funds)
            out_secs.append({"name": sec.title(), "n": len(rows), "mcap": None,
                             "chg": None, "w1": None, "w1m": None, "w3m": None,
                             "w6m": None, "w1y": None, "ytd": None, "h52": None,
                             "l52": None, "sales": None, "pat": None, "assets": None,
                             "liab": None, "shares": None, "ff": None, "eps": None,
                             "bv": None, "pe": None, "ps": None})
            continue
        total_mcap += mcap
        equity = assets / (1 + de_w / wsum) if assets and wsum else None
        eps = pat / shares if shares else None
        out_secs.append({
            "name": sec.title(), "n": n, "mcap": mcap,
            "chg": chg_w / mcap if mcap else None,
            "w1": w_w / mcap if mcap else None,
            "w1m": m_w / mcap if mcap else None,
            "w3m": q_w / mcap if mcap else None,
            "w6m": s_w / mcap if mcap else None,
            "w1y": y_w / mcap if mcap else None,
            "ytd": yt_w / mcap if mcap else None,
            "h52": h52 or None, "l52": l52 or None,
            "sales": sales or None, "pat": pat or None, "assets": assets or None,
            "liab": (assets - equity) if equity else None,
            "shares": shares or None, "ff": ff or None,
            "eps": eps, "bv": (equity / shares) if equity and shares else None,
            "pe": (mcap / pat) if pat else None,
            "ps": (mcap / sales) if sales else None,
        })
    # ── merge the official DPS feed ──
    def _norm(name):
        return "".join(c for c in name.upper() if c.isalnum())
    dps_by_norm = {_norm(k): k for k in _DPS_SEC}
    used = set()
    for s in out_secs:
        hit = dps_by_norm.get(_norm(s["name"]))
        if not hit:
            continue
        used.add(hit)
        v = _DPS_SEC[hit]
        s["code"] = v["code"]
        s["adv"], s["dec"], s["unch"] = v["adv"], v["dec"], v["unch"]
        s["turnover"] = v["turnover"]
        if v["mcap_bn"]:
            s["mcap"] = v["mcap_bn"] * 1e9
        qs = _DPS_STK.get(hit, [])
        if qs:
            s["n"] = len(qs)
            wsum = csum = ew_n = ew_c = 0.0
            for q in qs:
                if q["pct"] is None:
                    continue
                w = tv_mcap.get(q["sym"], 0)
                if w > 0:
                    csum += q["pct"] * w
                    wsum += w
                else:
                    ew_c += q["pct"]
                    ew_n += 1
            if wsum > 0:
                s["chg"] = csum / wsum
            elif ew_n:
                s["chg"] = ew_c / ew_n
    # sectors the portal lists that our static map missed
    for k, v in _DPS_SEC.items():
        if k in used:
            continue
        qs = _DPS_STK.get(k, [])
        wsum = csum = ew_n = ew_c = 0.0
        for q in qs:
            if q["pct"] is None:
                continue
            w = tv_mcap.get(q["sym"], 0)
            if w > 0:
                csum += q["pct"] * w
                wsum += w
            else:
                ew_c += q["pct"]
                ew_n += 1
        chg = csum / wsum if wsum > 0 else (ew_c / ew_n if ew_n else None)
        out_secs.append({"name": k.title().replace(" & ", " & "), "n": len(qs),
                         "mcap": (v["mcap_bn"] or 0) * 1e9 or None, "chg": chg,
                         "w1": None, "w1m": None, "w3m": None, "w6m": None,
                         "w1y": None, "ytd": None, "h52": None, "l52": None,
                         "sales": None, "pat": None, "assets": None, "liab": None,
                         "shares": None, "ff": None, "eps": None, "bv": None,
                         "pe": None, "ps": None, "code": v["code"],
                         "adv": v["adv"], "dec": v["dec"], "unch": v["unch"],
                         "turnover": v["turnover"]})
    total_mcap = sum(s["mcap"] for s in out_secs if s["mcap"])
    for s in out_secs:
        s["weight"] = (s["mcap"] / total_mcap * 100) if (total_mcap and s["mcap"]) else None
    out_secs.sort(key=lambda x: -(x["mcap"] or 0))
    out = {"ok": True, "sectors": out_secs, "total_mcap": total_mcap,
           "live": len(quotes), "dps": bool(_DPS_SEC),
           "as_of": _now_pkt().isoformat(timespec="seconds")}
    if out_secs:
        _SEC_CACHE.update({"ts": now, "data": out})
    return out


@app.get("/api/watchlists")
def watchlists_all():
    """Master list + extra lists + color flags + per-stock notes."""
    return {"master": [w["symbol"].upper() for w in _watchlist()],
            "lists": appcfg.get_lists(), "flags": appcfg.get_flags(),
            "notes": appcfg.get_list_notes()}


@app.post("/api/watchlists/list")
def watchlists_list_save(body: dict):
    """Create or replace an extra watchlist. Symbols must exist in the master list."""
    name = str(body.get("name", "")).strip()
    if not name or name.lower() == "master":
        return {"ok": False, "error": "give the list a name (it cannot be 'Master')"}
    master = {w["symbol"].upper() for w in _watchlist()}
    raw = [str(s).upper().strip() for s in (body.get("symbols") or [])]
    syms, seen = [], set()
    for s in raw:
        if s in master and s not in seen:
            syms.append(s); seen.add(s)
    bad = [s for s in raw if s not in master]
    lists = [l for l in appcfg.get_lists() if l["name"].lower() != name.lower()]
    lists.append({"name": name, "symbols": syms})
    appcfg.save({"watchlists": lists})
    return {"ok": True, "list": {"name": name, "symbols": syms},
            "skipped_not_in_master": bad}


@app.delete("/api/watchlists/list/{name}")
def watchlists_list_delete(name: str):
    lists = [l for l in appcfg.get_lists() if l["name"].lower() != name.lower()]
    appcfg.save({"watchlists": lists})
    return {"ok": True, "lists": lists}


@app.post("/api/watchlists/flag")
def watchlists_flag(body: dict):
    """Set (or clear, with empty color) a color flag on a symbol."""
    sym = str(body.get("symbol", "")).upper().strip()
    color = str(body.get("color", "") or "").strip().lower()
    flags = appcfg.get_flags()
    if color:
        flags[sym] = color
    else:
        flags.pop(sym, None)
    appcfg.save({"flags": flags})
    return {"ok": True, "flags": flags}


@app.post("/api/watchlists/note")
def watchlists_note(body: dict):
    """Set (or clear, with empty text) a per-stock note inside one extra watchlist."""
    lst = str(body.get("list", "")).strip()
    sym = str(body.get("symbol", "")).upper().strip()
    text = str(body.get("text", "") or "").strip()[:500]
    if not lst or lst.lower() == "master":
        return {"ok": False, "error": "Notes belong to a sub-list (not the Master list)."}
    if lst not in {l["name"] for l in appcfg.get_lists()}:
        return {"ok": False, "error": f'No watchlist named "{lst}".'}
    master = {w["symbol"].upper() for w in _watchlist()}
    if sym not in master:
        return {"ok": False, "error": f"{sym} is not in the Master watchlist."}
    notes = appcfg.get_list_notes()
    if text:
        notes.setdefault(lst, {})[sym] = text
    else:
        notes.get(lst, {}).pop(sym, None)
        if not notes.get(lst):
            notes.pop(lst, None)
    appcfg.save({"list_notes": notes})
    return {"ok": True, "notes": appcfg.get_list_notes()}


@app.post("/api/stock/{symbol}/resync")
def stock_resync(symbol: str):
    """Force-fetch the LATEST data for one symbol right now (bypasses caches)."""
    symbol = symbol.upper().strip()
    w = _wmap().get(symbol, {})
    base = psx._norm(symbol)
    for cand in dict.fromkeys([symbol, base, base + "XD", base + "XR", base + "XB"]):
        for fn in (f"quote_{cand}.json", f"fund_{cand}.json",
                   f"eod_{cand}.csv", f"eod_{cand}_lite.csv"):
            try:
                (psx.CACHE / fn).unlink(missing_ok=True)
            except Exception:
                pass
    try:
        h = psx.get_history(symbol, max_age_hours=0)
        s = ind.snapshot(h)
        try:
            q = psx.get_quote(symbol)
        except Exception:
            q = {}
        fund = fundmod.get_fundamentals(symbol, w.get("name", ""), max_age_min=0)
        return {"ok": True, "symbol": symbol, "snapshot": s,
                "quote": q, "fundamentals": fund}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── single stock ────────────────────────────────────────────────────
@app.get("/api/stock/{symbol}")
def stock(symbol: str):
    symbol = symbol.upper()
    w = _wmap().get(symbol, {})
    h = psx.get_history(symbol)
    s = ind.snapshot(h)
    fund = fundmod.get_fundamentals(symbol, w.get("name", ""))
    return {"symbol": symbol, "name": w.get("name", symbol),
            "sector": w.get("sector", fund.get("sector_name", "")),
            "snapshot": s, "fundamentals": fund,
            "intrinsic": fundmod.intrinsic_value(fund, s.get("close"), symbol)}


@app.get("/api/stock/{symbol}/history")
def history(symbol: str, start: str | None = None, end: str | None = None):
    df = psx.get_history(symbol.upper())
    if start:
        df = df[df["date"] >= start]
    if end:
        df = df[df["date"] <= end]
    t = ind.compute_all(df)
    out = []
    for r in t.itertuples():
        out.append({"date": str(r.date.date()) if hasattr(r.date, "date") else str(r.date),
                    "open": round(float(r.open), 2), "high": round(float(r.high), 2),
                    "low": round(float(r.low), 2), "close": round(float(r.close), 2),
                    "volume": int(r.volume) if r.volume == r.volume else 0,
                    "sma20": _r(r.sma20), "sma50": _r(r.sma50), "sma200": _r(r.sma200),
                    "rsi14": _r(r.rsi14)})
    return {"symbol": symbol.upper(), "bars": out}


def _r(v):
    try:
        return round(float(v), 2) if v == v else None
    except (TypeError, ValueError):
        return None


@app.get("/api/stock/{symbol}/research")
def research(symbol: str):
    w = _wmap().get(symbol.upper(), {})
    out = R.full_report(symbol, w.get("name", ""))
    if "error" not in out:
        ts = _now_pkt().isoformat(timespec="seconds")
        out["generated_at"] = ts
        _write_meta({f"research_{symbol.upper()}": ts})
    return out


@app.get("/api/stock/{symbol}/proposal")
def proposal(symbol: str, capital: float | None = None, risk: float | None = None):
    w = _wmap().get(symbol.upper(), {})
    s = appcfg.get_settings()
    if not capital or capital <= 0:
        capital = float(s.get("paper_cash", 1000000))
    if not risk or risk <= 0:
        risk = float(s.get("default_risk_pct", 1.0))
    out = strat.build_proposal(symbol, w.get("name", ""), capital, risk)
    if "error" not in out:
        ts = _now_pkt().isoformat(timespec="seconds")
        out["generated_at"] = ts
        _write_meta({f"proposal_{symbol.upper()}": ts})
    return out


@app.get("/api/stock/{symbol}/news")
def stock_news(symbol: str):
    w = _wmap().get(symbol.upper(), {})
    items = newsmod.get_stock_news(symbol, w.get("name", ""))
    items += sent.reddit_mentions(symbol)
    for a in invmod.announcements_for(symbol):
        items.insert(0, {"title": f"[PSX filing · {a['category']}] {a['title']}",
                         "link": a["link"], "published": a["when"],
                         "summary": a["summary"] or "", "source": "Investify Announcements",
                         "pdf": a.get("pdf", ""), "sentiment_hint": a.get("sentiment", "")})
    scored = [{**i, "sentiment": sent.score_text(i.get("title", "") + " " + i.get("summary", ""))}
              for i in items]
    return {"symbol": symbol.upper(), "sentiment": sent.analyze_items(items), "items": scored[:25]}


@app.get("/api/news")
def market_news(limit: int = 30):
    items = invmod.fetch_news() + newsmod.get_market_news(limit=limit)
    return {"sentiment": sent.analyze_items(items),
            "items": [{**i, "sentiment": sent.score_text(i.get("title", "") + " " + i.get("summary", ""))}
                      for i in items]}


@app.get("/api/announcements")
def announcements(symbol: str | None = None, watchlist_only: bool = False, limit: int = 30):
    """PSX company filings via Investify (free). Filter by symbol or your watchlist."""
    items = invmod.fetch_announcements()
    if symbol:
        items = [a for a in items if a["symbol"] == symbol.upper()]
    elif watchlist_only:
        wl = {str(w.get("symbol", "")).upper() for w in appcfg.get_watchlist()}
        items = [a for a in items if a["symbol"] in wl]
    return {"count": len(items[:limit]), "items": items[:limit]}


# ── official PSX website feeds (psx.com.pk + financials.psx.com.pk) ─
@app.get("/api/market/overview")
def market_overview():
    """Market internals: breadth, turnover, session status and index levels.

    Live scraping of psx.com.pk/market-summary fails whenever the site is slow,
    redesigned or the machine is offline — which used to leave the whole
    overview panel empty. When that happens we derive the same numbers from the
    portal mirror, and say so in `source`.
    """
    try:
        ov = pso.get_market_overview()
    except Exception:
        ov = None
    if ov:
        return ov
    fallback = _overview_from_mirror()
    if fallback:
        return fallback
    return {"error": "market overview unavailable: no live summary and no mirror"}


def _overview_from_mirror() -> dict:
    """Advance/decline, volume, value and index levels computed from the mirror."""
    try:
        import pandas as pd
        from src.data import mirror
        if not mirror.available():
            return {}
        snap = mirror.snapshot()
        if snap.empty:
            return {}
        priced = snap[snap["price"].notna()]
        chg = pd.to_numeric(priced["change_pct"], errors="coerce")
        vol = pd.to_numeric(priced["volume"], errors="coerce").fillna(0)
        turnover = float((priced["price"].fillna(0) * vol).sum())
        breadth = {
            "advanced": int((chg > 0).sum()),
            "declined": int((chg < 0).sum()),
            "unchanged": int((chg == 0).sum()),
            "total": int(len(priced)),
        }
        idx = [{"name": i["name"], "value": i["value"], "change": i["change"],
                "pct": i["pct"]}
               for i in mirror.indices()[:8] if i.get("value")]
        kse = next((i for i in mirror.indices() if i["code"] == "KSE100"), None)
        as_of = mirror.as_of() or ""
        today = _now_pkt().date().isoformat()
        return {
            "source": "PSX Data Portal mirror",
            "note": "psx.com.pk summary unreachable — figures derived from the "
                    "last captured portal session",
            "as_of": as_of,
            "status": "Open" if as_of[:10] == today else "Closed",
            "volume": float(vol.sum()),
            "value": turnover,
            "trades": None,
            "breadth": breadth,
            "indices": idx,
        }
    except Exception:
        return {}


@app.get("/api/stock/{symbol}/filings")
def stock_filings(symbol: str, limit: int = 40):
    """Official annual/quarterly report history from financials.psx.com.pk
    with direct PDF download links."""
    try:
        rows = pso.get_company_filings(symbol, limit=limit)
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)[:200], "items": []}
    return {"symbol": symbol.upper(), "count": len(rows), "items": rows,
            "source": "financials.psx.com.pk"}


@app.get("/api/filings/recent")
def filings_recent(limit: int = 30):
    """Market-wide calendar of the latest official report filings."""
    return {"count": min(limit, 200), "items": pso.get_recent_filings(limit=limit),
            "source": "financials.psx.com.pk"}


# ── universe (search) ───────────────────────────────────────────────
@app.get("/api/universe")
def universe():
    df = screen.universe()
    df = df[df["price"] > 0].sort_values("market_cap", ascending=False, na_position="last")
    return {"symbols": [{"symbol": r["symbol"], "price": _r(r.get("price")),
                         "chg": _r(r.get("change_pct")), "sector": str(r.get("sector", ""))}
                        for r in df.to_dict(orient="records")]}


# ── screener ────────────────────────────────────────────────────────
class ScreenReq(BaseModel):
    filters: dict = {}


@app.get("/api/screener/presets")
def presets():
    return {"presets": [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "filters"},
                         "filters": v["filters"]} for k, v in screen.PRESETS.items()]}


@app.post("/api/screener/run")
def screener_run(req: ScreenReq):
    return screen.run(req.filters or {})


# ── backtest ────────────────────────────────────────────────────────
@app.get("/api/backtest/strategies")
def bt_strats():
    return {"strategies": [{"id": k, "name": v["name"], "desc": v["desc"], "params": v["params"]}
                           for k, v in bt.STRATEGIES.items()]}


class BTReq(BaseModel):
    symbol: str = "OGDC"
    strategy: str = "sma_cross"
    start: str | None = None
    end: str | None = None
    capital: float | None = None
    commission_pct: float | None = None
    slippage_pct: float | None = None
    use_atr_stop: bool = True
    atr_mult: float = 2.0
    take_profit_mult: float = 0.0
    params: dict = {}


@app.post("/api/backtest/run")
def bt_run(req: BTReq):
    s = appcfg.get_settings()
    cap = req.capital if (req.capital and req.capital > 0) else float(s.get("paper_cash", 1000000))
    comm = req.commission_pct if req.commission_pct is not None else float(s.get("commission_pct", 0.15))
    slip = req.slippage_pct if req.slippage_pct is not None else float(s.get("slippage_pct", 0.10))
    return bt.run(req.symbol, req.strategy, req.start, req.end, cap,
                  comm, slip, req.use_atr_stop,
                  req.atr_mult, req.take_profit_mult, req.params)


def _cached_report(symbol: str, fresh: bool = False) -> dict:
    """A-to-Z executive report with a 12h disk cache (stale served if the
    rebuild fails, so the report page never breaks mid-fetch)."""
    import json as _json
    import time as _time

    sym = str(symbol).upper().strip()
    p = ROOT / "data" / "cache" / f"report_{sym}.json"

    def _stale():
        if p.exists():
            try:
                return _json.loads(p.read_text())
            except Exception:
                return None
        return None

    if not fresh and p.exists() and (_time.time() - p.stat().st_mtime) < 12 * 3600:
        cached = _stale()
        if cached:
            return cached
    try:
        rep = frep.build_full_report(sym)
    except Exception as e:
        return _stale() or {"symbol": sym, "error": str(e)}
    if not rep.get("error"):
        try:
            p.write_text(_json.dumps(rep, default=str))
        except Exception:
            pass
    return rep


@app.get("/api/stock/{symbol}/report")
def stock_report(symbol: str, fresh: bool = False):
    """Full A-to-Z executive report as JSON (screen preview + PDF source)."""
    return _cached_report(symbol, fresh=fresh)


@app.get("/api/stock/{symbol}/report.pdf")
def stock_report_pdf(symbol: str):
    """Full A-to-Z executive report as a downloadable PDF."""
    rep = _cached_report(symbol)
    if "error" in rep:
        return {"ok": False, "error": rep["error"]}
    try:
        from src.agents.analysis import deep_pack
        rep["deep"] = deep_pack(symbol)
    except Exception:
        pass
    pdf = pdfmod.build_pdf(rep)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename={rep['symbol']}_executive_report.pdf"})


# ── compare up to 5 stocks side by side (A-to-Z) ──────────────────────
def _compare_block(symbol: str) -> dict:
    """Everything comparable for one stock: price, technicals, fundamentals,
    filings, performance series (12M, normalized to 100)."""
    sym = psx.resolve_symbol(str(symbol).upper().strip())
    out: dict = {"symbol": sym, "ok": True}
    try:
        h = psx.get_history(sym)
        s = ind.snapshot(h)
        out["tech"] = s
        lb = h.iloc[-1]
        last_c, open_c = float(lb["close"]), float(lb["open"])
        out["session"] = {"open": round(open_c, 2), "high": round(float(lb["high"]), 2),
                          "low": round(float(lb["low"]), 2), "close": round(last_c, 2),
                          "volume": float(lb.get("volume", 0) or 0),
                          "date": str(lb["date"])[:10],
                          "direction": "Buyers stronger" if last_c >= open_c
                          else "Sellers stronger"}
        # long-run price CAGR (years of available history)
        cc = h["close"].astype(float)
        years = len(cc) / 252
        if years >= 1 and float(cc.iloc[0]) > 0:
            out["price_cagr"] = round(((last_c / float(cc.iloc[0])) ** (1 / years) - 1) * 100, 2)
        # 12-month performance normalized to 100 (weekly points for charting)
        import pandas as _pd
        c = h["close"].astype(float).tail(252)
        if len(c) > 40:
            base = float(c.iloc[0])
            w = c.iloc[::5]
            out["perf12m"] = [{"d": str(d)[:10], "v": round(float(v) / base * 100, 2)}
                              for d, v in zip(h["date"].tail(252).iloc[::5], w)]
        else:
            out["perf12m"] = []
    except Exception as e:
        out["tech"] = {"error": str(e)[:150]}
        out["perf12m"] = []
    try:
        f = fundmod.get_fundamentals(sym)
        hs = f.get("history_stats") or {}
        yf = f.get("yfinance") or {}
        st = f.get("statements") or {}
        q = f.get("quote") or {}
        # payout: Yahoo ratio (fraction) → % ; else fundamentals already
        # computed a % from DPS÷EPS when the statements were available.
        payout = f.get("payout_ratio")
        if payout is None and yf.get("payoutRatio") is not None:
            payout = round(float(yf["payoutRatio"]) * 100, 1)
        hi52, lo52 = hs.get("high_52w"), hs.get("low_52w")
        px = f.get("price") or hs.get("last_close")
        wk52_pos = None
        try:
            if px and hi52 and lo52 and hi52 > lo52:
                wk52_pos = round((float(px) - lo52) / (hi52 - lo52) * 100, 1)
        except Exception:
            pass
        out["fund"] = {
            "name": f.get("long_name") or f.get("company_name") or sym,
            "sector": f.get("sector_name") or "",
            "price": px,
            "change_pct": f.get("change_pct"),
            "change_1y_pct": f.get("change_1y_pct") or
            (round(float(yf["52WeekChange"]) * 100, 2) if yf.get("52WeekChange") else None),
            "market_cap": f.get("market_cap"),
            "pe_ratio": f.get("pe_ratio") or yf.get("trailingPE"),
            "forward_pe": yf.get("forwardPE"),
            "dividend_yield": f.get("dividend_yield") or yf.get("dividendYield"),
            "payout_ratio": payout,
            "price_to_book": yf.get("priceToBook") or f.get("price_to_book"),
            "eps": f.get("eps") or yf.get("trailingEps"),
            "book_value": yf.get("bookValue"),
            "roe": f.get("roe") if f.get("roe") is not None else
            (round(float(yf["returnOnEquity"]) * 100, 2) if yf.get("returnOnEquity") else None),
            "roa": f.get("roa"),
            "profit_margin": f.get("profit_margin") if f.get("profit_margin") is not None else
            (round(float(yf["profitMargins"]) * 100, 2) if yf.get("profitMargins") else None),
            "debt_equity": f.get("debt_equity") if f.get("debt_equity") is not None
            else yf.get("debtToEquity"),
            "current_ratio": yf.get("currentRatio"),
            "free_cashflow": f.get("free_cash_flow") or yf.get("freeCashflow"),
            "beta": f.get("beta") or yf.get("beta"),
            # FY financial snapshot (Yahoo statements) — the analyzer layout
            "revenue": st.get("total_revenue"), "net_income": st.get("net_income"),
            "total_assets": st.get("total_assets"), "total_equity": st.get("total_equity"),
            "total_liabilities": st.get("total_liabilities"), "total_debt": st.get("total_debt"),
            "eps_growth": st.get("eps_growth"), "revenue_growth_y": st.get("revenue_growth"),
            "net_income_growth": st.get("earnings_growth"),
            "perf_1m": hs.get("perf_1m"), "perf_3m": hs.get("perf_3m"),
            "perf_6m": hs.get("perf_6m"), "perf_1y": hs.get("perf_1y"),
            "high_52w": hi52, "low_52w": lo52,
            "off_high_pct": hs.get("off_high_pct"), "wk52_pos": wk52_pos,
            "indices": q.get("listed_in"),
            "avg_vol_30d": q.get("volume_avg_30d"),
        }
        out["price_cagr"] = out.get("price_cagr")
        out["session"] = out.get("session") or {}
    except Exception as e:
        out["fund"] = {"error": str(e)[:150]}
    try:
        fil = pso.get_company_filings(sym, limit=1)
        out["last_filing"] = (fil[0]["posted"] if fil else None)
    except Exception:
        out["last_filing"] = None
    return out


@app.get("/api/compare")
def compare(symbols: str):
    """Side-by-side comparison of up to 5 stocks. ?symbols=OGDC,PPL,FFC"""
    from concurrent.futures import ThreadPoolExecutor
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:5]
    if not syms:
        return {"error": "pass ?symbols=A,B,C", "stocks": []}
    with ThreadPoolExecutor(max_workers=5) as ex:
        stocks = list(ex.map(_compare_block, syms))
    return {"count": len(stocks), "stocks": stocks,
            "as_of": datetime.now(PKT).isoformat(timespec="minutes")}


@app.get("/api/compare.pdf")
def compare_pdf(symbols: str):
    """Download the full side-by-side comparison as a PDF."""
    from src.app import compare_pdf as cmppdf
    data = compare(symbols)
    if not data.get("stocks"):
        return {"ok": False, "error": "no symbols"}
    pdf = cmppdf.build_pdf(data)
    name = "_vs_".join(s["symbol"] for s in data["stocks"])
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename=compare_{name}.pdf"})


# ── paper trading ───────────────────────────────────────────────────
class OrderReq(BaseModel):
    symbol: str
    side: str
    qty: int
    price: float | None = None
    note: str = ""


@app.get("/api/paper/account")
def paper_account():
    return positions_wrap()


def positions_wrap():
    return ledger.positions()


@app.get("/api/paper/history")
def paper_history():
    return {"orders": ledger.history()}


@app.get("/api/paper/statement")
def paper_statement():
    """Real broker statement (account W615) with live market prices."""
    import pandas as _pd
    from src.paper import statement as stmt
    prices: dict = {}
    try:
        snap = psx.get_market_snapshot()
        pr = dict(zip(snap["symbol"].astype(str).str.upper(),
                      _pd.to_numeric(snap["price"], errors="coerce")))
        prices = {k: float(v) for k, v in pr.items() if _pd.notna(v)}
    except Exception:
        pass
    return stmt.build(prices)


@app.post("/api/paper/order")
def paper_order(req: OrderReq):
    return ledger.place_order(req.symbol, req.side, req.qty, req.price, req.note)


# ── REAL broker account (live ledger, account W615) ─────────────────
class BrokerTradeReq(BaseModel):
    symbol: str
    side: str = "buy"
    qty: float = 0
    rate: float | None = None      # blank → live price
    date: str | None = None


class BrokerCloseReq(BaseModel):
    symbol: str
    qty: float | None = None       # blank → whole position
    rate: float | None = None      # blank → live price


def _live_prices() -> dict:
    import pandas as _pd
    prices: dict = {}
    try:
        snap = psx.get_market_snapshot()
        pr = dict(zip(snap["symbol"].astype(str).str.upper(),
                      _pd.to_numeric(snap["price"], errors="coerce")))
        prices = {k: float(v) for k, v in pr.items() if _pd.notna(v)}
    except Exception:
        pass
    return prices


@app.get("/api/broker/account")
def broker_account():
    """Live book of the REAL broker account: positions, realized P&L,
    full trade history — all at current market prices."""
    from src.broker import ledger as broker_ledger
    return broker_ledger.build(_live_prices())


@app.get("/api/broker/brief")
def broker_brief():
    """Compact dashboard brief of the REAL account: win/loss pies data +
    what changed since the previous visit (snapshot saved per visit)."""
    import json as _json
    from src.broker import ledger as broker_ledger
    b = broker_ledger.brief(_live_prices())
    snap_file = ROOT / "data" / "broker_visit.json"
    now = datetime.now(PKT)
    t = b["totals"]
    cur = {"at": now.isoformat(timespec="minutes"),
           "mv": t["market_value"], "upnl": t["unrealized_pnl"],
           "rpnl": t["realized_pnl"], "trades": b["book_trades"],
           "open": b["open_n"]}
    prev = None
    try:
        if snap_file.exists():
            prev = _json.loads(snap_file.read_text())
    except Exception:
        prev = None

    def sub(a, c):
        try:
            return None if a is None or (prev or {}).get(c) is None \
                else round(float(a) - float(prev[c]), 2)
        except Exception:
            return None
    delta = None
    if prev and prev.get("at"):
        delta = {"at": prev["at"],
                 "mv_chg": sub(t["market_value"], "mv"),
                 "upnl_chg": sub(t["unrealized_pnl"], "upnl"),
                 "rpnl_chg": sub(t["realized_pnl"], "rpnl"),
                 "trades_added": (b["book_trades"] - int(prev.get("trades", 0) or 0))}
    try:
        snap_file.write_text(_json.dumps(cur))
    except Exception:
        pass
    return {**b, "since_last": delta}


@app.post("/api/broker/trade")
def broker_trade(req: BrokerTradeReq):
    """Add a new trade to the real broker account."""
    from src.broker import ledger as broker_ledger
    rate = req.rate
    if not rate:
        rate = _live_prices().get(req.symbol.upper().strip())
        if not rate:
            return {"error": "no live price found — please enter the rate"}
    try:
        t = broker_ledger.add_trade(req.symbol, req.side, req.qty, rate, req.date)
        return {"ok": True, "trade": t}
    except ValueError as e:
        return {"error": str(e)}


@app.post("/api/broker/close")
def broker_close(req: BrokerCloseReq):
    """Close all (or part) of an open real position."""
    from src.broker import ledger as broker_ledger
    try:
        t = broker_ledger.close_position(req.symbol, req.qty, req.rate,
                                         _live_prices())
        return {"ok": True, "trade": t}
    except ValueError as e:
        return {"error": str(e)}


@app.post("/api/broker/reset")
def broker_reset():
    """Restore the book to the original W615 statement trades."""
    from src.broker import ledger as broker_ledger
    return broker_ledger.reset()


@app.post("/api/broker/statement/parse")
async def broker_statement_parse(file: UploadFile = File(...)):
    """Read an uploaded broker statement PDF and detect open positions.
    Returns a preview only — nothing is changed until /statement/apply."""
    from src.broker import statement_pdf as spdf
    data = await file.read()
    if len(data) > 25_000_000:
        return {"ok": False, "error": "file too large (max 25 MB)"}
    res = spdf.parse_pdf(data)
    return {"ok": True, "filename": file.filename, **res}


@app.post("/api/broker/statement/apply")
def broker_statement_apply(body: dict):
    """Replace the live book with the confirmed statement rows."""
    from src.broker import ledger as broker_ledger
    try:
        return broker_ledger.import_book(body.get("rows") or [], body.get("date"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/broker/advice")
def broker_advice():
    """Ask the configured AI engine to assess the real broker portfolio.
    Falls back to rule-based notes when no AI key is configured."""
    from src.broker import ledger as broker_ledger
    book = broker_ledger.build(_live_prices())
    pos, tot = book["positions"], book["totals"]
    if not pos:
        return {"ai": False, "text": "No open positions to assess right now."}
    lines = [f"- {p['symbol']}: {p['qty']:,.0f} sh @ avg {p['avg_cost']:.2f}, "
             f"last {p['last'] or 'n/a'}, invested Rs {p['invested']:,.0f}, "
             f"unrealized {p['unrealized']} ({p['unrealized_pct']}%)"
             for p in pos]
    real = book["realized"][-8:]
    real_lines = [f"- {r['date']} {r['symbol']} sold {r['qty']:,.0f} @ {r['rate']:.2f}, "
                  f"P&L Rs {r['pnl']:+,.0f}" for r in real]
    prompt = (
        "You are a disciplined Pakistan Stock Exchange (PSX) swing-trading coach. "
        "Assess this REAL retail portfolio and give practical management advice. "
        "Be specific, concise and use simple English. Include: 1) overall health, "
        "2) the biggest risk right now, 3) what to hold / trim / close and why, "
        "4) one concrete rule to follow this week. Do not invent prices; use only "
        "the figures given.\n\n"
        f"Open positions (live):\n" + "\n".join(lines) + "\n\n"
        f"Totals: invested Rs {tot['still_invested']:,.0f}, market value "
        f"{tot['market_value']}, unrealized {tot['unrealized_pnl']}, "
        f"realized P&L {tot['realized_pnl']:+,.0f}\n\n"
        "Recent closed trades:\n" + ("\n".join(real_lines) or "- none")
    )
    try:
        reply = llmmod.generate(prompt, timeout=60)
        if reply:
            return {"ai": True, "text": reply}
        return {"ai": False, "text": _broker_fallback(book)}
    except Exception as e:
        return {"ai": False, "error": str(e)[:300],
                "text": _broker_fallback(book)}


def _broker_fallback(book: dict) -> str:
    """Rule-based advice when no AI engine is configured."""
    pos, tot = book["positions"], book["totals"]
    mv = tot["market_value"] or sum(p["market_value"] or 0 for p in pos)
    notes = ["⚙️ AI engine not configured (add a key in Settings → AI) — here are rule-based notes instead:"]
    if mv:
        for p in pos:
            w = (p["market_value"] or 0) / mv * 100
            if w > 35:
                notes.append(f"• {p['symbol']} is {w:.0f}% of the book — over-concentration; consider trimming below ~30%.")
            if (p["unrealized_pct"] or 0) <= -7:
                notes.append(f"• {p['symbol']} is down {p['unrealized_pct']:.1f}% — revisit the thesis or set a hard stop.")
            if (p["unrealized_pct"] or 0) >= 12:
                notes.append(f"• {p['symbol']} is up {p['unrealized_pct']:.1f}% — consider partial profit-booking.")
    if (tot["unrealized_pnl"] or 0) < 0:
        notes.append("• Portfolio is underwater: prefer selling weakness into strength, not adding to losers.")
    if not any(n.startswith("•") for n in notes):
        notes.append("• Position weights and P&L look balanced — keep following your stop-loss discipline.")
    notes.append("• General rule: never risk more than 1–2% of capital on any single idea.")
    return "\n".join(notes)


@app.post("/api/paper/reset")
def paper_reset(cash: float | None = None):
    if not cash or cash <= 0:
        cash = float(appcfg.get_settings().get("paper_cash", 1000000))
    return ledger.reset(cash)


# ── risk ────────────────────────────────────────────────────────────
class RiskReq(BaseModel):
    symbol: str = "OGDC"
    entry: float = 0
    stop: float = 0
    target: float = 0
    qty: int = 0
    capital: float = 1000000


@app.post("/api/risk/check")
def risk_check(req: RiskReq):
    ldcp = None
    try:
        q = psx.get_quote(req.symbol)
        ldcp = float(q.get("ldcp") or q.get("LDCP") or 0) or None
    except Exception:
        pass
    return riskmod.check_trade(req.symbol, req.entry, req.stop, req.target,
                               req.qty, req.capital, ldcp)


# ── clock / signals status / refresh ────────────────────────────────
@app.get("/api/signals/status")
def signals_status():
    now = _now_pkt()
    meta = _read_meta()
    status, note = _market_status(now)
    return {"server_time_pkt": now.isoformat(timespec="seconds"),
            "market_status": status, "market_note": note,
            "last_watchlist_signals_at": meta.get("watchlist_signals_at"),
            "per_symbol": {k: v for k, v in meta.items()
                            if k != "watchlist_signals_at"}}


class RefreshReq(BaseModel):
    full: bool = False


@app.post("/api/refresh")
def refresh(req: RefreshReq):
    """Fetch latest data + recompute signals.

    Quick (default): clears quotes, market snapshot, indices, news, then
    rebuilds pulse + watchlist signals. Full: also re-downloads ALL price
    history (slow, several minutes) — rarely needed (history is daily data).
    """
    cache = ROOT / "data" / "cache"
    for pat in ("quote_*.json", "screener.csv", "indices.json",
                "sectors.csv", "news_market.json", "official_overview.json"):
        for f in cache.glob(pat):
            try:
                f.unlink()
            except Exception:
                pass
    if req.full:
        for f in cache.glob("eod_*.csv"):
            try:
                f.unlink()
            except Exception:
                pass
    result: dict = {"full": req.full}
    try:
        result["pulse"] = pulse()
    except Exception as e:
        result["pulse_error"] = str(e)[:200]
    try:
        result["watchlist"] = watchlist()
    except Exception as e:
        result["watchlist_error"] = str(e)[:200]
    ts = _now_pkt().isoformat(timespec="seconds")
    _write_meta({"watchlist_signals_at": ts})
    result["refreshed_at"] = ts
    return result


# ── settings (no-code control center) ─────────────────────────────────
def _validate_settings(payload: dict) -> list[str]:
    import re as _re
    errs: list[str] = []
    wl = payload.get("watchlist")
    if wl is not None:
        if not isinstance(wl, list) or not wl:
            errs.append("Watchlist must have at least 1 stock.")
        elif len(wl) > 30:
            errs.append("Watchlist can have at most 30 stocks.")
        else:
            seen: set[str] = set()
            for i, w in enumerate(wl, 1):
                sym = str((w or {}).get("symbol", "")).upper().strip()
                if not _re.fullmatch(r"[A-Z0-9]{1,12}", sym or ""):
                    errs.append(f"Row {i}: symbol must be 1-12 capital letters/numbers (e.g. OGDC).")
                elif sym in seen:
                    errs.append(f"Row {i}: {sym} is listed twice.")
                seen.add(sym)

    def num(sec: str, key: str, lo: float, hi: float, label: str):
        sec_d = payload.get(sec)
        if isinstance(sec_d, dict) and key in sec_d and sec_d[key] is not None:
            try:
                v = float(sec_d[key])
            except (TypeError, ValueError):
                errs.append(f"{label} must be a number.")
                return
            if not (lo <= v <= hi):
                errs.append(f"{label} must be between {lo} and {hi}.")

    num("settings", "paper_cash", 10000, 1e12, "Starting cash")
    num("settings", "default_risk_pct", 0.1, 10, "Risk per trade %")
    num("settings", "circuit_breaker_pct", 1, 20, "Circuit breaker %")
    num("settings", "commission_pct", 0, 2, "Commission %")
    num("settings", "slippage_pct", 0, 2, "Slippage %")
    num("settings", "proposal_valid_days", 1, 30, "Proposal valid days")
    num("settings", "screener_max_stocks", 20, 120, "Screener depth")
    num("ollama", "timeout_sec", 5, 120, "AI timeout")
    llm_p = payload.get("llm")
    if isinstance(llm_p, dict):
        prov = llm_p.get("provider")
        if prov is not None and prov not in ("ollama", "groq", "openrouter", "gemini", "cerebras"):
            errs.append("AI provider must be Ollama, Groq, OpenRouter, Gemini, or Cerebras.")
        num("llm", "timeout_sec", 5, 300, "AI timeout")
    num("ui", "auto_refresh_sec", 30, 600, "Auto-refresh seconds")
    ui = payload.get("ui")
    if isinstance(ui, dict) and ui.get("default_stock"):
        if not _re.fullmatch(r"[A-Z0-9]{1,12}", str(ui["default_stock"]).upper().strip()):
            errs.append("Default stock must be a valid symbol (e.g. OGDC).")
    ol = payload.get("ollama")
    if isinstance(ol, dict) and ol.get("base_url"):
        if not str(ol["base_url"]).startswith(("http://", "https://")):
            errs.append("AI address must start with http:// or https://.")
    return errs


@app.get("/api/settings")
def get_settings():
    return {"ok": True, "config": {
        "watchlist": appcfg.get_watchlist(), "settings": appcfg.get_settings(),
        "ollama": appcfg.get_ollama(), "ui": appcfg.get_ui(),
        "llm": _llm_for_ui(),
        "cloud": {"r2_configured": appcfg.r2_configured()}}}


class SettingsReq(BaseModel):
    watchlist: list | None = None
    settings: dict | None = None
    ollama: dict | None = None
    ui: dict | None = None
    llm: dict | None = None


@app.put("/api/settings")
def put_settings(req: SettingsReq):
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if "llm" in payload:
        payload["llm"] = llmmod.unmask_payload(payload["llm"], appcfg.get_llm())
    errs = _validate_settings(payload)
    if errs:
        return {"ok": False, "errors": errs}
    if "watchlist" in payload:
        norm = []
        for w in payload["watchlist"]:
            sym = str(w.get("symbol", "")).upper().strip()
            norm.append({"symbol": sym, "name": (w.get("name") or sym).strip(),
                         "sector": (w.get("sector") or "").strip(),
                         "reason": (w.get("reason") or "").strip()})
        payload["watchlist"] = norm
    if "ui" in payload and payload["ui"].get("default_stock"):
        payload["ui"]["default_stock"] = str(payload["ui"]["default_stock"]).upper().strip()
    cfg = appcfg.save(payload)
    return {"ok": True, "config": cfg,
            "note": "Saved. Changes apply immediately — no restart needed."}


@app.post("/api/settings/test-ollama")
def test_ollama():
    import time as _t
    o = appcfg.get_ollama()
    t0 = _t.time()
    try:
        import requests
        r = requests.post(f"{o.get('base_url', 'http://localhost:11434')}/api/generate",
                          json={"model": o.get("model", "llama3.1"),
                                "prompt": "Reply with exactly: OK", "stream": False},
                          timeout=min(float(o.get("timeout_sec", 25)), 60))
        ms = int((_t.time() - t0) * 1000)
        if r.status_code == 200 and (r.json().get("response") or "").strip():
            return {"ok": True, "ms": ms,
                    "message": f"Connected in {ms}ms. Reply: {(r.json()['response'] or '').strip()[:120]}"}
        return {"ok": False,
                "message": f"Ollama answered with status {r.status_code}. Is model '{o.get('model')}' downloaded? Run: ollama pull {o.get('model')}"}
    except Exception as e:
        return {"ok": False,
                "message": f"Cannot reach Ollama at {o.get('base_url')}: {str(e)[:150]}. Is Ollama running?"}


class TestAIReq(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


@app.post("/api/settings/test-ai")
def test_ai(req: TestAIReq | None = None):
    if req is None:
        return llmmod.test_connection()
    return llmmod.test_connection(req.provider, req.model, req.api_key)


_MODELS_CACHE: dict = {}


@app.get("/api/ai/models")
def ai_models(provider: str):
    """Live list of FREE models for the chosen provider, so Settings can
    offer a dropdown instead of blind typing. OpenRouter works without a
    key (public list); the others use the key saved in Settings."""
    import time as _t
    import requests as _rq
    prov = (provider or "ollama").lower()
    now = _t.time()
    hit = _MODELS_CACHE.get(prov)
    if hit and now - hit[0] < 300:
        return hit[1]

    def done(models, note=""):
        out = {"provider": prov, "models": models, "note": note}
        _MODELS_CACHE[prov] = (now, out)
        return out

    key = ""
    if prov != "ollama":
        sub = appcfg.get_llm().get(prov) or {}
        key = str(sub.get("api_key") or "").strip()

    try:
        if prov == "openrouter":
            r = _rq.get("https://openrouter.ai/api/v1/models", timeout=20)
            r.raise_for_status()
            data = r.json().get("data", [])
            free = sorted(m["id"] for m in data
                          if str((m.get("pricing") or {}).get("prompt", "1")) in ("0", "0.0")
                          or m["id"].endswith(":free"))
            return done(free or sorted(m["id"] for m in data),
                        "" if free else "no $0 models listed today — cheapest shown")
        if prov == "groq":
            if not key:
                return done([], "paste your free Groq key first, then pick Groq again")
            r = _rq.get("https://api.groq.com/openai/v1/models",
                        headers={"Authorization": f"Bearer {key}"}, timeout=15)
            r.raise_for_status()
            ids = sorted(m["id"] for m in r.json().get("data", [])
                         if m.get("active", True))
            return done(ids)
        if prov == "cerebras":
            if not key:
                return done([], "paste your free Cerebras key first, then pick Cerebras again")
            r = _rq.get("https://api.cerebras.ai/v1/models",
                        headers={"Authorization": f"Bearer {key}"}, timeout=15)
            r.raise_for_status()
            return done(sorted(m["id"] for m in r.json().get("data", [])))
        if prov == "gemini":
            if not key:
                return done([], "paste your free Gemini key first, then pick Gemini again")
            r = _rq.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                        headers={"x-goog-api-key": key}, timeout=15)
            r.raise_for_status()
            ids = sorted(m["name"].replace("models/", "")
                         for m in r.json().get("models", [])
                         if "generateContent" in
                         (m.get("supportedGenerationMethods") or []))
            return done(ids)
        # ollama — models installed on the user's own PC
        o = appcfg.get_ollama()
        r = _rq.get(f"{o.get('base_url', 'http://localhost:11434')}/api/tags", timeout=6)
        r.raise_for_status()
        return done(sorted(m["name"] for m in r.json().get("models", [])),
                    "models downloaded on your PC (ollama pull <name>)")
    except Exception as e:
        return done([], f"could not reach {prov}: {str(e)[:120]}")


@app.get("/api/ai/providers")
def ai_providers():
    return {"providers": llmmod.PROVIDERS}


def _llm_for_ui() -> dict:
    """LLM config for the Settings screen, keys always masked."""
    return llmmod.mask_keys(appcfg.get_llm())


@app.get("/api/cloud/status")
def cloud_status():
    """Cloud integrations status — booleans only, secrets stay on disk."""
    return {"r2_configured": appcfg.r2_configured(),
            "r2_bucket": appcfg.get_r2().get("bucket", "") if appcfg.r2_configured() else ""}


@app.get("/api/fit-guide")
def fit_guide_status():
    """Status of the Strategy Fit Guide generator + whether the PDF exists."""
    p = ROOT / "strategy_fit_guide.pdf"
    return {**_FIT_STATE, "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else 0}


@app.post("/api/fit-guide/run")
def fit_guide_run():
    """Re-run every backtest (25 stocks x all strategies, ~1 min) in a
    background thread and rebuild strategy_fit_guide.pdf."""
    import importlib.util
    import threading

    if _FIT_LOCK.locked():
        return {"ok": False, "error": "already running"}

    def _job():
        with _FIT_LOCK:
            _FIT_STATE["status"] = "running"
            _FIT_STATE["error"] = None
            try:
                spec = importlib.util.spec_from_file_location(
                    "sfg", ROOT / "scripts" / "make_strategy_fit_pdf.py")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.main()
                _FIT_STATE["status"] = "done"
                _FIT_STATE["last_run"] = _now_pkt().isoformat(timespec="seconds")
            except Exception as e:
                _FIT_STATE["status"] = "error"
                _FIT_STATE["error"] = str(e)

    threading.Thread(target=_job, daemon=True).start()
    return {"ok": True, "status": "started"}


@app.get("/api/fit-guide/download")
def fit_guide_download():
    p = ROOT / "strategy_fit_guide.pdf"
    if not p.exists():
        return {"ok": False, "error": "not generated yet - press Regenerate first"}
    return FileResponse(p, media_type="application/pdf",
                        filename="strategy_fit_guide.pdf")


# ── Money Management tab (plan, sizing, journal, discipline) ────────────
@app.get("/api/money")
def money_state():
    return money_mod.get_state()


@app.post("/api/money/plan")
def money_plan_save(body: dict):
    return {"ok": True, "plan": money_mod.save_plan(body)}


@app.post("/api/money/trade")
def money_trade_add(body: dict):
    try:
        rec = money_mod.add_trade(body)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "trade": rec, "state": money_mod.get_state()}


@app.delete("/api/money/trade/{tid}")
def money_trade_del(tid: str):
    ok = money_mod.delete_trade(tid)
    return {"ok": ok, "state": money_mod.get_state()}


@app.post("/api/money/open")
def money_open_add(body: dict):
    try:
        rec = money_mod.add_open(body)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "open": rec, "state": money_mod.get_state()}


@app.delete("/api/money/open/{tid}")
def money_open_del(tid: str):
    ok = money_mod.delete_open(tid)
    return {"ok": ok, "state": money_mod.get_state()}


@app.post("/api/money/open/{tid}/close")
def money_open_close(tid: str, body: dict):
    try:
        rec = money_mod.close_open(tid, float(body["exit"]), str(body.get("exit_date") or ""))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "trade": rec, "state": money_mod.get_state()}


@app.post("/api/money/size")
def money_size(body: dict):
    try:
        return {"ok": True, **money_mod.size_symbol(
            body.get("symbol", ""), float(body["entry"]),
            float(body["stop"]), float(body["target"]))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


BRIEF_CACHE: dict = {}


def _plain_md(t: str) -> str:
    """Turn simple AI markdown (**bold**, * / - bullets) into plain text."""
    if not t:
        return t
    out = []
    for ln in str(t).splitlines():
        s = ln.strip().replace("**", "")
        for b in ("* ", "- ", "+ "):
            if s.startswith(b):
                s = "• " + s[len(b):].strip()
                break
        out.append(s)
    return "\n".join(out).strip()


@app.post("/api/ai/brief")
def ai_morning_brief(body: dict | None = None):
    """'What to watch today' over the Master list — AI when ready, else rules."""
    today = _now_pkt().date().isoformat()
    force = bool((body or {}).get("force"))
    if not force and BRIEF_CACHE.get("date") == today and BRIEF_CACHE.get("text"):
        return {"ok": True, **{k: BRIEF_CACHE[k] for k in ("text", "ai", "date", "note")}}
    rows = [r for r in _wl_rows(_watchlist()) if "error" not in r]
    gain = sorted((r for r in rows if r.get("day_chg") is not None),
                  key=lambda r: -r["day_chg"])
    up3, dn3 = gain[:3], list(reversed(gain[-3:]))
    ov = lambda r, k: (r["snapshot"].get(k))
    oversold = [r["symbol"] for r in rows if (ov(r, "rsi14") or 99) < 32]
    overbought = [r["symbol"] for r in rows if (ov(r, "rsi14") or 0) > 68]
    brk = [r["symbol"] for r in rows if ov(r, "breakout_20d")]
    bdn = [r["symbol"] for r in rows if ov(r, "breakdown_20d")]
    macdup = [r["symbol"] for r in rows if ov(r, "macd_cross_up")]
    sma20up = [r["symbol"] for r in rows if ov(r, "sma20_cross_up")]

    lines = []
    if up3:
        lines.append("• Strongest today: " + ", ".join(f"{r['symbol']} {r['day_chg']:+.1f}%" for r in up3))
    if dn3:
        lines.append("• Weakest today: " + ", ".join(f"{r['symbol']} {r['day_chg']:+.1f}%" for r in dn3))
    if oversold:
        lines.append("• Oversold (RSI under 32) — watch for a bounce: " + ", ".join(oversold))
    if overbought:
        lines.append("• Overbought (RSI over 68) — don't chase, protect profits: " + ", ".join(overbought))
    if brk:
        lines.append("• 20-day breakouts (momentum): " + ", ".join(brk))
    if sma20up:
        lines.append("• Crossed above the 20-day average: " + ", ".join(sma20up))
    if macdup:
        lines.append("• MACD turned up: " + ", ".join(macdup))
    if bdn:
        lines.append("• 20-day breakdowns — avoid holding these: " + ", ".join(bdn))
    lines.append("• Rules: risk 1% per swing, exit at the stop the same day, never add to a loser.")
    rule_brief = "\n".join(lines)

    ai_text, ai, err = None, False, ""
    if appcfg.get_ollama().get("enabled"):
        tbl = "\n".join(
            f"{r['symbol']}: price {r['snapshot'].get('close')}, day {r.get('day_chg')}%, "
            f"5d {r.get('chg5')}%, 21d {r.get('chg21')}%, RSI {r['snapshot'].get('rsi14')}, "
            f"breakout20={bool(ov(r, 'breakout_20d'))}, macd_bull={bool(ov(r, 'macd_bull'))}"
            for r in rows)
        prompt = ("You are a disciplined PSX (Pakistan Stock Exchange) swing trader. "
                  "Here are today's live signals for my watchlist:\n" + tbl +
                  "\nWrite a short 'what to watch today' morning brief: 6-10 bullet lines, "
                  "simple English, naming the 2-4 stocks worth watching for a swing and the "
                  "ones to avoid, each with a one-clause reason. End with one risk-reminder line.")
        try:
            ai_text = _plain_md(llmmod.generate(prompt, timeout=90))
            ai = bool(ai_text)
        except Exception as e:
            err = str(e)[:220]
    text = ai_text or rule_brief
    BRIEF_CACHE.clear()
    BRIEF_CACHE.update({"text": text, "ai": ai, "date": today, "note": err})
    return {"ok": True, "text": text, "ai": ai, "date": today, "note": err}


@app.get("/api/money/trade-plan/{symbol}")
def money_trade_plan_pdf(symbol: str):
    """One-stock Trade Plan PDF: full research + best-fit strategy + sized plan."""
    from src.app import trade_plan_pdf as tppdf
    try:
        data, name = tppdf.build(symbol)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/cache/info")
def cache_info():
    import time as _t
    cache = ROOT / "data" / "cache"
    files: list[dict] = []
    total = 0
    if cache.exists():
        for f in cache.glob("*"):
            try:
                sz = f.stat().st_size
                total += sz
                files.append({"name": f.name, "kb": round(sz / 1024, 1),
                              "age_h": round((_t.time() - f.stat().st_mtime) / 3600, 1)})
            except Exception:
                pass
    files.sort(key=lambda x: -x["kb"])
    return {"files": len(files), "total_kb": round(total / 1024, 1), "top": files[:12]}


@app.post("/api/cache/clear")
def cache_clear():
    cache = ROOT / "data" / "cache"
    n = 0
    if cache.exists():
        for f in cache.glob("*"):
            if f.name == "signals_meta.json":
                continue
            try:
                f.unlink()
                n += 1
            except Exception:
                pass
    return {"ok": True, "cleared": n}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import Response
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           b'<rect width="32" height="32" rx="8" fill="#0b3d2e"/>'
           b'<text x="16" y="23" font-size="18" text-anchor="middle" fill="#c9a227">\xe2\x97\x88</text></svg>')
    return Response(content=svg, media_type="image/svg+xml")


# ── dashboard ───────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def root():
    # no-cache: users always get the newest page after an update
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
