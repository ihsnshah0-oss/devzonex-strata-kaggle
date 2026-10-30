"""PSX Long Signal Manual — 21 setups (L01-L21) as backtest strategies.

Source: the user's "PSX LONG Entries — Detailed Signal Manual" (26 pages).
Each setup is two-stage in live trading (Stage-1 pre-signal watch -> Stage-2
buy trigger). For backtesting on daily bars the stages are merged: the signal
fires on the day the Stage-2 trigger candle CLOSES, and the engine enters at
the NEXT morning's open — which is exactly the manual's Window-A execution.

Approximations (documented per strategy):
* Index-regime gates (KSE-100 vs its 50MA) are proxied by the stock's own
  trend (close vs 200MA / rising 50MA) — per-stock backtests have no index.
* L04 needs an earnings calendar we don't have, so the "results day" is
  approximated by a high-volume +4%+ catalyst candle that closes near its high.
* L00 (regime scan) and L-PYR (pyramiding add-on) are trading-routine rules,
  not entries — they are not backtestable strategies.
"""
import numpy as np
import pandas as pd

from ..analysis import indicators as ind


# ── helpers ──────────────────────────────────────────────────────────
def _prep(df: pd.DataFrame) -> pd.DataFrame:
    t = ind.compute_all(df)
    return t


def _top_half(t: pd.DataFrame) -> pd.Series:
    rng = (t["high"] - t["low"]).replace(0, np.nan)
    return ((t["close"] - t["low"]) / rng >= 0.5).fillna(False)


def _bull(t: pd.DataFrame) -> pd.Series:
    return t["close"] > t["open"]


def _cooldown(sig: pd.Series, n: int) -> pd.Series:
    """Keep a signal, then suppress the following n bars."""
    out = sig.copy().values
    last = -10**9
    for i in range(len(out)):
        if out[i]:
            if i - last <= n:
                out[i] = False
            else:
                last = i
    return pd.Series(out, index=sig.index)


def _swing_low_idxs(low: np.ndarray, k: int = 3) -> list[int]:
    out = []
    for i in range(k, len(low) - 1):          # right side may be shorter at the tail
        win = low[max(0, i - k): i + min(k, len(low) - i) + 1]
        if low[i] <= win.min() and (i - k >= 0 or i > 0):
            out.append(i)
    return out


def _prev(cond: pd.Series) -> pd.Series:
    """Condition as it stood at YESTERDAY's close (no look-ahead, no warning)."""
    v = cond.fillna(False).to_numpy(dtype=bool)
    out = np.zeros_like(v)
    out[1:] = v[:-1]
    return pd.Series(out, index=cond.index)


