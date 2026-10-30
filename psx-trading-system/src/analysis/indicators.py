"""Classic technical indicators in pure pandas/numpy (no paid libs).

All functions take a DataFrame with date/open/high/low/close/volume and
return Series aligned to it. `compute_all` adds every column; `snapshot`
reduces the latest bar to a plain dict for the API/research layers.
"""
import numpy as np
import pandas as pd

# ── moving averages ─────────────────────────────────────────────────
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()

def wilders(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average = EMA with alpha 1/n (slower than EMA)."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()

def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Commodity Channel Index on the typical price."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(n, min_periods=n).mean()
    md = (tp - ma).abs().rolling(n, min_periods=n).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))

# ── RSI (Wilder) ────────────────────────────────────────────────────
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100 * (gain > 0).astype(float))

# ── MACD ────────────────────────────────────────────────────────────
def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    line = ema(close, fast) - ema(close, slow)
    signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal

# ── Bollinger ───────────────────────────────────────────────────────
def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std()
    return mid, mid + k * sd, mid - k * sd

# ── ATR ─────────────────────────────────────────────────────────────
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

# ── Stochastic ──────────────────────────────────────────────────────
def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3):
    lo = df["low"].rolling(k, min_periods=k).min()
    hi = df["high"].rolling(k, min_periods=k).max()
    pct_k = 100 * (df["close"] - lo) / (hi - lo).replace(0, np.nan)
    return pct_k, pct_k.rolling(d, min_periods=d).mean()

# ── OBV / volume ────────────────────────────────────────────────────
def obv(df: pd.DataFrame) -> pd.Series:
    d = df["close"].diff()
    return (np.sign(d.fillna(0)) * df["volume"].fillna(0)).cumsum()

def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return close.pct_change(n) * 100

def donchian(df: pd.DataFrame, n: int = 20):
    return (df["high"].rolling(n, min_periods=n).max(),
            df["low"].rolling(n, min_periods=n).min())

# ── swings / support-resistance ─────────────────────────────────────
def swing_levels(df: pd.DataFrame, left: int = 5, right: int = 5, lookback: int = 120):
    h, l = df["high"].values, df["low"].values
    n = len(df)
    start = max(left, n - lookback)
    highs, lows = [], []
    for i in range(start, n - right):
        if h[i] == h[i - left:i + right + 1].max():
            highs.append(float(h[i]))
        if l[i] == l[i - left:i + right + 1].min():
            lows.append(float(l[i]))
    return highs, lows


def support_resistance(df: pd.DataFrame) -> dict:
    if len(df) < 30:
        c = float(df["close"].iloc[-1])
        return {"support_1": c, "support_2": c, "resistance_1": c, "resistance_2": c}
    close = float(df["close"].iloc[-1])
    highs, lows = swing_levels(df)
    res = sorted([x for x in highs if x > close * 1.002])[:2]
    sup = sorted([x for x in lows if x < close * 0.998], reverse=True)[:2]
    hi20 = float(df["high"].tail(20).max())
    lo20 = float(df["low"].tail(20).min())
    return {
        "support_1": round(sup[0], 2) if sup else round(lo20, 2),
        "support_2": round(sup[1], 2) if len(sup) > 1 else round(lo20, 2),
        "resistance_1": round(res[0], 2) if res else round(hi20, 2),
        "resistance_2": round(res[1], 2) if len(res) > 1 else round(hi20, 2),
    }

# ── bulk + snapshot ─────────────────────────────────────────────────
def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["sma10"] = sma(c, 10); df["sma20"] = sma(c, 20)
    df["sma50"] = sma(c, 50); df["sma100"] = sma(c, 100); df["sma200"] = sma(c, 200)
    df["ema5"] = ema(c, 5); df["ema10"] = ema(c, 10); df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50); df["ema100"] = ema(c, 100); df["ema200"] = ema(c, 200)
    df["ema12"] = ema(c, 12); df["ema26"] = ema(c, 26)
    df["rsi14"] = rsi(c)
    m, s, h = macd(c)
    df["macd"], df["macd_signal"], df["macd_hist"] = m, s, h
    mid, up, lo = bollinger(c)
    df["bb_mid"], df["bb_up"], df["bb_lo"] = mid, up, lo
    df["atr14"] = atr(df)
    k, d = stochastic(df)
    df["stoch_k"], df["stoch_d"] = k, d
    df["obv"] = obv(df)
    df["roc12"] = roc(c)
    dh, dl = donchian(df, 20)
    df["don_hi20"], df["don_lo20"] = dh, dl
    df["vol_sma20"] = df["volume"].rolling(20, min_periods=5).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma20"].replace(0, np.nan)
    df["high_52w"] = c.rolling(252, min_periods=20).max()
    df["low_52w"] = c.rolling(252, min_periods=20).min()
    return df


def _f(x):
    try:
        v = float(x)
        return round(v, 2) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None


