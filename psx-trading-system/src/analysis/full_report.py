"""A-to-Z single-stock executive report — one composer feeds screen + PDF."""
from datetime import date, timedelta, datetime, timezone

PKT = timezone(timedelta(hours=5))


def _now_pkt():
    return datetime.now(PKT).isoformat(timespec="seconds")

from ..backtest import engine as bt
from ..data import appconfig as appcfg
from ..data import fundamentals as fundmod
from ..data import news as newsmod
from ..data import psx_client as psx
from . import researcher as R
from . import strategy as strat


# ── tiny formatters ─────────────────────────────────────────────────
def _num(x, nd=2):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def _rs(x):
    v = _num(x)
    return f"Rs{v:,.2f}" if v is not None else "--"


def _pct(x, signed=True):
    v = _num(x)
    if v is None:
        return "--"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _x(x):
    v = _num(x)
    return f"{v}x" if v is not None else "--"


def _sent_label(s):
    if isinstance(s, dict):
        return str(s.get("label", s.get("sentiment", "neutral")))
    return str(s or "neutral")


# ── plain-English state readers ─────────────────────────────────────
def _rsi_state(rsi):
    r = _num(rsi)
    if r is None:
        return "unknown"
    if r < 30:
        return f"{r} — oversold (washed out, bounce possible)"
    if r < 45:
        return f"{r} — soft (sellers in charge)"
    if r <= 55:
        return f"{r} — neutral (no edge either way)"
    if r <= 70:
        return f"{r} — firm (buyers in charge)"
    return f"{r} — overbought (hot, chase with care)"


def _trend_line(s):
    a50, a200 = s.get("above_sma50"), s.get("above_sma200")
    px = _rs(s.get("close"))
    if a50 and a200:
        return f"{px} — above both 50-day and 200-day averages: healthy uptrend."
    if a50 and not a200:
        return f"{px} — above 50-day but below 200-day: rebound attempt, not yet a real uptrend."
    if a200 and not a50:
        return f"{px} — below 50-day but above 200-day: short-term weak, long-term uptrend alive."
    return f"{px} — below both averages: downtrend. Only bottom-fish with a strict stop."


def _vol_line(s):
    v = _num(s.get("vol_ratio"))
    if v is None:
        return "unknown"
    if v >= 1.5:
        return f"{v}x average — heavy interest, move means more."
    if v >= 1.1:
        return f"{v}x average — firm participation."
    if v >= 0.7:
        return f"{v}x average — normal."
    return f"{v}x average — quiet; breakouts on thin volume often fail."


