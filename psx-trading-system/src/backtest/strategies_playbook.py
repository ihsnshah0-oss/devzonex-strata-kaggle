"""Moving-Average Strategy Guide — indicator playbooks (mind-map edition).

Source: the user's "Moving Average Strategy Guide" mind map:
  * Standard daily indicators : 5 EMA (1 week), 21 EMA (1 month), 63 EMA (1 quarter)
  * Long-term weekly cycles   : 30-week SMA (stage analysis), 52-week EMA (1 year)
  * Indicator types           : SMA / EMA / Wilders (Wilder's smoothing)
  * Strategic application     : trend ID (rising/falling/flat MA), context
    playbooks (trending -> momentum & breakouts, ranging -> mean reversion),
    systematic trend filtering (EMA vs Wilders, same period) to cut whipsaw.
  * Intraday cycles (manual charts, documented in docs/20-...): 1-day = 78 EMA
    on the 5-min, 1-week = 130 EMA on the 15-min, 1-month = 126 EMA on the
    65-min. Free EOD data has no intraday bars, so the engine backtests the
    daily/weekly equivalents (5/21/63 EMA, 30w SMA, 52w EMA).

The user asked to extend the map with RSI divergence and CCI, and to build
each playbook from 2-3 indicators. Every strategy below states its indicator
set in the name/description.

Signals fire on the CLOSE of the bar; the engine enters next open.
"""
import numpy as np
import pandas as pd

from ..analysis import indicators as ind
from .strategies_psx import _swing_low_idxs

_PB = "🗺 MA Playbook — "


# ── shared helpers ──────────────────────────────────────────────────
def _cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    return ind.cci(df, n)


def _rising_edge(cond: pd.Series) -> pd.Series:
    v = (cond == True).to_numpy()                      # NaN-safe, no downcast
    prev = np.zeros_like(v)
    prev[1:] = v[:-1]
    return pd.Series(v & ~prev, index=cond.index)


def _cooldown(sig: pd.Series, n: int) -> pd.Series:
    out = sig.copy().to_numpy(dtype=bool)
    last = -10**9
    for i in range(len(out)):
        if out[i]:
            if i - last <= n:
                out[i] = False
            else:
                last = i
    return pd.Series(out, index=sig.index)


def _bull_div(low: pd.Series, rsi: pd.Series, k: int = 3,
              lookback: int = 60, rsi_max: float = 45.0) -> pd.Series:
    """Bullish RSI divergence: newer swing low is a LOWER price low but a
    HIGHER RSI low (RSI still bearish, < rsi_max). Flag raised k bars after
    the second low (confirmation), so no look-ahead."""
    lo = low.to_numpy(dtype=float)
    rs = rsi.to_numpy(dtype=float)
    n = len(lo)
    out = np.zeros(n, dtype=bool)
    piv = _swing_low_idxs(lo, k)
    for a, b in zip(piv, piv[1:]):
        if b - a > lookback or b - a < 2:
            continue
        if not (np.isfinite(rs[a]) and np.isfinite(rs[b])):
            continue
        if lo[b] < lo[a] * 0.999 and rs[b] > rs[a] + 1.0 and rs[b] < rsi_max:
            out[min(n - 1, b + k)] = True
    return pd.Series(out, index=low.index)


def _weekly(df: pd.DataFrame) -> pd.DataFrame:
    return (df.set_index("date").resample("W-FRI")
            .agg({"open": "first", "high": "max", "low": "min",
                  "close": "last", "volume": "sum"})
            .dropna(subset=["close"]))


def _wk_to_daily(wk: pd.Series, df: pd.DataFrame) -> pd.Series:
    """Last COMPLETED week's value, mapped to daily bars (no look-ahead).

    Returns a float series (bools become 0/1) so callers can fillna/astype
    without pandas object-dtype downcast warnings."""
    num = wk.astype(float) if wk.dtype == bool else wk
    d = num.reindex(df.set_index("date").index, method="ffill").shift(1)
    return d.reset_index(drop=True)


# ── PB1 · One-Week Momentum Ride — 5 EMA + 21 EMA + CCI(20) ──────────
def sig_pb1(df) -> pd.Series:
    """Ride strong momentum (the map's 5-day-EMA purpose) inside a 1-month
    cycle: close > 5EMA > 21EMA with CCI > +100 (momentum confirmation)."""
    t = ind.compute_all(df)
    e5, e21 = ind.ema(t["close"], 5), ind.ema(t["close"], 21)
    cond = (t["close"] > e5) & (e5 > e21) & (_cci(df) > 100)
    return _cooldown(_rising_edge(cond), 10)


