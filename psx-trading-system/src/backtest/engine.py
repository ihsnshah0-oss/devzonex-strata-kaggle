"""Backtesting engine — long-only daily-bar backtests with costs.

Strategies are pure functions: signal_bars(df, params) -> Series[bool] for
entries, plus optional exits. The runner handles ATR stops/targets,
commission + slippage, and full performance stats.
"""
import numpy as np
import pandas as pd

from ..analysis import indicators as ind
from ..data import psx_client as psx

# ── strategy signal functions (enter on next open) ──────────────────
def sig_sma_cross(df: pd.DataFrame, fast: int = 10, slow: int = 50) -> pd.Series:
    t = ind.compute_all(df)
    return (t["close"] > ind.sma(t["close"], slow)) & \
           (ind.sma(t["close"], fast) > ind.sma(t["close"], slow))


def sig_rsi_meanrev(df: pd.DataFrame, oversold: int = 30, overbought: int = 70) -> pd.Series:
    t = ind.compute_all(df)
    return t["rsi14"] < oversold


def sig_breakout(df: pd.DataFrame, window: int = 20, vol_mult: float = 1.2) -> pd.Series:
    t = ind.compute_all(df)
    hi = t["high"].rolling(window, min_periods=window).max().shift(1)
    return (t["close"] > hi) & (t["vol_ratio"].fillna(0) >= vol_mult)


def sig_momentum(df: pd.DataFrame, roc_n: int = 63, min_roc: float = 5.0) -> pd.Series:
    t = ind.compute_all(df)
    return (t["close"].pct_change(roc_n) * 100 > min_roc) & (t["close"] > t["sma50"])


def sig_macd(df: pd.DataFrame) -> pd.Series:
    t = ind.compute_all(df)
    m, s, _ = ind.macd(t["close"])
    return m > s


def sig_stage2(df: pd.DataFrame, lookback_w: int = 52, vol_mult: float = 1.3) -> pd.Series:
    """Stage 2 breakout: weekly close at a new N-week high on >= vol_mult x
    average weekly volume (Weinstein-style). Mapped back to daily bars."""
    wk = df.set_index("date").resample("W-FRI").agg(
        {"close": "last", "volume": "sum"}).dropna(subset=["close"])
    hi = wk["close"].shift(1).rolling(lookback_w, min_periods=lookback_w).max()
    vavg = wk["volume"].shift(1).rolling(10).mean()
    brk = (wk["close"] > hi) & (wk["volume"] > vol_mult * vavg)
    brk_d = brk.reindex(df.set_index("date").index, method="ffill").astype("boolean").shift(1)
    brk_d = brk_d.fillna(False).astype(bool).reset_index(drop=True)
    # rising edge only: one entry per breakout week (matches the verified playbook —
    # no re-entering the same week right after a stop-out)
    prev = brk_d.astype("boolean").shift(1).fillna(False).astype(bool)
    return brk_d & ~prev


def _stage2_weekly_below_sma(df: pd.DataFrame, sma_w: int = 30) -> np.ndarray:
    """Daily-mapped flag: last completed week closed below its N-week SMA."""
    wk = df.set_index("date").resample("W-FRI").agg({"close": "last"}).dropna(subset=["close"])
    below = wk["close"] < wk["close"].rolling(sma_w, min_periods=sma_w).mean()
    d = below.reindex(df.set_index("date").index, method="ffill").astype("boolean").shift(1)
    return d.fillna(False).astype(bool).reset_index(drop=True).values