def _thesis(sym, snap, disc, bull, bear, trader, prop, fund, mom20=None, mom60=None):
    """Executive bullets in plain English."""
    px = snap.get("close")
    out = [f"Verdict: {disc.get('verdict', '?')} "
           f"(confidence {disc.get('confidence', '?')}) — trader action: "
           f"{trader.get('action', '?')}. {_trend_line(snap)}"]
    out.append(f"Momentum: RSI {_rsi_state(snap.get('rsi14'))}; MACD "
               f"{'bullish (above signal)' if snap.get('macd_bull') else 'bearish (below signal)'}; "
               f"volume {_vol_line(snap)}")
    off = _num(snap.get("off_52w_high_pct"))
    off_txt = f"{abs(off):.1f}% below 52-week high of {_rs(snap.get('high_52w'))}" if off else "52-week range unknown"
    out.append(f"Position: {off_txt}; 20-day return {_pct(mom20)}, "
               f"60-day return {_pct(mom60)}.")
    bf = (bull.get("factors") or [{}])[0]
    rf = (bear.get("factors") or [{}])[0]
    out.append(f"Debate: bulls {bull.get('score', '?')} vs bears {bear.get('score', '?')} "
               f"(net {disc.get('net_score', '?')}). Strongest bull case: "
               f"{bf.get('factor', '?')} — {bf.get('detail', '')} Biggest risk: "
               f"{rf.get('factor', '?')} — {rf.get('detail', '')}")
    p = prop.get("proposal", {})
    out.append(f"Trade plan: buy zone {_rs((p.get('entry_range') or [None, None])[0])}–"
               f"{_rs((p.get('entry_range') or [None, None])[1])}, stop "
               f"{_rs(p.get('stop_loss'))}, targets {_rs(p.get('target_1'))} / "
               f"{_rs(p.get('target_2'))} (reward:risk {p.get('reward_risk_t1', '?')} / "
               f"{p.get('reward_risk_t2', '?')}). Size: {p.get('suggested_qty', 0):,} shares "
               f"≈ {_rs(p.get('est_cost_rs'))} = {_rs(p.get('risk_rs'))} risk "
               f"({p.get('risk_pct', '?')}% of { _rs(p.get('capital_assumed'))}).")
    flags = []
    if snap.get("death_cross"):
        flags.append("death cross on moving averages (bearish)")
    if snap.get("breakdown_20d"):
        flags.append("fresh 20-day breakdown (weakness)")
    if (_num(snap.get("rsi14")) or 50) > 70:
        flags.append("overbought RSI (don't chase)")
    if (_num(snap.get("atr_pct")) or 0) > 5:
        flags.append(f"high daily swing ({_num(snap.get('atr_pct'))}% ATR — use smaller size)")
    pe = _num((fund or {}).get("pe_ratio"))
    y = _num((fund or {}).get("dividend_yield"))
    val = []
    if pe is not None:
        val.append(f"P/E {pe}x ({'cheap' if pe < 8 else 'fair' if pe < 15 else 'pricey'})")
    if y:
        val.append(f"yield {y}%")
    out.append("Red flags: " + ("; ".join(flags) if flags else "none screaming — "
               "normal swing risk only.") + (f" Value: {', '.join(val)}." if val else ""))
    return out


def _backtest_block(sym, s):
    try:
        start = str(date.today() - timedelta(days=3 * 365))
        r = bt.run(sym, "rsi_meanrev", start, None,
                   float(s.get("paper_cash", 1000000)),
                   float(s.get("commission_pct", 0.15)),
                   float(s.get("slippage_pct", 0.10)),
                   True, 2.0, 0.0, None)
        m = r["metrics"]
        beat = "beat" if m["total_return_pct"] >= m["buy_hold_pct"] else "lagged"
        line = (f"RSI mean-reversion from {r['window']['start']} to {r['window']['end']}: "
                f"{m['total_return_pct']:+.1f}% total ({beat} buy-and-hold "
                f"{m['buy_hold_pct']:+.1f}%), {m['trades']} trades, win rate "
                f"{m['win_rate_pct']}%, max fall {m['max_drawdown_pct']}%.")
        return {"strategy": r["strategy_name"], "window": r["window"],
                "metrics": m, "line": line}
    except Exception as e:
        return {"error": str(e)[:200]}


