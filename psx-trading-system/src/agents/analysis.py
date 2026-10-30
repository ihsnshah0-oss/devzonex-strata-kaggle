"""Deep fundamental-analysis engines backing the 🧠 Deep Analysis tab.

Six engines (exposed as six background agents + on-demand compute):
  PROFILE / STATEMENTS / RATIOS / VALUATION / PEERS / INTEL(pros-cons)
Everything is disk-cached; agents warm the watchlist in the background so the
UI and the PDF render instantly.
"""
import json
import re
import time
from pathlib import Path

import yaml

from src.agents.core import Agent, start_agents
from src.data import company_intel as ci
from src.data.fundamentals import CACHE, get_fundamentals

DISK = CACHE / "deep"
DISK.mkdir(parents=True, exist_ok=True)
R_DISCOUNT, G_TERM = 0.14, 0.03


# ── helpers ────────────────────────────────────────────────────────────
def _cache(key, sym, ttl):
    p = DISK / f"{key}_{sym}.json"
    try:
        if p.exists() and time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text())
    except Exception:
        pass
    return None


def _store(key, sym, data):
    try:
        (DISK / f"{key}_{sym}.json").write_text(json.dumps(data, default=str))
    except Exception:
        pass


def _yf_ticker(symbol):
    base = symbol
    for suf in ("XD", "XR", "XB", "XW"):
        if base.endswith(suf) and len(base) > len(suf):
            base = base[: -len(suf)]
    return f"{base}.KA"


def _series(df, key, n=4):
    try:
        if df is not None and key in df.index:
            vals = []
            for c in range(min(df.shape[1], n)):
                v = df.loc[key].iloc[c]
                vals.append(float(v) if v == v else None)
            return vals
    except Exception:
        pass
    return []


def _watchlist_symbols():
    try:
        w = yaml.safe_load(Path(__file__).resolve().parents[2].joinpath(
            "config/watchlist.yaml").read_text()) or {}
        return [s["symbol"] for s in w.get("watchlist", []) if s.get("symbol")]
    except Exception:
        return []


def _sector_of(symbol):
    try:
        from src.data.psx_sectors import SYMBOL_SECTOR
        return SYMBOL_SECTOR.get(symbol.upper())
    except Exception:
        return None


def _cagr(old, new, years):
    try:
        if old and new and old > 0 and new > 0 and years:
            return round(((new / old) ** (1 / years) - 1) * 100, 1)
    except Exception:
        pass
    return None


# ── 1) PROFILE + BUSINESS INTEL ────────────────────────────────────────
def profile_pack(symbol, ttl=86400):
    hit = _cache("profile", symbol, ttl)
    if hit:
        return hit
    symbol = symbol.upper()
    fund = get_fundamentals(symbol)
    sector = _sector_of(symbol) or fund.get("sector_name") or ""
    cur = ci.COMPANY_INTEL.get(symbol)
    tpl = ci.SECTOR_TEMPLATE.get((sector or "").upper(), {})
    yf = fund.get("yfinance") or {}
    st = fund.get("statements") or {}
    out = {
        "symbol": symbol,
        "company": fund.get("long_name") or yf.get("longName") or symbol,
        "sector": sector,
        "business": cur.get("business") or tpl.get("business")
        or "Data on the business model is not curated for this company; see its annual report on financials.psx.com.pk.",
        "customers": cur.get("customers") or tpl.get("customers") or "—",
        "moat": cur.get("moat") or tpl.get("moat")
        or "No identifiable moat in the free data — treat as competitive.",
        "assets": {
            "total_assets": st.get("total_assets"),
            "total_equity": st.get("total_equity"),
            "total_liabilities": st.get("total_liabilities"),
            "total_debt": st.get("total_debt"),
            "market_cap": fund.get("market_cap") or yf.get("marketCap"),
        },
        "insider_ownership_pct": yf.get("heldPercentInsiders"),
        "sources": fund.get("sources", []),
    }
    _store("profile", symbol, out)
    return out


