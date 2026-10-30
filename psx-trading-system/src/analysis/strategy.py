"""Trading Strategy — Trader agent + Deep Thinking + transaction proposal.

'Deep Thinking' here is a transparent rule-based reasoning engine (free,
offline). If the user enables Ollama in config, a local LLM narrative is
appended — never required.
"""
from datetime import date, timedelta

from ..data import appconfig as appcfg
from ..data import psx_client as psx
from . import indicators as ind
from . import llm as llmmod
from . import researcher as R

def _cfg() -> dict:
    return {"ollama": appcfg.get_ollama(), "settings": appcfg.get_settings()}


# ── Trader: multi-strategy vote ─────────────────────────────────────
def strategy_votes(df, snap: dict) -> list[dict]:
    t = ind.compute_all(df)
    votes = []

    def vote(name, signal, strength, note):
        votes.append({"strategy": name, "signal": signal,
                      "strength": strength, "note": note})

    # 1) SMA trend (10/50)
    if snap.get("above_sma50") and _gt(t, "sma10", "sma50"):
        vote("SMA trend", "buy", 0.8, "Price > 50DMA and 10DMA > 50DMA")
    elif not snap.get("above_sma50") and not _gt(t, "sma10", "sma50"):
        vote("SMA trend", "sell", 0.8, "Price < 50DMA and 10DMA < 50DMA")
    else:
        vote("SMA trend", "neutral", 0.3, "Moving averages mixed")

    # 2) RSI regime
    rsi = _num(snap.get("rsi14"), 50)
    if rsi < 30:
        vote("RSI mean-reversion", "buy", 0.7, f"RSI {rsi:.0f} oversold — bounce setup")
    elif rsi > 70:
        vote("RSI mean-reversion", "sell", 0.7, f"RSI {rsi:.0f} overbought — fade setup")
    elif rsi > 55:
        vote("RSI momentum", "buy", 0.5, f"RSI {rsi:.0f} bullish regime")
    elif rsi < 45:
        vote("RSI momentum", "sell", 0.5, f"RSI {rsi:.0f} bearish regime")
    else:
        vote("RSI", "neutral", 0.2, f"RSI {rsi:.0f} neutral zone")

    # 3) MACD
    if snap.get("macd_cross_up"):
        vote("MACD", "buy", 0.8, "Fresh bullish MACD crossover")
    elif snap.get("macd_cross_down"):
        vote("MACD", "sell", 0.8, "Fresh bearish MACD crossover")
    elif snap.get("macd_bull"):
        vote("MACD", "buy", 0.4, "MACD above signal (no fresh cross)")
    else:
        vote("MACD", "sell", 0.4, "MACD below signal (no fresh cross)")

    # 4) Breakout
    if snap.get("breakout_20d"):
        vote("Donchian breakout", "buy", 0.75, "20-day high breakout")
    elif snap.get("breakdown_20d"):
        vote("Donchian breakout", "sell", 0.75, "20-day low breakdown")
    else:
        vote("Donchian breakout", "neutral", 0.2, "Inside 20-day range")

    # 5) Bollinger position
    c, up, lo = (_num(snap.get("close")), _num(snap.get("bb_up")),
                 _num(snap.get("bb_lo")))
    if c and up and c >= up:
        vote("Bollinger", "sell", 0.45, "Tagging upper band — stretched")
    elif c and lo and c <= lo:
        vote("Bollinger", "buy", 0.45, "Tagging lower band — washed out")
    else:
        vote("Bollinger", "neutral", 0.2, "Inside Bollinger bands")

    # 6) Volume thrust
    vr, roc12 = _num(snap.get("vol_ratio"), 1), _num(snap.get("roc12"))
    if vr >= 2 and roc12 > 0:
        vote("Volume thrust", "buy", 0.7, f"Volume {vr:.1f}× on up-move")
    elif vr >= 2 and roc12 < 0:
        vote("Volume thrust", "sell", 0.7, f"Volume {vr:.1f}× on down-move")
    return votes