def _fund_rows(fund, snap=None):
    """ALL fundamental data, grouped. `fund` is fundamentals.get_fundamentals()
    output (snapshot row + quote + history stats + yfinance + DPS tables)."""
    f = fund or {}
    yf = f.get("yfinance") or {}
    hs = f.get("history_stats") or {}
    q = f.get("quote") or {}
    rows: list = []

    def hdr(t):
        rows.append((f"--- {t} ---", ""))

    def add(label, v, fmt=None):
        if v is None or v == "" or v != v:  # NaN check
            return
        rows.append((label, fmt(v) if fmt else str(v)))

    hdr("MARKET")
    add("Price (last close)", f.get("price") or hs.get("last_close"), _rs)
    add("Day change", f.get("change_pct"), _pct)
    add("Market cap", f.get("market_cap"), _rs)
    add("Market cap (Yahoo)", yf.get("marketCap"),
        lambda v: f"Rs {float(v) / 1e9:.1f} bn" if v else None)
    add("Enterprise value", yf.get("enterpriseValue"),
        lambda v: f"Rs {float(v) / 1e9:.1f} bn" if v else None)
    add("Sector", f.get("sector_name"))
    add("Shares outstanding", yf.get("sharesOutstanding"),
        lambda v: f"{float(v) / 1e6:,.1f} million" if v else None)
    add("Free float", yf.get("floatShares"),
        lambda v: f"{float(v) / 1e6:,.1f} million" if v else None)
    add("Insider holding", yf.get("heldPercentInsiders"),
        lambda v: f"{float(v) * 100:.1f}%" if v is not None else None)
    add("Institutional holding", yf.get("heldPercentInstitutions"),
        lambda v: f"{float(v) * 100:.1f}%" if v is not None else None)
    add("Beta", f.get("beta") or yf.get("beta"), _x)

    hdr("VALUATION")
    add("P/E (trailing)", f.get("pe_ratio") or yf.get("trailingPE"), _x)
    add("P/E (forward)", yf.get("forwardPE"), _x)
    add("Price / book", yf.get("priceToBook"), _x)
    add("Price / sales", yf.get("priceToSalesTrailing12Months"), _x)
    add("Dividend yield", f.get("dividend_yield") or yf.get("dividendYield"),
        lambda v: _pct(v, signed=False))
    add("Dividend rate", yf.get("dividendRate"), lambda v: f"Rs {float(v):.2f}" if v else None)
    add("Payout ratio", yf.get("payoutRatio"),
        lambda v: f"{float(v) * 100:.0f}%" if v is not None else None)
    exd = yf.get("exDividendDate")
    if exd:
        try:
            from datetime import datetime as _dt
            add("Ex-dividend date", _dt.utcfromtimestamp(float(exd)).strftime("%d %b %Y"))
        except Exception:
            pass

    hdr("PROFITABILITY")
    add("ROE", f.get("roe") or yf.get("returnOnEquity"),
        lambda v: _pct(float(v) * 100 if abs(float(v)) <= 3 else v, signed=False))
    add("ROA", yf.get("returnOnAssets"),
        lambda v: _pct(float(v) * 100, signed=False))
    add("Net profit margin", f.get("profit_margin") or yf.get("profitMargins"),
        lambda v: _pct(float(v) * 100 if abs(float(v)) <= 3 else v, signed=False))
    add("Operating margin", yf.get("operatingMargins"),
        lambda v: _pct(float(v) * 100, signed=False))
    add("Gross margin", yf.get("grossMargins"),
        lambda v: _pct(float(v) * 100, signed=False))

    hdr("GROWTH")
    add("Revenue growth", f.get("revenue_growth") or yf.get("revenueGrowth"),
        lambda v: _pct(float(v) * 100 if abs(float(v)) <= 5 else v))
    add("Earnings growth", f.get("earnings_growth") or yf.get("earningsGrowth"),
        lambda v: _pct(float(v) * 100 if abs(float(v)) <= 5 else v))
    add("Quarterly earnings growth", yf.get("earningsQuarterlyGrowth"),
        lambda v: _pct(float(v) * 100))

    hdr("FINANCIAL HEALTH")
    add("Debt / equity", f.get("debt_equity") or yf.get("debtToEquity"), _x)
    add("Current ratio", yf.get("currentRatio"), _x)
    add("Quick ratio", yf.get("quickRatio"), _x)
    add("Total cash", yf.get("totalCash"),
        lambda v: f"Rs {float(v) / 1e9:.2f} bn" if v else None)
    add("Total debt", yf.get("totalDebt"),
        lambda v: f"Rs {float(v) / 1e9:.2f} bn" if v else None)
    add("EBITDA", yf.get("ebitda"), lambda v: f"Rs {float(v) / 1e9:.2f} bn" if v else None)
    add("Total revenue (ttm)", yf.get("totalRevenue"),
        lambda v: f"Rs {float(v) / 1e9:.2f} bn" if v else None)
    add("Operating cash flow", yf.get("operatingCashflow"),
        lambda v: f"Rs {float(v) / 1e9:.2f} bn" if v else None)
    add("Free cash flow", f.get("free_cash_flow") or yf.get("freeCashflow"),
        lambda v: _rs(v) if not isinstance(v, (int, float)) else f"Rs {float(v) / 1e9:.2f} bn")

    hdr("PER SHARE")
    add("EPS (ttm)", yf.get("trailingEps"), lambda v: f"Rs {float(v):.2f}" if v else None)
    add("EPS (forward)", yf.get("forwardEps"), lambda v: f"Rs {float(v):.2f}" if v else None)
    add("Revenue / share", yf.get("revenuePerShare"),
        lambda v: f"Rs {float(v):.2f}" if v else None)
    add("Book value / share", yf.get("bookValue"), lambda v: f"Rs {float(v):.2f}" if v else None)

    hdr("PRICE HISTORY")
    add("52-week high", hs.get("high_52w"), _rs)
    add("52-week low", hs.get("low_52w"), _rs)
    add("Off 52-week high", hs.get("off_high_pct"), _pct)
    add("1-month return", hs.get("perf_1m"), _pct)
    add("3-month return", hs.get("perf_3m"), _pct)
    add("6-month return", hs.get("perf_6m"), _pct)
    add("1-year return", hs.get("perf_1y"), _pct)
    add("52-week change (Yahoo)", yf.get("52WeekChange"),
        lambda v: _pct(float(v) * 100))

    hdr("ANALYSTS (Yahoo)")
    add("Recommendation", yf.get("recommendationKey"))
    add("Analysts covering", yf.get("numberOfAnalystOpinions"))
    add("Target mean / high / low", None if not yf.get("targetMeanPrice") else
        f"Rs {_num(yf.get('targetMeanPrice'))} (Rs {_num(yf.get('targetLowPrice'))} - "
        f"Rs {_num(yf.get('targetHighPrice'))})")

    hdr("LISTING & DPS QUOTE")
    add("Index membership", q.get("listed_in"))
    add("Free float", q.get("free_float"))
    add("Avg volume (30d)", q.get("volume_avg_30d"),
        lambda v: f"{float(v):,.0f}" if v else None)
    add("1-year change (DPS)", q.get("change_1y_pct"), _pct)

    hdr("DPS ANNUAL STATEMENTS (latest 3 years)")
    for rec in (f.get("dps_tables") or {}).get("annual", [])[:12]:
        vals = [str(v) for k, v in rec.items() if k != "metric"]
        vals = [v for v in vals if v and str(v) not in ("nan", "None")]
        if rec.get("metric") and vals:
            rows.append((str(rec["metric"]), " | ".join(vals[:3])))
    hdr("DPS QUARTERLY STATEMENTS (latest)")
    for rec in (f.get("dps_tables") or {}).get("quarterly", [])[:12]:
        vals = [str(v) for k, v in rec.items() if k != "metric"]
        vals = [v for v in vals if v and str(v) not in ("nan", "None")]
        if rec.get("metric") and vals:
            rows.append((str(rec["metric"]), " | ".join(vals[:3])))

    srcs = f.get("sources") or []
    if srcs:
        rows.append(("Data sources", ", ".join(srcs)))
    note = f.get("source_note") or f.get("note")
    if note:
        rows.append(("Source note", str(note)[:300]))
    return rows