STRATEGIES = {
    "sma_cross": {"fn": sig_sma_cross, "name": "SMA Trend (10/50)",
                  "desc": "Buy when price and fast SMA are above slow SMA.",
                  "params": {"fast": 10, "slow": 50}},
    "rsi_meanrev": {"fn": sig_rsi_meanrev, "name": "RSI Mean-Reversion",
                    "desc": "Buy oversold (RSI<30), exit at RSI>55.",
                    "params": {"oversold": 30, "overbought": 70}},
    "breakout": {"fn": sig_breakout, "name": "Donchian Breakout",
                 "desc": "Buy 20-day high breakouts on rising volume.",
                 "params": {"window": 20, "vol_mult": 1.2}},
    "momentum": {"fn": sig_momentum, "name": "Quarterly Momentum",
                 "desc": "Buy 3-month winners still above 50DMA.",
                 "params": {"roc_n": 63, "min_roc": 5.0}},
    "macd": {"fn": sig_macd, "name": "MACD Bull",
             "desc": "Long while MACD line is above signal.",
             "params": {}},
    "stage2_breakout": {"fn": sig_stage2, "name": "Stage 2 Breakout (52w high + volume)",
                        "desc": "Weekly close at a new 52-week high on >=1.3x average volume; "
                                "exit on weekly close below the 30-week SMA. "
                                "Backtest-verified best fit for 1-6 week swing holds.",
                        "params": {"lookback_w": 52, "vol_mult": 1.3, "sma_w": 30}},
}

from .strategies_psx import PSX_STRATEGIES  # noqa: E402
STRATEGIES.update(PSX_STRATEGIES)

from .strategies_playbook import PLAYBOOK_STRATEGIES  # noqa: E402
STRATEGIES.update(PLAYBOOK_STRATEGIES)


def _max_dd(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity / peak - 1).min()
    return round(float(dd) * 100, 2)