def exit_pb1(df) -> pd.Series:
    t = ind.compute_all(df)
    e5, e21 = ind.ema(t["close"], 5), ind.ema(t["close"], 21)
    return (t["close"] < e21) | (_cci(df) < -100)


# ── PB2 · One-Month Swing Cycle — 21 EMA + 63 EMA + RSI divergence ──
def sig_pb2(df) -> pd.Series:
    """Uptrend (21EMA > 63EMA), pullback that tags the 21EMA, then a bullish
    recovery close above the prior high — taken when RSI shows a higher-low
    divergence at the dip (or a healthy 40-60 reset)."""
    t = ind.compute_all(df)
    e21, e63 = ind.ema(t["close"], 21), ind.ema(t["close"], 63)
    uptrend = e21 > e63
    tagged = (t["low"].rolling(5, min_periods=1).min() <= e21 * 1.02)
    recover = t["close"] > t["high"].shift(1)
    div = _bull_div(t["low"], t["rsi14"], k=3, lookback=20, rsi_max=50)
    div_recent = div.rolling(10, min_periods=1).max().fillna(False).astype(bool)
    rsi_reset = (t["rsi14"] > 40) & (t["rsi14"] < 60)
    return _cooldown(uptrend & tagged & recover & (div_recent | rsi_reset), 15)


def exit_pb2(df) -> pd.Series:
    t = ind.compute_all(df)
    return t["close"] < ind.ema(t["close"], 63)


# ── PB3 · Quarter Context — 63 EMA + 30-week SMA + CCI(20) ──────────
def sig_pb3(df) -> pd.Series:
    """Daily quarter trend (close > 63EMA) inside a positive market stage
    (weekly close > 30-week SMA); CCI crossing up through -100 times the dip."""
    t = ind.compute_all(df)
    wk = _weekly(df)
    stage_up = _wk_to_daily(wk["close"] > wk["close"].rolling(30, min_periods=30).mean(), df)
    stage_up = stage_up.fillna(0).astype(bool)
    c = _cci(df)
    dip_turn = _rising_edge(c > -100)
    return _cooldown((t["close"] > ind.ema(t["close"], 63)) & stage_up & dip_turn, 15)


def exit_pb3(df) -> pd.Series:
    t = ind.compute_all(df)
    wk = _weekly(df)
    below_w = _wk_to_daily(wk["close"] < wk["close"].rolling(30, min_periods=30).mean(), df)
    return (t["close"] < ind.ema(t["close"], 63)) | below_w.fillna(False).astype(bool)


# ── PB4 · Major Cycle Shift — 30w SMA + 52w EMA + weekly RSI div ────
def sig_pb4(df) -> pd.Series:
    """Weinstein-style stage shift on the WEEKLY chart: close reclaiming the
    30-week SMA while 30w > 52w EMA — or an early entry on weekly bullish RSI
    divergence. One position per cycle move."""
    wk = _weekly(df)
    s30 = wk["close"].rolling(30, min_periods=30).mean()
    e52 = wk["close"].ewm(span=52, adjust=False, min_periods=52).mean()
    rsi_w = ind.rsi(wk["close"], 14)
    cross_up = (wk["close"] > s30) & (wk["close"].shift(1) <= s30.shift(1))
    aligned = s30 > e52
    div_w = _bull_div(wk["low"], rsi_w, k=2, lookback=26, rsi_max=45)
    wk_sig = (cross_up & aligned) | div_w
    return _cooldown(_wk_to_daily(wk_sig, df).fillna(False).astype(bool), 20)


def exit_pb4(df) -> pd.Series:
    wk = _weekly(df)
    s30 = wk["close"].rolling(30, min_periods=30).mean()
    return _wk_to_daily(wk["close"] < s30, df).fillna(False).astype(bool)