def _fund_charts(fund, snap=None):
    """Chart-ready numbers for the report's fundamentals view."""
    f = fund or {}
    hs = f.get("history_stats") or {}
    yf = f.get("yfinance") or {}

    def fpct(v):
        try:
            v = float(v)
            return v * 100 if abs(v) <= 3 else v
        except Exception:
            return None

    perf = [(k, hs.get(v)) for k, v in (("1M", "perf_1m"), ("3M", "perf_3m"),
                                         ("6M", "perf_6m"), ("1Y", "perf_1y"))]
    ratios = []
    for label, val in (("P/E", f.get("pe_ratio") or yf.get("trailingPE")),
                       ("Yield %", f.get("dividend_yield")),
                       ("ROE %", fpct(f.get("roe") or yf.get("returnOnEquity"))),
                       ("Margin %", fpct(f.get("profit_margin") or yf.get("profitMargins"))),
                       ("D/E", f.get("debt_equity") or yf.get("debtToEquity"))):
        try:
            ratios.append((label, round(float(val), 2)))
        except Exception:
            pass
    return {"performance": [{"label": k, "value": v} for k, v in perf if v is not None],
            "ratios": [{"label": k, "value": v} for k, v in ratios],
            "range52": {"low": hs.get("low_52w"), "high": hs.get("high_52w"),
                        "now": hs.get("last_close") or (snap or {}).get("close")}}