def run(symbol: str, strategy: str = "sma_cross", start: str | None = None,
        end: str | None = None, capital: float = 1000000,
        commission_pct: float = 0.15, slippage_pct: float = 0.10,
        use_atr_stop: bool = True, atr_mult: float = 2.0,
        take_profit_mult: float = 0.0, params: dict | None = None) -> dict:
    symbol = symbol.upper().strip()
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'. Pick from {list(STRATEGIES)}")
    spec = STRATEGIES[strategy]
    p = {**spec["params"], **(params or {})}

    df = psx.get_history(symbol)
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    df = df.reset_index(drop=True)
    if len(df) < 60:
        return {"error": "not enough history for this window"}

    t = ind.compute_all(df)
    entries = spec["fn"](df, **{k: v for k, v in p.items()
                                if k in spec["fn"].__code__.co_varnames}).fillna(False)

    cost = commission_pct / 100 + slippage_pct / 100
    cash, qty, entry_px, stop, target = capital, 0, 0.0, 0.0, 0.0
    equity_curve, trades = [], []
    in_pos = False
    entry_i = None      # bar index of the open trade (set on entry)

    closes = t["close"].values
    opens = t["open"].values
    highs = t["high"].values
    lows = t["low"].values
    atrs = t["atr14"].fillna(t["close"] * 0.02).values
    dates = t["date"]
    s2_exit = (_stage2_weekly_below_sma(df, int(p.get("sma_w", 30)))
               if strategy == "stage2_breakout" else None)
    exit_fn = spec.get("exit_fn")
    exit_flag = None
    if exit_fn is not None:
        exit_flag = exit_fn(df, **{k: v for k, v in p.items()
                                   if k in exit_fn.__code__.co_varnames})
        exit_flag = exit_flag.fillna(False).astype(bool)

    for i in range(1, len(t)):
        px_open = float(opens[i])
        # exits first (intraday stop/target check on bar i)
        if in_pos:
            exit_px, reason = 0.0, ""
            if use_atr_stop and float(lows[i]) <= stop:
                exit_px, reason = stop, "atr-stop"
            elif take_profit_mult and float(highs[i]) >= target:
                exit_px, reason = target, "take-profit"
            elif strategy == "rsi_meanrev" and float(t["rsi14"].iloc[i]) > 55:
                exit_px, reason = px_open, "rsi-exit"
            elif strategy in ("sma_cross", "macd") and not bool(entries.iloc[i]):
                exit_px, reason = px_open, "signal-off"
            elif strategy == "momentum" and (float(closes[i]) < float(t["sma50"].iloc[i])):
                exit_px, reason = px_open, "trend-exit"
            elif strategy == "stage2_breakout" and s2_exit is not None and bool(s2_exit[i]):
                exit_px, reason = px_open, "weekly-30w-sma-exit"
            elif exit_flag is not None and bool(exit_flag.iloc[i]):
                exit_px, reason = px_open, spec.get("exit_reason", "strategy-exit")
            if exit_px:
                proceeds = qty * exit_px * (1 - cost)
                ret = (proceeds - (qty * entry_px)) / (qty * entry_px) * 100
                trades.append({"entry_date": str(dates.iloc[entry_i].date()),
                               "exit_date": str(dates.iloc[i].date()),
                               "entry": round(entry_px, 2), "exit": round(exit_px, 2),
                               "qty": qty, "return_pct": round(float(ret), 2),
                               "reason": reason})
                cash = proceeds
                qty, in_pos = 0, False
        # entries
        if not in_pos and bool(entries.iloc[i - 1]):
            fill = px_open * (1 + cost)
            q = int(cash // fill)
            if q > 0:
                qty, entry_px, entry_i = q, fill, i
                cash -= q * fill
                atr = float(atrs[i]) or fill * 0.02
                stop = fill - atr_mult * atr
                target = fill + take_profit_mult * atr if take_profit_mult else 0.0
                in_pos = True
        equity_curve.append({"date": str(dates.iloc[i].date()),
                             "equity": round(cash + qty * float(closes[i]), 2)})

    eq = pd.Series([e["equity"] for e in equity_curve])
    rets = eq.pct_change().dropna()
    wins = [x for x in trades if x["return_pct"] > 0]
    losses = [x for x in trades if x["return_pct"] <= 0]
    gp = sum(x["return_pct"] for x in wins)
    gl = abs(sum(x["return_pct"] for x in losses)) or 1e-9
    years = max((t["date"].iloc[-1] - t["date"].iloc[0]).days / 365.25, 1 / 365.25)
    cagr = ((eq.iloc[-1] / capital) ** (1 / years) - 1) * 100 if len(eq) else 0
    buy_hold = (float(closes[-1]) / float(opens[1]) - 1) * 100

    # a position still open at the last bar: its profit is in final equity but
    # NOT in the closed-trade win-rate — report it separately so numbers add up
    open_trade = None
    if in_pos:
        now_px = float(closes[-1])
        open_trade = {"entry_date": str(dates.iloc[entry_i].date()),
                      "entry": round(entry_px, 2), "now": round(now_px, 2),
                      "qty": qty,
                      "unrealized_pct": round((now_px / entry_px - 1) * 100, 2)}

    return {
        "symbol": symbol, "strategy": strategy,
        "strategy_name": spec["name"], "params": p,
        "window": {"start": str(dates.iloc[0].date()), "end": str(dates.iloc[-1].date()),
                   "bars": len(t)},
        "metrics": {
            "final_equity": round(float(eq.iloc[-1]), 2),
            "total_return_pct": round((float(eq.iloc[-1]) / capital - 1) * 100, 2),
            "buy_hold_pct": round(buy_hold, 2),
            "cagr_pct": round(float(cagr), 2),
            "sharpe": round(float(rets.mean() / rets.std() * (252 ** 0.5)) if len(rets) and rets.std() else 0, 2),
            "max_drawdown_pct": _max_dd(eq),
            "trades": len(trades),
            "open_trade": open_trade,
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "profit_factor": round(gp / gl, 2) if trades else 0,
            "avg_win_pct": round(gp / len(wins), 2) if wins else 0,
            "avg_loss_pct": round(sum(x["return_pct"] for x in losses) / len(losses), 2) if losses else 0,
        },
        "equity": equity_curve[::max(len(equity_curve) // 400, 1)],
        "trades": trades[-100:],
        "assumptions": {"capital": capital, "commission_pct": commission_pct,
                        "slippage_pct": slippage_pct, "use_atr_stop": use_atr_stop,
                        "atr_mult": atr_mult, "take_profit_mult": take_profit_mult},
    }