# ── 2) FINANCIAL STATEMENTS (multi-year) ───────────────────────────────
def statements_pack(symbol, ttl=7 * 86400):
    """Reported statements, mirror first, Yahoo second.

    The portal mirror carries what PSX actually publishes (Sales, Profit after
    Taxation, EPS, margins, growth per fiscal year). When a symbol is not in
    the mirror we fall back to Yahoo's statement endpoints, and when neither
    answers we return empty series — never invented numbers.
    """
    hit = _cache("stmts", symbol, ttl)
    if hit:
        return hit

    mirror_pack = _mirror_statements(symbol)
    if mirror_pack.get("revenue") or mirror_pack.get("net_income"):
        _store("stmts", symbol, mirror_pack)
        return mirror_pack

    try:
        import yfinance as yfin
        t = yfin.Ticker(_yf_ticker(symbol.upper()))
        fin, bs, cf = t.financials, t.balance_sheet, t.cash_flow
    except Exception:
        fin = bs = cf = None
    rev = _series(fin, "Total Revenue") or _series(fin, "Operating Revenue")
    ni = _series(fin, "Net Income")
    eps = _series(fin, "Basic EPS")
    ocf = _series(cf, "Operating Cash Flow")
    capex = _series(cf, "Capital Expenditure")
    fcf = []
    for i in range(max(len(ocf), len(capex))):
        o = ocf[i] if i < len(ocf) else None
        c = capex[i] if i < len(capex) else None
        f = None
        if o is not None and c is not None:
            f = o + c          # capex reported negative
        elif o is not None:
            f = o
        fcf.append(f)
    if not any(fcf):
        fcf = _series(cf, "Free Cash Flow")
    assets = _series(bs, "Total Assets")
    liab = _series(bs, "Total Liabilities Net Minority Interest") or _series(bs, "Total Liabilities")
    eq = _series(bs, "Stockholders Equity")
    years = []
    try:
        import yfinance as yfin  # noqa
        cols = list(fin.columns) if fin is not None else []
        years = [str(c.year) for c in cols[:4]]
    except Exception:
        pass
    def _first(seq, i=0):
        return seq[i] if len(seq) > i else None

    out = {
        "years": years,
        "revenue": rev, "net_income": ni, "eps": eps, "fcf": fcf,
        "assets": assets, "liabilities": liab, "equity": eq,
        "revenue_cagr_3y": _cagr(_first(rev, -1) if len(rev) > 3 else _first(rev, 1),
                                 _first(rev), 3 if len(rev) > 3 else 1),
        "ni_cagr_3y": _cagr(_first(ni, -1) if len(ni) > 3 else _first(ni, 1),
                            _first(ni), 3 if len(ni) > 3 else 1),
        "net_margin_pct": (round(ni[0] / rev[0] * 100, 1)
                           if rev and ni and rev[0] and ni[0] else None),
        "de_ratio": (round(liab[0] / eq[0], 2)
                     if liab and eq and eq[0] and liab[0] is not None else None),
    }
    if any([rev, ni, assets]):
        _store("stmts", symbol, out)
    return out


def _mirror_statements(symbol) -> dict:
    """Statements from the portal mirror (empty dict when not covered)."""
    try:
        from ..data import mirror
        return mirror.statements(symbol) or {}
    except Exception:
        return {}


# ── 3) KEY RATIOS ──────────────────────────────────────────────────────
def ratios_pack(symbol, ttl=86400):
    hit = _cache("ratios", symbol, ttl)
    if hit:
        return hit
    fund = get_fundamentals(symbol)
    yf = fund.get("yfinance") or {}
    st = fund.get("statements") or {}
    px = fund.get("price") or fund.get("close")
    eq = st.get("total_equity")
    mcap = fund.get("market_cap") or yf.get("marketCap")
    bvps = yf.get("bookValue")
    pb = yf.get("priceToBook") or ((px / bvps) if px and bvps else None)
    eps = fund.get("eps") or st.get("eps") or yf.get("trailingEps")
    div_rate = yf.get("dividendRate")
    dy = fund.get("dividend_yield") or ((yf.get("dividendYield") or 0) * 100
                                        if yf.get("dividendYield") else None)
    payout = fund.get("payout_ratio")
    if payout is None and eps and div_rate:
        payout = round(div_rate / float(eps) * 100, 1)
    fcf = fund.get("free_cash_flow")
    out = {
        "pe": fund.get("pe_ratio") or yf.get("trailingPE"),
        "pb": round(pb, 2) if pb else None,
        "roe": fund.get("roe"),
        "roa": fund.get("roa"),
        "dividend_yield_pct": round(dy, 2) if dy else None,
        "dividend_per_share": div_rate,
        "payout_ratio_pct": payout,
        "debt_equity": fund.get("debt_equity") or st.get("debt_equity"),
        "net_margin_pct": fund.get("profit_margin") or st.get("profit_margin"),
        "fcf": fcf,
        "fcf_yield_pct": round(fcf / mcap * 100, 2) if fcf and mcap else None,
        "dividend_sustainable": bool(payout is not None and 0 <= payout <= 85),
        "eps": eps, "bvps": bvps, "price": px, "market_cap": mcap,
    }
    _store("ratios", symbol, out)
    return out