def build_full_report(symbol: str, company: str = "") -> dict:
    """Compose the full A-to-Z report. Single AI call max (inside proposal)."""
    sym = str(symbol).upper().strip()
    w = next((x for x in (appcfg.get_watchlist() or [])
              if str(x.get("symbol", "")).upper() == sym), {})
    company = company or w.get("name", sym)
    sector = w.get("sector", "")
    s = appcfg.get_settings() or {}
    capital = float(s.get("paper_cash", 1000000) or 1000000)
    risk_pct = float(s.get("default_risk_pct", 1.0) or 1.0)

    prop = strat.build_proposal(sym, company, capital, risk_pct)
    if "error" in prop:
        return {"symbol": sym, "company": company, "error": prop["error"]}
    rep = R.full_report(sym, company)
    snap = rep.get("snapshot", {}) or {}
    try:
        _h = psx.get_history(sym)["close"].astype(float)
        mom20 = round((_h.iloc[-1] / _h.iloc[-21] - 1) * 100, 2) if len(_h) > 21 else None
        mom60 = round((_h.iloc[-1] / _h.iloc[-61] - 1) * 100, 2) if len(_h) > 61 else None
    except Exception:
        mom20 = mom60 = None
    disc = rep.get("discussion", {}) or {}
    bull = rep.get("bullish", {}) or {}
    bear = rep.get("bearish", {}) or {}
    rr = rep.get("risk_reward", {}) or {}

    try:
        fund = fundmod.get_fundamentals(sym, company)
    except Exception as e:
        fund = {"error": str(e)[:200]}
    try:
        news = newsmod.get_stock_news(sym, company, 8)
    except Exception:
        news = []

    news_rows = [{"title": n.get("title", ""), "source": n.get("source", ""),
                 "published": str(n.get("published", ""))[:16],
                 "sentiment": _sent_label(n.get("sentiment")),
                 "summary": (n.get("summary", "") or "")[:220],
                 "link": n.get("link", "")} for n in (news or [])[:8]]

    key_stats = [("Price", _rs(snap.get("close"))),
                 ("Day change", _pct((fund or {}).get("change_pct"))),
                 ("Verdict", f"{disc.get('verdict', '?')} ({disc.get('confidence', '?')} confidence)"),
                 ("Trader action", trader_action(prop)),
                 ("RSI (14)", str(_num(snap.get("rsi14")) or "--")),
                 ("Trend", "Uptrend" if snap.get("above_sma200") else "Downtrend"),
                 ("52-week high / low", f"{_rs(snap.get('high_52w'))} / {_rs(snap.get('low_52w'))}"),
                 ("P/E", _x((fund or {}).get("pe_ratio"))),
                 ("Dividend yield", _pct((fund or {}).get("dividend_yield"), signed=False)),
                 ("Reward : risk (T1)", str(rr.get("reward_risk_t1", "--")))]

    price_rows = [("Last close", f"{_rs(snap.get('close'))} on {snap.get('date', '?')}"),
                  ("Trend frame", _trend_line(snap)),
                  ("20-day avg", _rs(snap.get("sma20"))),
                  ("50-day avg", _rs(snap.get("sma50"))),
                  ("200-day avg", _rs(snap.get("sma200"))),
                  ("Golden / death cross", ("Golden cross (bullish)" if snap.get("golden_cross")
                                             else "Death cross (bearish)" if snap.get("death_cross")
                                             else "None recently")),
                  ("52-week high / low", f"{_rs(snap.get('high_52w'))} / {_rs(snap.get('low_52w'))}"),
                  ("Distance from 52w high", _pct(snap.get("off_52w_high_pct"))),
                  ("Support 1 / 2", f"{_rs(snap.get('support_1'))} / {_rs(snap.get('support_2'))}"),
                  ("Resistance 1 / 2", f"{_rs(snap.get('resistance_1'))} / {_rs(snap.get('resistance_2'))}"),
                  ("Daily swing (ATR)", f"{_rs(snap.get('atr14'))} ({_pct(snap.get('atr_pct'), signed=False)} of price)")]

    bb_txt = "unknown"
    c, up, lo = _num(snap.get("close")), _num(snap.get("bb_up")), _num(snap.get("bb_lo"))
    if c and up and lo and up > lo:
        pos = (c - lo) / (up - lo)
        bb_txt = ("near upper band (hot)" if pos > 0.8 else "near lower band (cold)"
                  if pos < 0.2 else "mid-band (neutral)")
    tech_rows = [("RSI (14)", _rsi_state(snap.get("rsi14"))),
                 ("MACD", f"{'bullish' if snap.get('macd_bull') else 'bearish'}"
                           f"{' — fresh buy cross' if snap.get('macd_cross_up') else ''}"
                           f"{' — fresh sell cross' if snap.get('macd_cross_down') else ''}"),
                 ("Stochastic", f"K {_num(snap.get('stoch_k'))} / D {_num(snap.get('stoch_d'))}"),
                 ("Bollinger position", bb_txt),
                 ("Volume vs average", _vol_line(snap)),
                 ("20-day return", _pct(mom20)),
                 ("60-day return", _pct(mom60)),
                 ("20-day breakout / breakdown", ("Breakout (strength)" if snap.get("breakout_20d")
                                                  else "Breakdown (weakness)" if snap.get("breakdown_20d")
                                                  else "Inside range"))]

    return {
        "symbol": sym, "company": company, "sector": sector,
        "as_of": snap.get("date"), "generated_at": _now_pkt(),
        "key_stats": key_stats,
        "executive": {"verdict": disc.get("verdict"), "confidence": disc.get("confidence"),
                      "action": trader_action(prop),
                      "thesis": _thesis(sym, snap, disc, bull, bear, prop.get("trader", {}), prop, fund, mom20, mom60)},
        "price_trend": price_rows,
        "technicals": tech_rows,
        "quant": {"trader": prop.get("trader"), "votes": prop.get("votes", [])},
        "debate": {"bull_score": bull.get("score"), "bear_score": bear.get("score"),
                   "net": disc.get("net_score"), "verdict": disc.get("verdict"),
                   "bull_factors": (bull.get("factors") or [])[:6],
                   "bear_factors": (bear.get("factors") or [])[:6]},
        "trade_plan": {"proposal": prop.get("proposal"), "supports": [snap.get("support_1"), snap.get("support_2")],
                       "resistances": [snap.get("resistance_1"), snap.get("resistance_2")],
                       "assessment": rr.get("assessment", "")},
        "fundamentals": _fund_rows(fund, snap),
        "fund_charts": _fund_charts(fund, snap),
        "news": news_rows,
        "backtest": _backtest_block(sym, s),
        "deep_thinking": prop.get("deep_thinking", {}),
        "disclaimer": prop.get("disclaimer", "For education, not financial advice."),
    }


def trader_action(prop: dict) -> str:
    t = prop.get("trader", {}) if isinstance(prop, dict) else {}
    return str(t.get("action", "?"))