def _empty(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


# ── L01 Trend Pullback ───────────────────────────────────────────────
def sig_l01(df, pullback_pct: float = 2.0) -> pd.Series:
    t = _prep(df)
    c, sma20, sma50 = t["close"], t["sma20"], t["sma50"]
    if len(t) < 80:
        return _empty(df)
    trend = (c.shift(1) > sma50.shift(1)) & (sma50 > sma50.shift(3)) & (sma20 > sma50)
    touch = (t["low"] <= sma20 * (1 + pullback_pct / 100)) | \
            ((c <= sma20 * 1.03) & (c >= sma20))
    rsi_ok = (t["rsi14"] >= 35) & (t["rsi14"] <= 60)
    trigger = (c > t["high"].shift(1)) & _top_half(t) & \
              (t["vol_ratio"].fillna(0) >= 1.0) & (c <= sma20 * 1.04)
    return _cooldown(trend & touch & rsi_ok & trigger, 5)


def exit_l01(df) -> pd.Series:
    t = _prep(df)
    return _prev(t["close"] < t["sma20"])


# ── L02 Breakout + Retest ────────────────────────────────────────────
def sig_l02(df, win: int = 60, gap: int = 10, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 20:
        return _empty(df)
    hi, lo, cl, vr = t["high"].values, t["low"].values, t["close"].values, t["vol_ratio"].fillna(0).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    last_break = -10**9
    level = np.nan
    for i in range(win + gap, len(t)):
        seg = hi[i - win: i - gap]
        lvl = seg.max()
        touches = int((seg >= lvl * 0.99).sum())
        broke = (cl[i - 1] >= lvl * 1.02) and (vr[i - 1] >= vol_mult) and bool(top[i - 1])
        if broke:
            last_break, level = i - 1, lvl
        if 1 <= i - last_break <= 5 and not np.isnan(level):
            if lo[i] <= level * 1.01 and cl[i] > level and top[i]:
                sig[i] = True
                last_break = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L03 Range Bounce ─────────────────────────────────────────────────
def sig_l03(df, win: int = 40, min_width: float = 0.08) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 10:
        return _empty(df)
    supp = t["low"].rolling(win, min_periods=win).min()
    res = t["high"].rolling(win, min_periods=win).max()
    width = (res - supp) / supp
    pos = (t["close"] - supp) / (res - supp).replace(0, np.nan)
    lows = t["low"].values
    touches = pd.Series([int((lows[max(0, i - win): i] >= supp.iloc[i] * 0.98).sum())
                         if pd.notna(supp.iloc[i]) else 0 for i in range(len(t))], index=t.index)
    turn = _bull(t) & _top_half(t) & (t["close"] >= supp * 0.995) & \
        (t["rsi14"] > t["rsi14"].shift(1)) & (t["rsi14"].shift(1) < 45) & \
        (t["vol_ratio"].fillna(0) >= 1.0)
    sig = (width >= min_width) & (pos <= 0.30) & (touches >= 2) & turn
    return _cooldown(sig.fillna(False), 8)


# ── L04 Results-Week Momentum (catalyst-day approximation) ──────────
def sig_l04(df, burst_pct: float = 4.0, vol_mult: float = 1.8) -> pd.Series:
    t = _prep(df)
    if len(t) < 40:
        return _empty(df)
    cl, hi, vr = t["close"].values, t["high"].values, t["vol_ratio"].fillna(0).values
    pct = t["close"].pct_change().fillna(0).values * 100
    topq = ((t["close"] - t["low"]) / (t["high"] - t["low"]).replace(0, np.nan) >= 0.7).fillna(False).values
    sig = np.zeros(len(t), dtype=bool)
    cat_i = -10**9
    cat_hi = cat_cl = np.nan
    for i in range(3, len(t)):
        if pct[i - 1] >= burst_pct and vr[i - 1] >= vol_mult and topq[i - 1]:
            cat_i, cat_hi, cat_cl = i - 1, hi[i - 1], cl[i - 1]
        if 1 <= i - cat_i <= 2 and cl[i] > cat_hi and cl[i] <= cat_cl * 1.06 and vr[i] >= 1.0:
            sig[i] = True
            cat_i = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L05 52-Week High ─────────────────────────────────────────────────
def sig_l05(df, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < 260:
        return _empty(df)
    hh = t["high_52w"].shift(1)
    near = t["close"].shift(1) >= hh * 0.95
    not_vertical = t["close"].pct_change(10) <= 0.10
    regime = (t["close"] > t["sma200"]) & (t["sma50"] > t["sma50"].shift(5))
    brk = (t["close"] >= hh * 1.01) & (t["close"] <= hh * 1.06) & \
          (t["vol_ratio"].fillna(0) >= vol_mult) & _top_half(t)
    return _cooldown(near & not_vertical & regime & brk, 10)


# ── L06 Bull Flag / Pennant ──────────────────────────────────────────
def sig_l06(df, pole_min: float = 0.08, pole_max: float = 0.30, vol_mult: float = 1.3) -> pd.Series:
    t = _prep(df)
    if len(t) < 40:
        return _empty(df)
    hi, lo, cl, vol = t["high"].values, t["low"].values, t["close"].values, t["volume"].values
    vsma = t["vol_sma20"].fillna(1).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(20, len(t)):
        e = int(np.argmax(hi[i - 15: i - 2])) + (i - 15)          # pole peak (3+ bars ago)
        if e < 12 or e >= i - 2:
            continue
        pole_start = lo[max(0, e - 10): e + 1].min()
        gain = hi[e] / pole_start - 1
        if not (pole_min <= gain <= pole_max):
            continue
        d = i - e
        if not (3 <= d <= 12):
            continue
        flag_hi = hi[e + 1: i].max()
        flag_lo = lo[e + 1: i].min()
        mid = (hi[e] + pole_start) / 2
        if flag_hi > hi[e] * 1.02 or flag_lo < mid:
            continue
        if np.mean(vol[max(0, i - 3): i]) >= 0.85 * vsma[i]:       # flag volume must die
            continue
        if cl[i] > flag_hi and vol[i] >= vol_mult * vsma[i] and top[i]:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L07 Cup & Handle ─────────────────────────────────────────────────
def sig_l07(df, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < 160:
        return _empty(df)
    hi, lo, cl, vol = t["high"].values, t["low"].values, t["close"].values, t["volume"].values
    vsma = t["vol_sma20"].fillna(1).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(150, len(t)):
        rim_win = hi[i - 120: i - 25]
        if len(rim_win) < 30:
            continue
        rim = rim_win.max()
        rim_pos = int(np.argmax(rim_win)) + (i - 120)
        cup_lo = lo[rim_pos: i].min()
        depth = 1 - cup_lo / rim
        if not (0.10 <= depth <= 0.28):
            continue
        handle = lo[i - 15: i].min()
        if handle < cup_lo or (rim - handle) / rim > 0.13:
            continue
        if np.mean(vol[i - 10: i]) > 0.95 * vsma[i]:               # handle on light volume
            continue
        if cl[i] > rim and vol[i] >= vol_mult * vsma[i] and top[i]:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 15)


# ── L08 Ascending Triangle ───────────────────────────────────────────
def sig_l08(df, win: int = 45, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 15:
        return _empty(df)
    hi, lo, cl = t["high"].values, t["low"].values, t["close"].values
    vr = t["vol_ratio"].fillna(0).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(win, len(t)):
        ceil = hi[i - win: i - 1].max()
        touches = int((hi[i - win: i - 1] >= ceil * 0.99).sum())
        if touches < 2:
            continue
        piv = _swing_low_idxs(lo[max(0, i - win): i], k=2)
        if len(piv) < 3:
            continue
        last3 = [lo[max(0, i - win) + p] for p in piv[-3:]]
        rising = last3[0] < last3[1] < last3[2]
        near = cl[i - 1] >= ceil * 0.97
        if rising and near and cl[i] >= ceil * 1.005 and vr[i] >= vol_mult and top[i]:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L09 Double / Triple Bottom ───────────────────────────────────────
def sig_l09(df, tol: float = 0.03, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < 90:
        return _empty(df)
    lo, hi, cl, vol = t["low"].values, t["high"].values, t["close"].values, t["volume"].values
    vr = t["vol_ratio"].fillna(0).values
    piv = _swing_low_idxs(lo, k=3)
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    pairs = []
    for a in range(len(piv)):
        for b in range(a + 1, len(piv)):
            i1, i2 = piv[a], piv[b]
            if not (10 <= i2 - i1 <= 70):
                continue
            if abs(lo[i2] - lo[i1]) / lo[i1] > tol:
                continue
            if i1 >= 20 or cl[i1 - 20] <= cl[i1] * 1.05:           # need downtrend into bottom 1
                continue
            if vol[i2] > vol[i1] * 1.15:                           # 2nd bottom lighter volume
                continue
            neck = hi[i1: i2 + 1].max()
            pairs.append((i2, neck, lo[min(i1, i2)]))
    for i2, neck, _ in pairs:
        for i in range(i2 + 1, min(i2 + 31, len(t))):
            if cl[i] >= neck * 1.02 and vr[i] >= vol_mult and top[i]:
                sig[i] = True
                break
    return _cooldown(pd.Series(sig, index=df.index), 12)


# ── L10 Spring / Failed Breakdown ────────────────────────────────────
def sig_l10(df, win: int = 40, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 15:
        return _empty(df)
    lo, cl = t["low"].values, t["close"].values
    vr = t["vol_ratio"].fillna(0).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    dip_i = -10**9
    supp = np.nan
    for i in range(win + 5, len(t)):
        s = lo[i - win - 5: i - 5].min()
        touches = int((lo[i - win - 5: i - 5] <= s * 1.02).sum())
        if touches >= 2 and lo[i - 1] <= s * 0.995 and lo[i - 1] >= s * 0.96:
            dip_i, supp = i - 1, s
        if 1 <= i - dip_i <= 3 and not np.isnan(supp):
            if cl[i] > supp and vr[i] >= vol_mult and top[i]:
                sig[i] = True
                dip_i = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L11 RSI Bullish Divergence ───────────────────────────────────────
def sig_l11(df, k: int = 3) -> pd.Series:
    t = _prep(df)
    if len(t) < 80:
        return _empty(df)
    lo, cl = t["low"].values, t["close"].values
    rsi = t["rsi14"].values
    piv = _swing_low_idxs(lo, k=k)
    sig = np.zeros(len(t), dtype=bool)
    for a in range(len(piv)):
        for b in range(a + 1, len(piv)):
            i1, i2 = piv[a], piv[b]
            if not (5 <= i2 - i1 <= 40):
                continue
            if lo[i2] >= lo[i1] or rsi[i2] <= rsi[i1]:             # lower price low + higher RSI low
                continue
            if rsi[i1] > 40:
                continue
            for i in range(i2 + 1, min(i2 + 6, len(t))):
                if cl[i] > cl[i - 1] and _bull(t).iloc[i] and cl[i] >= lo[i2]:
                    sig[i] = True
                    break
    return _cooldown(pd.Series(sig, index=df.index), 10)


def exit_l11(df) -> pd.Series:
    t = _prep(df)                                            # bounce rental: out at the 50MA
    return _prev(t["close"] >= t["sma50"])


# ── L12 Inverse Head & Shoulders ─────────────────────────────────────
def sig_l12(df, vol_mult: float = 1.5) -> pd.Series:
    t = _prep(df)
    if len(t) < 120:
        return _empty(df)
    lo, hi, cl = t["low"].values, t["high"].values, t["close"].values
    vr = t["vol_ratio"].fillna(0).values
    top = _top_half(t).values
    piv = _swing_low_idxs(lo, k=3)
    sig = np.zeros(len(t), dtype=bool)
    for a in range(len(piv) - 2):
        ls, hd, rs = piv[a], piv[a + 1], piv[a + 2]
        if not (lo[hd] < lo[ls] and lo[hd] < lo[rs] and lo[rs] > lo[hd] * 1.01):
            continue
        if rs - ls > 100:
            continue
        neck = hi[ls: rs + 1].max()
        for i in range(rs + 1, min(rs + 21, len(t))):
            if cl[i] > neck and vr[i] >= vol_mult and top[i]:
                sig[i] = True
                break
    return _cooldown(pd.Series(sig, index=df.index), 15)


# ── ICT helpers ──────────────────────────────────────────────────────
def _sweep_mss(t: pd.DataFrame, look: int, mss_window: int, need_fvg: bool):
    """Vectorised-ish sweep->MSS detection. Returns bool Series on MSS bars."""
    lo, hi, cl = t["low"].values, t["high"].values, t["close"].values
    n = len(t)
    sig = np.zeros(n, dtype=bool)
    for i in range(look + 3, n):
        ssl = lo[i - look: i - 2].min()                       # liquidity below
        sweep = -1
        for j in range(i - 2, max(i - look, i - 6), -1):      # recent sweep candle
            if lo[j] < ssl * 1.001 and cl[j] > ssl:
                sweep = j
                break
        if sweep < 0:
            continue
        lh = hi[max(0, sweep - 8): sweep + 1].max()           # last lower-high to reclaim (MSS)
        mss = cl[i] > lh and cl[i] > cl[i - 1] and (cl[i] - lo[i]) > 0.6 * max(hi[i] - lo[i], 1e-9)
        if not mss:
            continue
        if need_fvg:                                          # bullish FVG left by displacement
            fvg = i >= 2 and hi[i - 2] < lo[i]
            if not fvg:
                continue
        if cl[i] < t["close"].rolling(look).max().iloc[i] * 0.999:  # still discount-ish
            sig[i] = True
    return sig


# ── L13 ICT-1 Sweep + MSS + FVG ──────────────────────────────────────
def sig_l13(df, look: int = 20) -> pd.Series:
    t = _prep(df)
    if len(t) < look + 20:
        return _empty(df)
    return _cooldown(pd.Series(_sweep_mss(t, look, 8, need_fvg=True), index=df.index), 10)


# ── L14 ICT-2 Bullish OB Bounce ──────────────────────────────────────
def sig_l14(df, win: int = 10) -> pd.Series:
    t = _prep(df)
    if len(t) < 60:
        return _empty(df)
    hi, lo, cl, op = t["high"].values, t["low"].values, t["close"].values, t["open"].values
    vr = t["vol_ratio"].fillna(0).values
    sig = np.zeros(len(t), dtype=bool)
    bos_i = -10**9
    ob_hi = ob_lo = np.nan
    for i in range(win + 5, len(t)):
        hh = hi[i - win - 1: i - 1].max()
        if cl[i - 1] > hh and vr[i - 1] >= 1.3 and cl[i - 1] > op[i - 1]:
            k = i - 2
            while k >= i - 7 and cl[k] >= op[k]:                # last down-candle pre-BOS
                k -= 1
            if k >= i - 7:
                bos_i, ob_hi, ob_lo = i - 1, max(op[k], cl[k]), lo[k]
        if 1 <= i - bos_i <= 15 and not np.isnan(ob_hi):
            mid = (ob_hi + ob_lo) / 2
            if lo[i] <= ob_hi and cl[i] > mid and cl[i] > op[i] and cl[i] > ob_lo:
                sig[i] = True
                bos_i = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L15 ICT-3 OTE Deep-Discount ──────────────────────────────────────
def sig_l15(df, leg_min: float = 0.08) -> pd.Series:
    t = _prep(df)
    if len(t) < 80:
        return _empty(df)
    hi, lo, cl = t["high"].values, t["low"].values, t["close"].values
    sma50 = t["sma50"].values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(35, len(t)):
        e = int(np.argmax(hi[i - 30: i - 2])) + (i - 30)
        if e < i - 25 or e >= i - 2:
            continue
        origin = lo[max(0, e - 15): e + 1].min()
        leg = hi[e] / origin - 1
        if leg < leg_min:
            continue
        band_top = hi[e] - 0.62 * (hi[e] - origin)
        band_bot = hi[e] - 0.79 * (hi[e] - origin)
        if lo[i] <= band_top and cl[i] >= band_bot and cl[i] > cl[i - 1] and \
           cl[i] > origin and not np.isnan(sma50[i]) and cl[i] > sma50[i]:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L16 ICT-4 Turtle Soup Bottom ─────────────────────────────────────
def sig_l16(df, look: int = 10) -> pd.Series:
    t = _prep(df)
    if len(t) < look + 15:
        return _empty(df)
    lo, hi, cl = t["low"].values, t["high"].values, t["close"].values
    n = len(t)
    sig = np.zeros(n, dtype=bool)
    for i in range(look + 3, n):
        level = lo[i - look: i - 2].min()                       # obvious lows
        sweep = -1
        for j in range(i - 2, max(i - look, i - 5), -1):
            if lo[j] < level * 1.001 and cl[j] > level:
                sweep = j
                break
        if sweep < 0:
            continue
        lh = hi[max(0, sweep - 6): sweep + 1].max()
        if cl[i] > lh and cl[i] > cl[i - 1] and cl[i] > level:  # reclaim + MSS
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 8)


# ── L17 Momentum Burst (day-2 continuation) ─────────────────────────
def sig_l17(df, burst_pct: float = 5.0, vol_mult: float = 2.0) -> pd.Series:
    t = _prep(df)
    if len(t) < 30:
        return _empty(df)
    cl, hi = t["close"].values, t["high"].values
    vr = t["vol_ratio"].fillna(0).values
    pct = t["close"].pct_change().fillna(0).values * 100
    rng = (t["high"] - t["low"]).replace(0, np.nan)
    near_hi = ((t["close"] - t["low"]) / rng >= 0.75).fillna(False).values
    sig = np.zeros(len(t), dtype=bool)
    b_i, b_hi, b_cl = -10**9, np.nan, np.nan
    for i in range(2, len(t)):
        if pct[i - 1] >= burst_pct and vr[i - 1] >= vol_mult and near_hi[i - 1]:
            b_i, b_hi, b_cl = i - 1, hi[i - 1], cl[i - 1]
        if i - b_i in (1, 2) and cl[i] > b_hi and cl[i] <= b_cl * 1.04:
            sig[i] = True
            b_i = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 8)


# ── L18 Bollinger Snap-Back ──────────────────────────────────────────
def sig_l18(df, washout_pct: float = 8.0) -> pd.Series:
    t = _prep(df)
    if len(t) < 220:
        return _empty(df)
    cl = t["close"]
    recent_min = cl.rolling(7, min_periods=7).min()
    washout = recent_min.shift(1) <= cl.shift(7) * (1 - washout_pct / 100)
    tagged = (t["low"] <= t["bb_lo"]).rolling(3, min_periods=1).max().astype(bool)
    rsi_low = (t["rsi14"] < 30).rolling(3, min_periods=1).max().astype(bool)
    floor = cl > t["sma200"]
    reclaim = _bull(t) & _top_half(t) & (cl > t["bb_lo"]) & (t["rsi14"] > t["rsi14"].shift(1))
    return _cooldown((washout & tagged & rsi_low & floor & reclaim).fillna(False), 10)


def exit_l18(df) -> pd.Series:
    t = _prep(df)                                            # manual: sell 100% at the 20MA
    return _prev(t["close"] >= t["sma20"])


# ── L19 Wyckoff LPS / Phase D ────────────────────────────────────────
def sig_l19(df, win: int = 50, min_width: float = 0.08) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 20:
        return _empty(df)
    hi, lo, cl, op, vol = (t["high"].values, t["low"].values, t["close"].values,
                           t["open"].values, t["volume"].values)
    vsma = t["vol_sma20"].fillna(1).values
    rng = (t["high"] - t["low"]).values
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(win + 10, len(t)):
        r_hi = hi[i - win: i - 8].max()
        r_lo = lo[i - win: i - 8].min()
        if (r_hi - r_lo) / r_lo < min_width:
            continue
        mid = (r_hi + r_lo) / 2
        sos = -1
        for j in range(i - 20, i - 3):                        # sign of strength candle
            if cl[j] > op[j] and cl[j] > mid and vol[j] >= 1.5 * vsma[j] and \
               rng[j] >= np.percentile(rng[max(0, j - 60): j + 1], 70):
                sos = j
        if sos < 0:
            continue
        pb = cl[sos + 1: i]
        if len(pb) < 2 or pb.min() < mid:                     # pullback holds above mid
            continue
        if np.mean(vol[sos + 1: i]) >= np.mean(vol[max(0, sos - 3): sos + 1]):
            continue                                          # pullback volume must be lighter
        if cl[i] > cl[i - 1] and top[i] and cl[i] > mid:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 12)


# ── L20 Stopping Volume + Test ───────────────────────────────────────
def sig_l20(df, vol_mult: float = 2.0) -> pd.Series:
    t = _prep(df)
    if len(t) < 90:
        return _empty(df)
    lo, hi, cl, vol = t["low"].values, t["high"].values, t["close"].values, t["volume"].values
    vsma = t["vol_sma20"].fillna(1).values
    rng = (hi - lo)
    top = _top_half(t).values
    sig = np.zeros(len(t), dtype=bool)
    stop_i, stop_lo = -10**9, np.nan
    for i in range(60, len(t)):
        wide = rng[i] >= np.percentile(rng[max(0, i - 60): i + 1], 80)
        if cl[i] < t["sma20"].iloc[i] and vol[i] >= vol_mult * vsma[i] and wide and top[i] and cl[i] > cl[i - 1]:
            stop_i, stop_lo = i, lo[i]
        if 1 <= i - stop_i <= 5 and not np.isnan(stop_lo):
            test = lo[i] >= stop_lo * 0.985 and lo[i] <= stop_lo * 1.02 and \
                vol[i] < 0.7 * vsma[i] and rng[i] < np.median(rng[max(0, i - 20): i + 1]) and cl[i] > cl[i - 1]
            if test:
                sig[i] = True
                stop_i = -10**9
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── L21 VAL Rejection (volume-profile approximation) ────────────────
def sig_l21(df, win: int = 60) -> pd.Series:
    t = _prep(df)
    if len(t) < win + 15:
        return _empty(df)
    cl, lo = t["close"].values, t["low"].values
    vol = t["volume"].fillna(0).values
    sig = np.zeros(len(t), dtype=bool)
    for i in range(win + 5, len(t)):
        prices = cl[i - win: i]
        vols = vol[i - win: i]
        if prices.min() <= 0 or vols.sum() <= 0:
            continue
        edges = np.linspace(prices.min(), prices.max(), 21)
        hist = np.zeros(20)
        for px, vv in zip(prices, vols):
            b = min(int((px - prices.min()) / (prices.max() - prices.min()) * 20), 19)
            hist[b] += vv
        hvn = int(np.argmax(hist))
        val = edges[hvn]                                      # low edge of the high-volume node
        body = abs(cl[i] - t["open"].values[i])
        wick = max(t["open"].values[i], cl[i]) - lo[i]
        reject = lo[i] <= val * 1.015 and cl[i] >= val and cl[i] > t["open"].values[i] and \
            wick >= body and ((cl[i] - lo[i]) / max(t["high"].values[i] - lo[i], 1e-9)) >= 0.5
        if reject:
            sig[i] = True
    return _cooldown(pd.Series(sig, index=df.index), 10)


# ── registry ─────────────────────────────────────────────────────────
_M = "📘 PSX Signal Manual — "
PSX_STRATEGIES = {
    "l01_trend_pullback": {"fn": sig_l01, "exit_fn": exit_l01, "name": _M + "L01 Trend Pullback [1%]",
                           "desc": "Uptrend dips to the rising 20MA (RSI 35-60), bought when price closes back above the prior day's high on volume. Exit on close below 20MA.",
                           "params": {"pullback_pct": 2.0}},
    "l02_breakout_retest": {"fn": sig_l02, "name": _M + "L02 Breakout + Retest [1%]",
                            "desc": "2%+ volume breakout above multi-week resistance, entered on the holding retest of the level.",
                            "params": {"win": 60, "gap": 10, "vol_mult": 1.5}},
    "l03_range_bounce": {"fn": sig_l03, "name": _M + "L03 Range Bounce [1%]",
                         "desc": "Buy the proven floor of a 1-month+ range (2+ touches) on a bullish turn candle; target the range top.",
                         "params": {"win": 40, "min_width": 0.08}},
    "l04_results_momentum": {"fn": sig_l04, "name": _M + "L04 Results-Week Momentum [1%]",
                             "desc": "High-volume +4%+ catalyst candle, entered on day 1-2 continuation above its high (earnings-day approximation).",
                             "params": {"burst_pct": 4.0, "vol_mult": 1.8}},
    "l05_52wk_high": {"fn": sig_l05, "name": _M + "L05 52-Week High [1%]",
                      "desc": "Basing within 5% of the 52-week high, bought on the volume close above it with the 200MA trend filter.",
                      "params": {"vol_mult": 1.5}},
    "l06_bull_flag": {"fn": sig_l06, "name": _M + "L06 Bull Flag / Pennant [1%]",
                      "desc": "+8-30% pole on volume, 3-12 day low-volume flag above the pole midpoint, bought on the flag-top break.",
                      "params": {"pole_min": 0.08, "pole_max": 0.30, "vol_mult": 1.3}},
    "l07_cup_handle": {"fn": sig_l07, "name": _M + "L07 Cup & Handle [1%]",
                       "desc": "10-28% rounded base, shallow light-volume handle in the upper half, bought on the rim break at 1.5x volume.",
                       "params": {"vol_mult": 1.5}},
    "l08_ascending_triangle": {"fn": sig_l08, "name": _M + "L08 Ascending Triangle [1%]",
                               "desc": "Flat ceiling (2+ touches) with rising lows, bought on the volume break above the ceiling.",
                               "params": {"win": 45, "vol_mult": 1.5}},
    "l09_double_bottom": {"fn": sig_l09, "name": _M + "L09 Double/Triple Bottom [0.5% ADV]",
                          "desc": "Two bottoms within 3% after a downtrend, second on lighter volume; bought on the 2%+ neckline break.",
                          "params": {"tol": 0.03, "vol_mult": 1.5}},
    "l10_spring": {"fn": sig_l10, "name": _M + "L10 Spring / Failed Breakdown [0.5% ADV]",
                   "desc": "Dip 0.5-4% below a 2+ touch support, bought on the high-volume close back above it.",
                   "params": {"win": 40, "vol_mult": 1.5}},
    "l11_rsi_divergence": {"fn": sig_l11, "exit_fn": exit_l11, "name": _M + "L11 RSI Bullish Divergence [0.5% ADV]",
                           "desc": "Lower price low + higher RSI low below 40, bought on the bullish confirmation candle; bounce rental, out at the 50MA.",
                           "params": {"k": 3}},
    "l12_inv_hs": {"fn": sig_l12, "name": _M + "L12 Inverse Head & Shoulders [0.5% ADV]",
                   "desc": "Three-trough base with the right shoulder above the head; bought on the volume neckline break.",
                   "params": {"vol_mult": 1.5}},
    "l13_ict_sweep_mss_fvg": {"fn": sig_l13, "name": _M + "L13 ICT Sweep + MSS + FVG [0.5% ADV]",
                              "desc": "Sweep of the swing lows, displacement close above the last lower-high (MSS) leaving a fair-value gap.",
                              "params": {"look": 20}},
    "l14_ict_ob_bounce": {"fn": sig_l14, "name": _M + "L14 ICT Bullish OB Bounce [0.5% ADV]",
                          "desc": "Break of structure up, then a bullish reaction from the last down-candle order block before the break.",
                          "params": {"win": 10}},
    "l15_ict_ote": {"fn": sig_l15, "name": _M + "L15 ICT OTE Deep-Discount [0.5% ADV]",
                    "desc": "Pullback into the 62-79% optimal-trade band of a fresh 8%+ displacement leg, above the 50MA.",
                    "params": {"leg_min": 0.08}},
    "l16_turtle_soup": {"fn": sig_l16, "name": _M + "L16 Turtle Soup Bottom [0.5% ADV]",
                        "desc": "Failed break of obvious recent lows: sweep wick, close back above, then reclaim of the last swing high.",
                        "params": {"look": 10}},
    "l17_momentum_burst": {"fn": sig_l17, "name": _M + "L17 Momentum Burst [0.5% ADV]",
                           "desc": "+5% catalyst candle on 2x volume closing near its high; day-1/2 continuation above the burst high.",
                           "params": {"burst_pct": 5.0, "vol_mult": 2.0}},
    "l18_bb_snapback": {"fn": sig_l18, "exit_fn": exit_l18, "name": _M + "L18 Bollinger Snap-Back [0.5% ADV]",
                        "desc": "8%+ washout tagging the lower band with RSI<30 above the 200MA; bought on the close back inside the bands, out at the 20MA.",
                        "params": {"washout_pct": 8.0}},
    "l19_wyckoff_lps": {"fn": sig_l19, "name": _M + "L19 Wyckoff LPS / Phase D [0.5% ADV]",
                        "desc": "Range with a strong sign-of-strength candle, light-volume pullback holding the midpoint, bought on the bullish turn.",
                        "params": {"win": 50, "min_width": 0.08}},
    "l20_stopping_volume": {"fn": sig_l20, "name": _M + "L20 Stopping Volume + Test [0.5% ADV]",
                            "desc": "2x-volume wide-range stopping bar in a decline, then the low-volume narrow Test; bought after the Test holds.",
                            "params": {"vol_mult": 2.0}},
    "l21_val_rejection": {"fn": sig_l21, "name": _M + "L21 VAL Rejection [0.5% ADV]",
                          "desc": "Rejection wick at the value-area-low of the 60-day volume profile with a close back above it.",
                          "params": {"win": 60}},
}
