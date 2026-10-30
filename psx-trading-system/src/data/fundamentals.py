"""Fundamentals & profile from free sources.

Priority: market snapshot (DPS via psxdata) + our own EOD history
(52-week range, performance windows) + yfinance (.KA) statement data.
Direct DPS company-page scraping is attempted best-effort.
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

from . import psx_client as psx

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"
UA = {"User-Agent": "Mozilla/5.0 (PSX-Live-Research; personal/educational use)"}

def _sector_name(code, fallback: str = "") -> str:
    """Real PSX sector name for a portal sector code (or a name already).

    The live screener sends numeric codes ("0820"), the portal mirror sends the
    code too but keeps the label alongside it, and some callers hand us a name
    directly. All three are accepted; the fallback is only used when we
    genuinely cannot resolve anything.
    """
    raw = "" if code is None else str(code).strip()
    if raw and not raw.replace(".", "", 1).isdigit():
        return raw.title()                       # already a name
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        n = None
    if n is not None:
        try:
            df = psx.get_sectors()
            for r in df.itertuples():
                try:
                    if int(float(str(r.sector_code))) == n:
                        return str(r.sector_name).title()
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass
        try:  # the snapshot itself carries the label
            from . import mirror
            snap = mirror.snapshot()
            hit = snap[snap["sector"].astype(str).str.strip() == raw]
            if len(hit):
                label = str(hit["sector_label"].iloc[0]).strip()
                if label:
                    return label.title()
        except Exception:
            pass
    return fallback or (f"Sector {raw}" if raw else "—")


def _yf_info(symbol: str) -> dict:
    try:
        import yfinance as yf
        info = yf.Ticker(f"{symbol}.KA").info or {}
        keep = ("trailingPE", "forwardPE", "priceToBook", "priceToSalesTrailing12Months",
                "returnOnEquity", "returnOnAssets",
                "profitMargins", "operatingMargins", "grossMargins",
                "earningsGrowth", "earningsQuarterlyGrowth", "revenueGrowth",
                "revenuePerShare", "trailingEps", "forwardEps", "bookValue",
                "dividendYield", "dividendRate", "payoutRatio", "exDividendDate",
                "marketCap", "enterpriseValue", "sharesOutstanding", "floatShares",
                "debtToEquity", "currentRatio", "quickRatio",
                "totalCash", "totalDebt", "ebitda", "totalRevenue",
                "freeCashflow", "operatingCashflow",
                "beta", "52WeekChange", "heldPercentInsiders", "heldPercentInstitutions",
                "targetMeanPrice", "targetHighPrice", "targetLowPrice",
                "recommendationKey", "numberOfAnalystOpinions", "longName")
        return {k: info.get(k) for k in keep if info.get(k) is not None}
    except Exception:
        return {}


def _yf_statements(symbol: str) -> dict:
    """Balance sheet + income statement + cash flow from Yahoo (.KA).

    The free `.info` endpoint stopped returning most ratios for PSX stocks,
    which left ROE / D-E / payout / margins blank. The statements endpoints
    still work, so we compute those ratios here ourselves.
    """
    try:
        import yfinance as yf
        # PSX adds ex-entitlement suffixes (LUCKXD, BOPXB...) that Yahoo
        # does not know — strip them so the ticker resolves.
        base = symbol
        for suf in ("XD", "XR", "XB", "XW"):
            if base.endswith(suf) and len(base) > len(suf):
                base = base[: -len(suf)]
        t = yf.Ticker(f"{base}.KA")

        def cell(df, key: str, col: int = 0):
            """Latest value for `key`; if the newest column is blank, fall
            back to older columns (some rows are only published yearly)."""
            try:
                if df is not None and key in df.index:
                    row = df.loc[key]
                    for c in range(col, min(df.shape[1], col + 3)):
                        v = row.iloc[c]
                        if v == v and v is not None:  # NaN guard
                            return float(v)
            except Exception:
                pass
            return None

        try:
            bs = t.balance_sheet
        except Exception:
            bs = None
        try:
            fin = t.financials
        except Exception:
            fin = None
        try:
            cf = t.cash_flow
        except Exception:
            cf = None

        out: dict = {}
        out["total_assets"] = cell(bs, "Total Assets")
        out["total_equity"] = cell(bs, "Stockholders Equity")
        out["total_liabilities"] = cell(bs, "Total Liabilities Net Minority Interest")
        out["total_debt"] = cell(bs, "Total Debt")
        out["net_income"] = cell(fin, "Net Income")
        out["total_revenue"] = (cell(fin, "Total Revenue") or
                                cell(fin, "Operating Revenue") or
                                cell(fin, "Net Interest Income"))
        out["eps"] = cell(fin, "Basic EPS")
        out["net_income_prev"] = cell(fin, "Net Income", 1)
        out["total_revenue_prev"] = cell(fin, "Total Revenue", 1)
        out["eps_prev"] = cell(fin, "Basic EPS", 1)
        out["free_cash_flow"] = cell(cf, "Free Cash Flow")

        ni, eq = out["net_income"], out["total_equity"]
        ta, td, rev = out["total_assets"], out["total_debt"], out["total_revenue"]
        if ni and eq:
            out["roe"] = round(ni / eq * 100, 2)
        if ni and ta:
            out["roa"] = round(ni / ta * 100, 2)
        if td is not None and eq:
            out["debt_equity"] = round(td / eq, 2)
        if ni and rev:
            out["profit_margin"] = round(ni / rev * 100, 2)
        if out["net_income_prev"] and ni:
            out["earnings_growth"] = round((ni / out["net_income_prev"] - 1) * 100, 2)
        if out["total_revenue_prev"] and rev:
            out["revenue_growth"] = round((rev / out["total_revenue_prev"] - 1) * 100, 2)
        if out["eps_prev"] and out["eps"]:
            out["eps_growth"] = round((out["eps"] / out["eps_prev"] - 1) * 100, 2)
        return {k: v for k, v in out.items() if v is not None}
    except Exception:
        return {}


def _dps_company_tables(symbol: str) -> dict:
    """DISABLED — the DPS company page no longer serves its financial tables
    (they became JavaScript-rendered and the scrape always came back empty,
    producing pointless network calls/errors on every run).

    Ratios that used to come from here (ROE, D/E, margins, growth) are now
    computed from Yahoo Finance statements in `_yf_statements()`, which works.
    Kept as a stub so callers keep working; returns instantly, no network."""
    return {}


def get_fundamentals(symbol: str, company: str = "", max_age_min: int = 60) -> dict:
    symbol = symbol.upper().strip()

    # Disk cache: fundamentals change slowly and yfinance is the slowest call
    # in the system — caching here removes the biggest source of UI lag.
    import json
    cache_p = CACHE / f"fund_{symbol}.json"
    try:
        if cache_p.exists() and (time.time() - cache_p.stat().st_mtime) < max_age_min * 60:
            return json.loads(cache_p.read_text())
    except Exception:
        pass

    out: dict = {"symbol": symbol, "sources": []}

    # 1) market snapshot row (price, P/E, yield, mcap)
    try:
        snap = psx.get_market_snapshot()
        row = snap[snap["symbol"].astype(str).str.upper() == psx.resolve_symbol(symbol)]
        if len(row):
            r = row.iloc[0].to_dict()
            out.update({k: (None if pd.isna(v) else v)
                        for k, v in r.items()})
            # `source` is filled in by psx_client: the portal mirror when we
            # are offline, the live DPS feed otherwise. Report what actually
            # answered instead of a fixed label.
            out["sources"].append(str(r.get("source") or "DPS market snapshot"))
    except Exception:
        pass

    # 2) quote (LDCP, circuit band, avg volumes)
    try:
        out["quote"] = psx.get_quote(symbol)
        out["sources"].append(str(out["quote"].get("source")
                                  or "DPS quote"))
    except Exception:
        out["quote"] = {}

    # 3) history-derived: 52w range + performance windows
    try:
        h = psx.get_history(symbol)
        if len(h):
            last = float(h["close"].iloc[-1])
            hi52 = float(h["close"].tail(252).max())
            lo52 = float(h["close"].tail(252).min())
            def perf(n):
                if len(h) > n and h["close"].iloc[-n - 1]:
                    return round((last / float(h["close"].iloc[-n - 1]) - 1) * 100, 2)
                return None
            out["history_stats"] = {
                "last_close": last, "last_date": str(h["date"].iloc[-1].date()),
                "high_52w": hi52, "low_52w": lo52,
                "off_high_pct": round((last / hi52 - 1) * 100, 2) if hi52 else None,
                "perf_1m": perf(21), "perf_3m": perf(63),
                "perf_6m": perf(126), "perf_1y": perf(252),
                "bars": len(h),
            }
            out["sources"].append("PSX EOD history (portal mirror)"
                                  if not psx.network_up() else "PSX EOD history")
    except Exception:
        out["history_stats"] = {}

    # 4) yfinance statement ratios
    yf = _yf_info(symbol)
    if yf:
        out["yfinance"] = yf
        out["sources"].append("Yahoo Finance (.KA)")

    # 4b) yfinance statements → ratios Yahoo's free API no longer publishes
    stmt = _yf_statements(symbol)
    if stmt:
        out["statements"] = stmt
        out["sources"].append("Yahoo statements (.KA)")

        def _blank(k):
            return out.get(k) in (None, "")

        def _fill(k, v, nd=2):
            if _blank(k) and v is not None:
                try:
                    out[k] = round(float(v), nd)
                except Exception:
                    pass

        _fill("roe", stmt.get("roe"))
        _fill("roa", stmt.get("roa"))
        _fill("profit_margin", stmt.get("profit_margin"))
        _fill("debt_equity", stmt.get("debt_equity"))
        _fill("free_cash_flow", stmt.get("free_cash_flow"))
        _fill("eps", stmt.get("eps"))
        _fill("earnings_growth", stmt.get("earnings_growth"))
        _fill("revenue_growth", stmt.get("revenue_growth"))
        if _blank("market_cap"):
            sh = yf.get("sharesOutstanding")
            px = out.get("price")
            if sh and px:
                out["market_cap"] = round(float(sh) * float(px), 2)
        if _blank("payout_ratio"):
            px = out.get("price")
            yld = out.get("dividend_yield")
            e = out.get("eps") or yf.get("trailingEps")
            if px and yld and e:
                dps = float(px) * float(yld) / 100.0
                out["payout_ratio"] = round(dps / float(e) * 100, 1)

    # 5) DPS company financial tables
    dps = _dps_company_tables(symbol)
    if dps:
        out["dps_tables"] = dps
        out["sources"].append("dps.psx.com.pk company page")

    out["sector_name"] = _sector_name(out.get("sector"), company)

    # Only cache a result that actually carries data. An offline run that found
    # nothing must not poison the cache for the next hour (that is how a blank
    # "P/E —" survived a restart in the first build).
    if _worth_caching(out):
        try:
            cache_p.write_text(json.dumps(out, default=str))
        except Exception:
            pass
    return out


def _worth_caching(out: dict) -> bool:
    price = out.get("price") or out.get("close")
    stats = out.get("history_stats") or {}
    return bool(price or stats.get("last_close"))


def intrinsic_value(fund: dict, price=None, symbol: str = "") -> dict:
    """Four-method intrinsic value (Pakistan-market benchmark, v3.19).

    Calibrated against the OGDC reference case (2026-10-08):
      1. DCF Model     FCF/share (≈80% of EPS) grown 6% for 5 years,
                       terminal 4%, discounted at 15% (PK risk premium)
      2. DDM Model     Gordon: DPS×(1+8%) / (14% − 8%)
      3. Asset NAV     Balance-sheet book value per share
      4. P/E Multiple  EPS × target sector P/E (sector median, default 6.5×)
    Headline value = average of the methods that could be computed;
    buy target = headline − 20% margin of safety.
    """
    yf = fund.get("yfinance") or {}
    st = fund.get("statements") or {}
    px = price or fund.get("price") or fund.get("close")
    try:
        px = float(px) if px else None
    except (TypeError, ValueError):
        px = None
    eps = fund.get("eps") or st.get("eps") or yf.get("trailingEps")
    mcap = fund.get("market_cap") or yf.get("marketCap")
    shares = yf.get("sharesOutstanding") or ((mcap / px) if mcap and px else None)
    eq = st.get("total_equity")
    bvps = yf.get("bookValue") or ((eq / shares) if eq and shares else None)
    # dividend per share: Yahoo dividendRate first, else yield × price
    dps = yf.get("dividendRate")
    if not dps:
        yld = fund.get("dividend_yield") or yf.get("dividendYield")
        if yld and px:
            yv = float(yld)
            if yv <= 1:          # Yahoo sometimes reports fraction
                yv *= 100
            dps = px * yv / 100.0

    # benchmark assumptions (PK market)
    R_DCF, G_DCF, TG, YRS = 0.15, 0.06, 0.04, 5   # DCF
    R_DDM, G_DDM = 0.14, 0.08                     # Gordon DDM
    MOS = 0.20                                    # margin of safety

    # target sector P/E: median of sector peers if the peers-agent cached it
    target_pe, pe_src = 6.5, "PSX normalised default 6.5×"
    try:
        if symbol:
            pf = CACHE / "deep" / f"peers_{symbol.upper()}.json"
            if pf.exists():
                pj = json.loads(pf.read_text())
                med = pj.get("sector_pe_median")
                if med and med > 0:
                    target_pe, pe_src = round(float(med), 2), f"sector median ({pj.get('sector', '')})"
    except Exception:
        pass

    methods, notes = {}, {}
    try:
        e = float(eps) if eps else None
    except (TypeError, ValueError):
        e = None

    # 1) DCF — FCF/share ≈ 80% of EPS (benchmark proxy when no FCF line)
    if e and e > 0:
        fcf0 = e * 0.80
        v, cf = 0.0, fcf0
        for i in range(1, YRS + 1):
            cf *= 1 + G_DCF
            v += cf / (1 + R_DCF) ** i
        v += cf * (1 + TG) / (R_DCF - TG) / (1 + R_DCF) ** YRS
        methods["DCF Model"] = round(v, 2)
        notes["DCF Model"] = (f"FCF/sh {fcf0:.2f} · g {G_DCF*100:.0f}% ×{YRS}y → "
                              f"{TG*100:.0f}% terminal · r {R_DCF*100:.0f}%")

    # 2) DDM — Gordon growth on the dividend stream
    try:
        d = float(dps) if dps else None
    except (TypeError, ValueError):
        d = None
    if d and d > 0 and R_DDM > G_DDM:
        methods["DDM Model"] = round(d * (1 + G_DDM) / (R_DDM - G_DDM), 2)
        notes["DDM Model"] = (f"DPS {d:.2f} · g {G_DDM*100:.0f}% · r {R_DDM*100:.0f}%")

    # 3) Asset NAV — balance-sheet book value per share
    try:
        b = float(bvps) if bvps else None
    except (TypeError, ValueError):
        b = None
    if b and b > 0:
        methods["Asset NAV"] = round(b, 2)
        notes["Asset NAV"] = "book value per share (assets − liabilities)"

    # 4) P/E multiple — EPS × target sector multiple
    if e and e > 0:
        methods["P/E Multiple"] = round(e * target_pe, 2)
        notes["P/E Multiple"] = f"EPS {e:.2f} × {target_pe}× ({pe_src})"

    value = round(sum(methods.values()) / len(methods), 2) if methods else None
    buy_target = round(value * (1 - MOS), 2) if value else None
    upside = round((value / px - 1) * 100, 2) if value and px else None
    if value and px:
        verdict = ("BUY zone — below MoS target" if px <= buy_target
                   else "HOLD — between target & fair value" if px <= value
                   else "OVERVALUED — above fair value")
    else:
        verdict = None
    return {"value": value, "buy_target": buy_target, "mos_pct": MOS * 100,
            "price": px, "upside_pct": upside, "verdict": verdict,
            "methods": methods, "notes": notes,
            "inputs": {"eps": round(e, 2) if e else None,
                       "dps": round(d, 2) if d else None,
                       "bvps": round(b, 2) if b else None,
                       "target_pe": target_pe,
                       "dcf_discount_pct": R_DCF * 100, "dcf_growth_pct": G_DCF * 100,
                       "dcf_terminal_pct": TG * 100,
                       "ddm_r_pct": R_DDM * 100, "ddm_g_pct": G_DDM * 100}}
