"""Researcher Team — Bullish analyst, Bearish analyst, internal discussion,
and risk/reward evaluation.

Rule-based and fully offline (works on any laptop). Each analyst scores
0–100 from weighted evidence; the discussion reconciles them into one
verdict. An optional local Ollama model can add narrative (see strategy).
"""
from ..data import news as news_mod
from ..data import psx_client as psx
from ..data import sentiment as sent
from . import indicators as ind


def _safe(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ── Bullish analyst ─────────────────────────────────────────────────
def bullish_case(symbol: str, snap: dict, fund: dict, news_sent: dict) -> dict:
    pts, factors = 50.0, []

    def add(name, detail, delta):
        nonlocal pts
        pts += delta
        factors.append({"factor": name, "detail": detail,
                        "points": round(delta, 1)})

    rsi = _safe(snap.get("rsi14"), 50)
    if snap.get("above_sma50") and snap.get("above_sma200"):
        add("Uptrend structure", "Price above 50-day and 200-day averages", 9)
    elif snap.get("above_sma50"):
        add("Short-term uptrend", "Price above 50-day average", 4)
    if snap.get("golden_cross"):
        add("Golden cross", "50-day average just crossed above 200-day", 7)
    if snap.get("macd_bull"):
        add("MACD bullish", "MACD line above signal line", 4)
    if snap.get("macd_cross_up"):
        add("MACD cross up", "Fresh bullish MACD crossover", 4)
    if snap.get("breakout_20d"):
        add("20-day breakout", "Close at/above 20-day Donchian high", 6)
    if 50 <= rsi <= 70:
        add("Healthy momentum", f"RSI {rsi:.0f} — strong without overheating", 4)
    elif 30 <= rsi < 45:
        add("Mean-reversion setup", f"RSI {rsi:.0f} — washed out, bounce odds up", 3)
    vr = _safe(snap.get("vol_ratio"), 1)
    if vr >= 1.5 and _safe(snap.get("roc12")) > 0:
        add("Volume confirmation", f"Volume {vr:.1f}× average on rising price", 5)
    if _safe(snap.get("stoch_k"), 50) < 25 and _safe(snap.get("stoch_d"), 50) < 25:
        add("Oversold stochastic", "Stochastic deeply oversold — snap-back fuel", 3)
    stats = fund.get("history_stats", {}) or {}
    if _safe(stats.get("perf_3m")) and stats["perf_3m"] > 10:
        add("Quarterly momentum", f"+{stats['perf_3m']:.1f}% over 3 months", 4)
    pe = _safe(fund.get("pe_ratio"))
    if 0 < pe < 12:
        add("Cheap valuation", f"P/E {pe:.1f}× — value cushion", 5)
    elif 0 < pe < 20:
        add("Fair valuation", f"P/E {pe:.1f}× — not demanding", 2)
    dy = _safe(fund.get("dividend_yield"))
    if dy >= 7:
        add("High dividend shield", f"{dy:.1f}% yield pays you to wait", 4)
    elif dy >= 3:
        add("Dividend support", f"{dy:.1f}% yield underpins downside", 2)
    ns = _safe(news_sent.get("score"))
    if ns > 0.07:
        add("Positive news flow", f"News sentiment {news_sent.get('label')} "
            f"({news_sent.get('positive', 0)} positive items)", 4)
    return {"score": round(max(0, min(100, pts)), 1), "factors": factors}


# ── Bearish analyst ─────────────────────────────────────────────────
def bearish_case(symbol: str, snap: dict, fund: dict, news_sent: dict) -> dict:
    pts, factors = 50.0, []

    def add(name, detail, delta):
        nonlocal pts
        pts += delta
        factors.append({"factor": name, "detail": detail,
                        "points": round(delta, 1)})

    rsi = _safe(snap.get("rsi14"), 50)
    if not snap.get("above_sma50") and not snap.get("above_sma200"):
        add("Downtrend structure", "Price below 50-day and 200-day averages", 9)
    elif not snap.get("above_sma50"):
        add("Weak short trend", "Price below 50-day average", 4)
    if snap.get("death_cross"):
        add("Death cross", "50-day average just crossed below 200-day", 7)
    if not snap.get("macd_bull"):
        add("MACD bearish", "MACD line below signal line", 4)
    if snap.get("macd_cross_down"):
        add("MACD cross down", "Fresh bearish MACD crossover", 4)
    if snap.get("breakdown_20d"):
        add("20-day breakdown", "Close at/below 20-day Donchian low", 6)
    if rsi >= 70:
        add("Overbought RSI", f"RSI {rsi:.0f} — exhaustion/pullback risk", 5)
    elif 55 < rsi < 65 and _safe(snap.get("roc12")) < 0:
        add("Fading momentum", f"RSI {rsi:.0f} but 12-day ROC negative", 3)
    vr = _safe(snap.get("vol_ratio"), 1)
    if vr >= 1.5 and _safe(snap.get("roc12")) < 0:
        add("Distribution volume", f"Volume {vr:.1f}× average on falling price", 5)
    if _safe(snap.get("stoch_k"), 50) > 75:
        add("Overbought stochastic", "Stochastic toppy — pullback fuel", 3)
    off = _safe(snap.get("off_52w_high_pct"))
    if off > -3:
        add("At 52-week highs", "No overhead supply, but chase risk is high", 2)
    stats = fund.get("history_stats", {}) or {}
    if _safe(stats.get("perf_3m")) and stats["perf_3m"] < -10:
        add("Negative momentum", f"{stats['perf_3m']:.1f}% over 3 months", 4)
    pe = _safe(fund.get("pe_ratio"))
    if pe >= 25:
        add("Rich valuation", f"P/E {pe:.1f}× — priced for perfection", 5)
    elif pe > 18:
        add("Full valuation", f"P/E {pe:.1f}× — limited margin of safety", 2)
    if _safe(fund.get("dividend_yield")) == 0:
        add("No dividend cushion", "Zero yield — price must do all the work", 2)
    ns = _safe(news_sent.get("score"))
    if ns < -0.07:
        add("Negative news flow", f"News sentiment {news_sent.get('label')} "
            f"({news_sent.get('negative', 0)} negative items)", 4)
    atrp = _safe(snap.get("atr_pct"))
    if atrp > 4:
        add("High volatility", f"ATR {atrp:.1f}% of price — wider stops needed", 2)
    return {"score": round(max(0, min(100, pts)), 1), "factors": factors}


# ── Internal discussion + verdict ───────────────────────────────────
def _verdict(score: float) -> tuple[str, str]:
    if score >= 75:
        return "STRONG BUY", "Evidence heavily favors upside."
    if score >= 60:
        return "BUY", "Evidence favors upside."
    if score > 45:
        return "HOLD", "Bull and bear cases roughly balanced."
    if score > 30:
        return "SELL", "Evidence favors downside."
    return "STRONG SELL", "Evidence heavily favors downside."


def internal_discussion(bull: dict, bear: dict) -> dict:
    b, s = bull["score"], bear["score"]
    net = round((b - s) / 2 + 50, 1)  # reconcile to 0–100
    net = max(0, min(100, net))
    spread = abs(b - s)
    if spread < 8:
        tone = ("Team is split — both cases carry weight. Default posture is "
                "caution: smaller size, wait for confirmation.")
    elif b > s:
        tone = ("Bulls won the debate by "
                f"{spread:.0f} points — upside scenario is better supported.")
    else:
        tone = ("Bears won the debate by "
                f"{spread:.0f} points — downside risks dominate the tape.")
    verdict, why = _verdict(net)
    confidence = round(min(95, 30 + abs(net - 50) * 1.2 + min(len(bull["factors"]) + len(bear["factors"]), 10)), 1)
    return {"net_score": net, "verdict": verdict, "verdict_note": why,
            "confidence": confidence, "summary": tone,
            "bull_score": b, "bear_score": s}


def evaluate_risk_reward(snap: dict, circuit_pct: float = 7.5) -> dict:
    close = _safe(snap.get("close"))
    atr = _safe(snap.get("atr14")) or close * 0.02
    s1 = _safe(snap.get("support_1")) or (close - 1.2 * atr)
    r1 = _safe(snap.get("resistance_1")) or (close + 1.5 * atr)
    r2 = _safe(snap.get("resistance_2")) or (close + 2.5 * atr)
    stop = round(min(s1, close - 1.0 * atr), 2)
    t1 = round(max(r1, close + 1.5 * atr), 2)
    t2 = round(max(r2, close + 2.5 * atr), 2)
    risk = max(close - stop, 0.01)
    rr1 = round((t1 - close) / risk, 2)
    rr2 = round((t2 - close) / risk, 2)
    day_band = round(close * circuit_pct / 100, 2)
    return {"entry_ref": round(close, 2), "atr": round(atr, 2),
            "stop": stop, "target_1": t1, "target_2": t2,
            "risk_per_share": round(risk, 2),
            "reward_risk_t1": rr1, "reward_risk_t2": rr2,
            "support_1": _safe(snap.get("support_1")), "support_2": _safe(snap.get("support_2")),
            "resistance_1": _safe(snap.get("resistance_1")), "resistance_2": _safe(snap.get("resistance_2")),
            "circuit_band_rs": day_band,
            "assessment": ("Favorable" if rr1 >= 1.5 else
                           "Fair" if rr1 >= 1.0 else "Poor") + f" — R:R {rr1}:1 to first target"}


# ── Full report ─────────────────────────────────────────────────────
def full_report(symbol: str, company: str = "") -> dict:
    symbol = symbol.upper().strip()
    df = psx.get_history(symbol)
    snap = ind.snapshot(df)
    if "error" in snap:
        return {"symbol": symbol, "error": snap["error"]}
    fund = __import__("src.data.fundamentals", fromlist=["get_fundamentals"]).get_fundamentals(symbol, company)
    items = news_mod.get_stock_news(symbol, company or fund.get("sector_name", ""))
    n_sent = sent.analyze_items(items)
    bull = bullish_case(symbol, snap, fund, n_sent)
    bear = bearish_case(symbol, snap, fund, n_sent)
    disc = internal_discussion(bull, bear)
    rr = evaluate_risk_reward(snap)
    return {"symbol": symbol, "company": company, "snapshot": snap,
            "fundamentals": {k: fund.get(k) for k in
                             ("price", "pe_ratio", "dividend_yield", "market_cap",
                              "change_pct", "change_1y_pct", "sector_name", "history_stats",
                              "yfinance", "sources")},
            "news_sentiment": n_sent,
            "news": items[:8],
            "bullish": bull, "bearish": bear, "discussion": disc,
            "risk_reward": rr}