def _num(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _gt(t, a: str, b: str) -> bool:
    try:
        return bool(t[a].iloc[-1] > t[b].iloc[-1])
    except Exception:
        return False


def trader_action(votes: list[dict], net_score: float) -> dict:
    w = {"buy": 1, "neutral": 0, "sell": -1}
    tech = sum(w[v["signal"]] * v["strength"] for v in votes)
    tech_n = max(-1, min(1, tech / 3))
    fund_n = (net_score - 50) / 50  # -1..1
    combined = round(0.55 * tech_n + 0.45 * fund_n, 3)
    if combined >= 0.45:
        action = "BUY"
    elif combined >= 0.15:
        action = "ACCUMULATE"
    elif combined <= -0.45:
        action = "SELL"
    elif combined <= -0.15:
        action = "REDUCE"
    else:
        action = "HOLD"
    return {"action": action, "score": combined,
            "technical_bias": round(tech_n, 3), "research_bias": round(fund_n, 3)}


# ── Deep Thinking (rule-based reasoning trace) ──────────────────────
def deep_think(symbol: str, report: dict, votes: list[dict], trader: dict) -> dict:
    snap = report["snapshot"]
    steps = [
        f"1. REGIME CHECK — {symbol} closed Rs{snap.get('close')} on {snap.get('date')}. "
        f"Trend frame: {'above' if snap.get('above_sma50') else 'below'} 50DMA, "
        f"{'above' if snap.get('above_sma200') else 'below'} 200DMA; "
        f"RSI {snap.get('rsi14')}, MACD {'bullish' if snap.get('macd_bull') else 'bearish'}.",
        f"2. DEBATE RESULT — bulls {report['discussion']['bull_score']} vs "
        f"bears {report['discussion']['bear_score']} → net {report['discussion']['net_score']} "
        f"({report['discussion']['verdict']}). {report['discussion']['summary']}",
        "3. STRATEGY VOTES — " + "; ".join(
            f"{v['strategy']}: {v['signal'].upper()} ({v['note']})" for v in votes) + ".",
        f"4. RISK CONTEXT — ATR Rs{snap.get('atr14')} ({snap.get('atr_pct')}% of price); "
        f"support Rs{snap.get('support_1')}/{snap.get('support_2')}, "
        f"resistance Rs{snap.get('resistance_1')}/{snap.get('resistance_2')}. "
        f"{report['risk_reward']['assessment']}.",
        f"5. NEWS LAYER — sentiment {report['news_sentiment']['label']} "
        f"(score {report['news_sentiment']['score']}, n={report['news_sentiment']['count']}).",
        f"6. DECISION — trader blends technical bias {trader['technical_bias']} with "
        f"research bias {trader['research_bias']} → combined {trader['score']} ⇒ {trader['action']}. "
        f"Size by risk, honor the stop, scale at targets.",
    ]
    llm_note = None
    engine = "rule-based deep reasoning"
    if appcfg.get_ollama().get("enabled"):
        llm_note = llmmod.narrative(symbol, report, votes, trader)
        if llm_note:
            L = appcfg.get_llm()
            prov = (L.get("provider") or "ollama").lower()
            model = (appcfg.get_ollama().get("model", "") if prov == "ollama"
                     else (L.get(prov) or {}).get("model", ""))
            engine += f" + {prov}:{model}"
    return {"steps": steps, "llm_narrative": llm_note, "engine": engine}


# ── Transaction proposal ────────────────────────────────────────────
def build_proposal(symbol: str, company: str = "", capital: float = 1000000,
                   risk_pct: float = 1.0) -> dict:
    symbol = symbol.upper().strip()
    report = R.full_report(symbol, company)
    if "error" in report:
        return report
    df = psx.get_history(symbol)
    snap = report["snapshot"]
    votes = strategy_votes(df, snap)
    trader = trader_action(votes, report["discussion"]["net_score"])
    think = deep_think(symbol, report, votes, trader)

    rr = report["risk_reward"]
    entry = rr["entry_ref"]
    risk_rs = capital * risk_pct / 100
    per_share = max(entry - rr["stop"], 0.01)
    qty = max(int(risk_rs // per_share), 0)
    cost = round(qty * entry, 2)

    buy_evidence = ([f"{f['factor']}: {f['detail']}" for f in report["bullish"]["factors"]]
                    + [f"{v['strategy']}: {v['note']}" for v in votes if v["signal"] == "buy"])
    sell_evidence = ([f"{f['factor']}: {f['detail']}" for f in report["bearish"]["factors"]]
                     + [f"{v['strategy']}: {v['note']}" for v in votes if v["signal"] == "sell"])
    return {
        "symbol": symbol, "company": company, "as_of": snap.get("date"),
        "verdict": report["discussion"]["verdict"],
        "confidence": report["discussion"]["confidence"],
        "trader": trader, "votes": votes,
        "buy_evidence": buy_evidence[:12], "sell_evidence": sell_evidence[:12],
        "deep_thinking": think,
        "proposal": {
            "action": trader["action"],
            "entry_range": [round(entry * 0.995, 2), round(entry * 1.005, 2)],
            "stop_loss": rr["stop"], "target_1": rr["target_1"], "target_2": rr["target_2"],
            "reward_risk_t1": rr["reward_risk_t1"], "reward_risk_t2": rr["reward_risk_t2"],
            "suggested_qty": qty, "est_cost_rs": cost,
            "risk_rs": round(min(qty * per_share, risk_rs), 2),
            "capital_assumed": capital, "risk_pct": risk_pct,
            "valid_until": str(date.today() + timedelta(days=int(appcfg.get_settings().get("proposal_valid_days", 5) or 5))),
            "timeframe": "swing (2–8 weeks)",
        },
        "risk_reward": rr,
        "disclaimer": "Paper-trading proposal for education, not financial advice.",
    }