def _divergences(t: pd.DataFrame):
    """Regular RSI & MACD divergences on the latest swing: 'bullish' / 'bearish' / None.

    Bullish: price made a LOWER low at the last swing low while RSI/MACD made a
    higher low. Bearish: price made a HIGHER high while RSI/MACD made a lower high.
    """
    n = len(t)
    if n < 40:
        return None, None
    w = t.iloc[-120:] if n >= 120 else t
    lo, hi, cl = w["low"].values, w["high"].values, w["close"].values
    rv, mv = w["rsi14"].values, w["macd"].values
    m = len(w)
    lows, highs = [], []
    for i in range(2, m - 2):
        if np.isnan(rv[i]) or np.isnan(mv[i]):
            continue
        if lo[i] < lo[i - 1] and lo[i] <= lo[i + 1] and lo[i] < lo[i - 2] and lo[i] <= lo[i + 2]:
            lows.append(i)
        if hi[i] > hi[i - 1] and hi[i] >= hi[i + 1] and hi[i] > hi[i - 2] and hi[i] >= hi[i + 2]:
            highs.append(i)
    rsi_div = macd_div = None
    if len(lows) >= 2 and (m - 1 - lows[-1]) <= 12:
        p1, p2 = lows[-2], lows[-1]
        if p2 - p1 >= 5 and cl[p2] < cl[p1]:
            if rv[p2] > rv[p1] + 1:
                rsi_div = "bullish"
            if mv[p2] > mv[p1]:
                macd_div = "bullish"
    if len(highs) >= 2 and (m - 1 - highs[-1]) <= 12:
        p1, p2 = highs[-2], highs[-1]
        if p2 - p1 >= 5 and cl[p2] > cl[p1]:
            if rsi_div is None and rv[p2] < rv[p1] - 1:
                rsi_div = "bearish"
            if macd_div is None and mv[p2] < mv[p1]:
                macd_div = "bearish"
    return rsi_div, macd_div


def snapshot(df: pd.DataFrame) -> dict:
    """Latest-bar indicator readings + cross/position flags."""
    t = compute_all(df)
    if len(t) < 30:
        return {"error": "not enough history"}
    a, b = t.iloc[-1], t.iloc[-2]
    close = float(a["close"])
    rsi_div, macd_div = _divergences(t)
    return {
        "close": round(close, 2), "date": str(a["date"].date()) if "date" in t else None,
        "sma10": _f(a["sma10"]), "sma20": _f(a["sma20"]), "sma50": _f(a["sma50"]),
        "sma100": _f(a["sma100"]), "sma200": _f(a["sma200"]), "rsi14": _f(a["rsi14"]),
        "ema5": _f(a["ema5"]), "ema10": _f(a["ema10"]), "ema20": _f(a["ema20"]),
        "ema50": _f(a["ema50"]), "ema100": _f(a["ema100"]), "ema200": _f(a["ema200"]),
        "above_ema5": bool(close > a["ema5"]) if pd.notna(a["ema5"]) else None,
        "above_ema10": bool(close > a["ema10"]) if pd.notna(a["ema10"]) else None,
        "above_ema20": bool(close > a["ema20"]) if pd.notna(a["ema20"]) else None,
        "above_ema50": bool(close > a["ema50"]) if pd.notna(a["ema50"]) else None,
        "above_ema100": bool(close > a["ema100"]) if pd.notna(a["ema100"]) else None,
        "above_ema200": bool(close > a["ema200"]) if pd.notna(a["ema200"]) else None,
        "above_sma10": bool(close > a["sma10"]) if pd.notna(a["sma10"]) else None,
        "above_sma20": bool(close > a["sma20"]) if pd.notna(a["sma20"]) else None,
        "above_sma100": bool(close > a["sma100"]) if pd.notna(a["sma100"]) else None,
        "macd": _f(a["macd"]), "macd_signal": _f(a["macd_signal"]),
        "macd_hist": _f(a["macd_hist"]), "macd_bull": bool(a["macd"] > a["macd_signal"]),
        "rsi_div": rsi_div, "macd_div": macd_div,
        "bb_up": _f(a["bb_up"]), "bb_mid": _f(a["bb_mid"]), "bb_lo": _f(a["bb_lo"]),
        "atr14": _f(a["atr14"]),
        "atr_pct": _f(a["atr14"] / a["close"] * 100),
        "stoch_k": _f(a["stoch_k"]), "stoch_d": _f(a["stoch_d"]),
        "roc12": _f(a["roc12"]),
        "don_hi20": _f(a["don_hi20"]), "don_lo20": _f(a["don_lo20"]),
        "vol_ratio": _f(a["vol_ratio"]),
        "high_52w": _f(a["high_52w"]), "low_52w": _f(a["low_52w"]),
        "off_52w_high_pct": _f((close / a["high_52w"] - 1) * 100) if a["high_52w"] else None,
        "above_sma50": bool(close > a["sma50"]) if pd.notna(a["sma50"]) else None,
        "above_sma200": bool(close > a["sma200"]) if pd.notna(a["sma200"]) else None,
        "golden_cross": bool(a["sma50"] > a["sma200"] and b["sma50"] <= b["sma200"])
        if pd.notna(a["sma200"]) and pd.notna(b["sma200"]) else False,
        "death_cross": bool(a["sma50"] < a["sma200"] and b["sma50"] >= b["sma200"])
        if pd.notna(a["sma200"]) and pd.notna(b["sma200"]) else False,
        "macd_cross_up": bool(a["macd"] > a["macd_signal"] and b["macd"] <= b["macd_signal"]),
        "macd_cross_down": bool(a["macd"] < a["macd_signal"] and b["macd"] >= b["macd_signal"]),
        "sma20_cross_up": bool(close > a["sma20"] and float(b["close"]) <= b["sma20"]) if pd.notna(a["sma20"]) and pd.notna(b["sma20"]) else False,
        "sma50_cross_up": bool(close > a["sma50"] and float(b["close"]) <= b["sma50"]) if pd.notna(a["sma50"]) and pd.notna(b["sma50"]) else False,
        "breakout_20d": bool(close >= (a["don_hi20"] or 0) and (a["don_hi20"] or 0) > 0),
        "breakdown_20d": bool(close <= (a["don_lo20"] or 0) and (a["don_lo20"] or 0) > 0),
        **support_resistance(df),
    }