# ── PB5 · Systematic Trend Filter — 21 EMA vs 21 Wilders + CCI ──────
def sig_pb5(df) -> pd.Series:
    """The map's whipsaw filter: EMA(21) above Wilders(21) = TREND mode ->
    buy momentum (CCI > +100); below = RANGE mode -> buy mean reversion
    (CCI < -200). Same period on both averages, exactly as the guide says."""
    t = ind.compute_all(df)
    e21 = ind.ema(t["close"], 21)
    w21 = ind.wilders(t["close"], 21)
    c = _cci(df)
    trend_mode = e21 > w21
    sig_trend = trend_mode & _rising_edge(c > 100)          # breakouts & momentum
    sig_range = ~trend_mode & (c < -200)                    # mean reversion
    return _cooldown(sig_trend | sig_range, 10)


def exit_pb5(df) -> pd.Series:
    t = ind.compute_all(df)
    c = _cci(df)
    trend_mode = ind.ema(t["close"], 21) > ind.wilders(t["close"], 21)
    return (trend_mode & (c < -100)) | (~trend_mode & (c > 0))


# ── PB6 · RSI Divergence Reversal — RSI div + 63 EMA + CCI ──────────
def sig_pb6(df) -> pd.Series:
    """Counter-trend bounce: price stretched below the quarter EMA (63),
    bullish RSI divergence on the lows, entered when CCI climbs back over
    -100. A rental — out at the 63 EMA."""
    t = ind.compute_all(df)
    e63 = ind.ema(t["close"], 63)
    stretched = t["close"] < e63 * 0.97
    div = _bull_div(t["low"], t["rsi14"], k=3, lookback=60, rsi_max=40)
    div_recent = div.rolling(10, min_periods=1).max().fillna(False).astype(bool)
    c = _cci(df)
    return _cooldown(stretched & div_recent & _rising_edge(c > -100), 20)


def exit_pb6(df) -> pd.Series:
    t = ind.compute_all(df)
    return t["close"] >= ind.ema(t["close"], 63)


PLAYBOOK_STRATEGIES = {
    "pb1_momentum_ride": {"fn": sig_pb1, "exit_fn": exit_pb1,
                          "name": _PB + "P1 Momentum Ride (5EMA+21EMA+CCI)",
                          "desc": "Map: 5-day EMA rides strong momentum inside the 21-day cycle. Buy close>5EMA>21EMA with CCI(20)>100; exit close<21EMA or CCI<-100.",
                          "params": {}},
    "pb2_swing_cycle": {"fn": sig_pb2, "exit_fn": exit_pb2,
                        "name": _PB + "P2 Swing Cycle (21EMA+63EMA+RSI-div)",
                        "desc": "Map: 21/63-day EMA month/quarter cycles. Buy uptrend pullbacks that tag the 21EMA and recover, confirmed by RSI higher-low divergence (or 40-60 reset); exit close<63EMA.",
                        "params": {}},
    "pb3_quarter_context": {"fn": sig_pb3, "exit_fn": exit_pb3,
                            "name": _PB + "P3 Quarter+Stage (63EMA+30wSMA+CCI)",
                            "desc": "Map: 63-day EMA quarter trend + 30-week SMA market stage. Buy daily dips (CCI crosses -100 up) only when both are up; exit if either breaks.",
                            "params": {}},
    "pb4_major_cycle_shift": {"fn": sig_pb4, "exit_fn": exit_pb4,
                              "name": _PB + "P4 Major Cycle (30wSMA+52wEMA+RSI-div)",
                              "desc": "Map: 30-week SMA stage analysis + 52-week EMA yearly cycle, weekly chart. Buy the reclaim of the 30w SMA while 30w>52w (or early on weekly RSI divergence); exit weekly close<30w SMA.",
                              "params": {}},
    "pb5_trend_filter_cci": {"fn": sig_pb5, "exit_fn": exit_pb5,
                             "name": _PB + "P5 Trend Filter (21EMA vs 21Wilders+CCI)",
                             "desc": "Map: EMA vs Wilders, same period, quantifies trend vs range. Trend mode buys CCI>100 momentum; range mode buys CCI<-200 reversion. Cuts whipsaw.",
                             "params": {}},
    "pb6_rsi_div_reversal": {"fn": sig_pb6, "exit_fn": exit_pb6,
                             "name": _PB + "P6 RSI-Div Bounce (RSI-div+63EMA+CCI)",
                             "desc": "User add-on: bullish RSI divergence while stretched below the 63 EMA, entered on CCI > -100; bounce rental exited at the 63 EMA.",
                             "params": {}},
}