# ── 4) PEERS (relative valuation) ──────────────────────────────────────
def peers_pack(symbol, ttl=7200):
    hit = _cache("peers", symbol, ttl)
    if hit:
        return hit
    symbol = symbol.upper()
    sector = _sector_of(symbol)
    out = {"sector": sector, "peers": [], "sector_pe_median": None,
           "sector_dy_median": None, "target_pe": None, "target_rank": None}
    if sector:
        try:
            from src.data.psx_sectors import SECTORS
            import requests
            syms = [s for s, _ in SECTORS.get(sector, [])][:80]
            r = requests.post("https://scanner.tradingview.com/pakistan/scan",
                              json={"symbols": {"tickers": ["PSX:" + s for s in syms],
                                                "query": {"types": []}},
                                    "columns": ["close", "market_cap_basic",
                                                "price_earnings_ttm",
                                                "dividend_yield_recent"]},
                              timeout=20,
                              headers={"User-Agent": "Mozilla/5.0"})
            rows = []
            for row in (r.json().get("data") or []):
                d = row.get("d") or []
                if d and d[0]:
                    rows.append({"s": row["s"].replace("PSX:", ""), "mcap": d[1],
                                 "pe": d[2], "dy": d[3]})
            pes = sorted(x["pe"] for x in rows if x["pe"] and x["pe"] > 0)
            dys = sorted(x["dy"] for x in rows if x["dy"])
            rows.sort(key=lambda x: -(x["mcap"] or 0))
            out["peers"] = rows[:12]
            out["sector_pe_median"] = pes[len(pes) // 2] if pes else None
            out["sector_dy_median"] = dys[len(dys) // 2] if dys else None
            me = next((x for x in rows if x["s"] == symbol), None)
            if me:
                out["target_pe"] = me["pe"]
                if me["pe"]:
                    out["target_rank"] = sum(
                        1 for x in rows if x["pe"] and x["pe"] < me["pe"]) + 1
        except Exception:
            pass
    _store("peers", symbol, out)
    return out


# ── 5) VALUATION (DCF + DDM + Graham + relative) ───────────────────────
def valuation_pack(symbol, ttl=86400):
    hit = _cache("val", symbol, ttl)
    if hit:
        return hit
    r = ratios_pack(symbol)
    s = statements_pack(symbol)
    p = peers_pack(symbol)
    fund = get_fundamentals(symbol)
    st = fund.get("statements") or {}
    yf = fund.get("yfinance") or {}
    px = r.get("price")
    eps = r.get("eps")
    models = {}
    notes = []
    fcf = next((f for f in (s.get("fcf") or []) if f), None)
    shares = yf.get("sharesOutstanding") or (
        (r.get("market_cap") / px) if r.get("market_cap") and px else None)
    # DCF on free cash flow
    if fcf and fcf > 0 and shares:
        g = max(0.0, min((s.get("revenue_cagr_3y") or 5) / 100, 0.12))
        cash, ce, v = 0.0, fcf, 0.0
        for t_ in range(1, 6):
            ce *= 1 + g
            v += ce / (1 + R_DISCOUNT) ** t_
        v += ce * (1 + G_TERM) / (R_DISCOUNT - G_TERM) / (1 + R_DISCOUNT) ** 5
        cash_eq = None
        try:
            import yfinance as yfin
            bs = yfin.Ticker(_yf_ticker(symbol)).balance_sheet
            if bs is not None and "Cash And Cash Equivalents" in bs.index:
                cash_eq = float(bs.loc["Cash And Cash Equivalents"].iloc[0])
        except Exception:
            pass
        net_debt = ((st.get("total_debt") or 0) - (cash_eq or 0))
        equity_v = v - net_debt
        per = equity_v / shares
        if per > 0:
            models["DCF (FCF, 2-stage)"] = round(per, 2)
            notes.append(f"DCF: latest FCF grown {g:.0%} for 5y then {G_TERM:.0%}, "
                         f"discounted at {R_DISCOUNT:.0%}, less net debt.")
    # DDM (Gordon growth) — mature dividend payers
    d = r.get("dividend_per_share")
    if not d and px and r.get("dividend_yield_pct"):   # estimate DPS from live yield
        d = px * r["dividend_yield_pct"] / 100
    roe = r.get("roe") or 0
    pay = r.get("payout_ratio_pct")
    if d and d > 0 and px:
        g = min(max(roe, 0) / 100 * (1 - (pay or 60) / 100), 0.08)
        if R_DISCOUNT > g:
            models["Dividend Discount (Gordon)"] = round(d * (1 + g) / (R_DISCOUNT - g), 2)
            notes.append(f"DDM: last dividend Rs {d:.2f} growing {g:.1%} vs {R_DISCOUNT:.0%} required.")
    # Graham
    if eps and eps > 0 and r.get("bvps"):
        models["Graham Number"] = round((22.5 * eps * r["bvps"]) ** 0.5, 2)
    # Relative vs sector median PE
    if eps and eps > 0 and p.get("sector_pe_median"):
        models["Sector-median P/E"] = round(eps * p["sector_pe_median"], 2)
        notes.append(f"Relative: your EPS Rs {eps:.2f} × sector median P/E "
                     f"{p['sector_pe_median']:.1f}.")
    vals = list(models.values())
    fair = round(sum(vals) / len(vals), 2) if vals else None
    mos = round((fair / px - 1) * 100, 1) if fair and px else None
    verdict = ("UNDERVERVALUED" if (mos or 0) >= 15 else
               "OVERVALUED" if (mos or 0) <= -15 else "FAIRLY VALUED")
    out = {"price": px, "models": models, "fair_value": fair,
           "margin_of_safety_pct": mos, "verdict": verdict, "notes": notes,
           "discount_pct": R_DISCOUNT * 100, "terminal_pct": G_TERM * 100}
    _store("val", symbol, out)
    return out


# ── 6) INTEL: industry, management, pros & cons ────────────────────────
def intel_pack(symbol, ttl=43200):
    hit = _cache("intel", symbol, ttl)
    if hit:
        return hit
    symbol = symbol.upper()
    prof = profile_pack(symbol)
    r = ratios_pack(symbol)
    s = statements_pack(symbol)
    v = valuation_pack(symbol)
    sector = prof.get("sector") or ""
    # industry trend from our live sector aggregates (TV 1Y/3M)
    trend = "not measurable from free feeds"
    sec_perf = None
    try:
        import requests
        from src.data.psx_sectors import SECTORS
        syms = [x for x, _ in SECTORS.get(sector, [])][:80]
        if syms:
            rr = requests.post("https://scanner.tradingview.com/pakistan/scan",
                               json={"symbols": {"tickers": ["PSX:" + x for x in syms],
                                                 "query": {"types": []}},
                                     "columns": ["market_cap_basic", "Perf.Y", "Perf.3M"]},
                               timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            w = y1 = q = 0.0
            for row in (rr.json().get("data") or []):
                dd = row.get("d") or []
                if dd and dd[0] and dd[1] is not None:
                    w += dd[0]; y1 += dd[1] * dd[0]
                    q += (dd[2] or 0) * dd[0]
            if w:
                sec_perf = {"y1": round(y1 / w, 1), "m3": round(q / w, 1)}
                trend = ("GROWING" if sec_perf["y1"] > 10 else
                         "STABLE" if sec_perf["y1"] > -5 else "DECLINING")
    except Exception:
        pass
    pros, cons = [], []
    cur = ci.COMPANY_INTEL.get(symbol, {})
    tpl = {}
    for base in (ci.SECTOR_TEMPLATE.get(sector.upper(), {}),):
        tpl = base
    pros += cur.get("pros", tpl.get("pros", []))
    cons += cur.get("cons", tpl.get("cons", []))
    if (s.get("revenue_cagr_3y") or 0) > 8:
        pros.append(f"Revenue compounding {s['revenue_cagr_3y']}% over 3y — top-line momentum.")
    if (r.get("roe") or 0) > 15:
        pros.append(f"ROE {r['roe']}% — management compounds shareholder capital well.")
    if (r.get("debt_equity") or 9) is not None and (r.get("debt_equity") or 9) < 1:
        pros.append(f"Conservative leverage (D/E {r['debt_equity']}).")
    if (r.get("dividend_yield_pct") or 0) > 4 and r.get("dividend_sustainable"):
        pros.append(f"{r['dividend_yield_pct']}% yield backed by a sustainable payout.")
    if (v.get("margin_of_safety_pct") or 0) > 10:
        pros.append("Price sits below modelled intrinsic value — margin of safety.")
    if (r.get("debt_equity") or 0) and r["debt_equity"] > 1.5:
        cons.append(f"High leverage (D/E {r['debt_equity']}) — rate-sensitive balance sheet.")
    if (s.get("ni_cagr_3y") or 0) < 0:
        cons.append("Earnings have shrunk over the last three years.")
    if (r.get("payout_ratio_pct") or 0) > 90:
        cons.append("Payout ratio above 90% — dividend stretches earnings.")
    if (v.get("margin_of_safety_pct") or 0) < -15:
        cons.append("Market price is well above modelled intrinsic value.")
    mgmt = []
    if prof.get("insider_ownership_pct"):
        mgmt.append(f"Insiders hold {prof['insider_ownership_pct']:.1f}% — interests aligned with shareholders.")
    if (r.get("roe") or 0) > 12:
        mgmt.append("Track record: double-digit ROE suggests disciplined capital allocation.")
    if r.get("dividend_sustainable"):
        mgmt.append("Consistent, covered dividends signal shareholder-friendly payout policy.")
    mgmt.append(ci.MANAGEMENT_NOTES["default"])
    out = {"sector": sector, "industry_trend": trend, "sector_perf": sec_perf,
           "management": mgmt, "pros": pros[:8], "cons": cons[:8],
           "business": prof.get("business"), "moat": prof.get("moat"),
           "customers": prof.get("customers")}
    _store("intel", symbol, out)
    return out


def deep_pack(symbol):
    symbol = symbol.upper()
    return {"symbol": symbol,
            "profile": profile_pack(symbol),
            "statements": statements_pack(symbol),
            "ratios": ratios_pack(symbol),
            "peers": peers_pack(symbol),
            "valuation": valuation_pack(symbol),
            "intel": intel_pack(symbol),
            "generated_at": time.strftime("%Y-%m-%d %H:%M PKT")}


# ── background agents ──────────────────────────────────────────────────
def _warm(kind):
    fns = {"profile": profile_pack,
           "statements": lambda s: statements_pack(s, 0),
           "ratios": ratios_pack, "peers": lambda s: peers_pack(s, 0),
           "valuation": valuation_pack, "intel": intel_pack}

    def job():
        for sym in _watchlist_symbols():
            try:
                fns[kind](sym)
            except Exception:
                continue
    return job


_REGISTERED = False


def register_agents():
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True
    Agent("profile-agent", 24 * 3600, _warm("profile"), "company briefs")
    Agent("statements-agent", 12 * 3600, _warm("statements"), "3-statement trends")
    Agent("ratios-agent", 6 * 3600, _warm("ratios"), "P/E P/B ROE yield")
    Agent("peers-agent", 2 * 3600, _warm("peers"), "sector comparables")
    Agent("valuation-agent", 6 * 3600, _warm("valuation"), "DCF/DDM/relative")
    Agent("intel-agent", 12 * 3600, _warm("intel"), "moat/industry/pros-cons")
    start_agents()
