# 20 — Moving-Average Indicator Playbooks (mind-map edition)

Built from your **Moving Average Strategy Guide** mind map, extended with
**RSI divergence** and **CCI** as you asked. Every playbook uses **2–3
indicators**, and every moving average keeps the **exact period on its exact
timeframe** from the map. All six playbooks are live in the **Backtest tab**
(strategy names start with **🗺 MA Playbook**).

## The map's cycle ladder (exact periods & timeframes)

| Cycle | Chart timeframe | Moving average | Purpose | Engine status |
|---|---|---|---|---|
| One day | **5-minute** | **78 EMA** | Day-trading resolution | manual chart (free data is end-of-day) |
| One week | **15-minute** | **130 EMA** | Zoomed-in weekly trend | manual chart |
| One month | **65-minute** | **126 EMA** | Swing resolution | manual chart |
| One week | daily | **5 EMA** | Ride strong momentum | ✅ P1 |
| One month | daily | **21 EMA** | Momentum swing cycle | ✅ P1, P2, P5 |
| One quarter | daily | **63 EMA** | Quarter context | ✅ P2, P3, P6 |
| Market stage | **weekly** | **30-week SMA** | Major cycle shifts | ✅ P3, P4 |
| One year | **weekly** | **52-week EMA** | Primary market cycle | ✅ P4 |

Why 78 / 130 / 126: a PSX session is 390 minutes, so **78×5min = 1 day**,
**130×15min ≈ 1 week**, **126×65min ≈ 1 month**. Use them as your *execution
ladder*: the daily/weekly playbooks below pick the trade; the intraday EMAs
time the actual entry when you sit at the screen (price above the 78 EMA on
the 5-min = day's path of least resistance). The automated engine can't see
intraday bars (free PSX data is end-of-day), so it backtests the daily and
weekly rungs of the same ladder.

## Indicator types (from the map)

- **SMA** — arithmetic mean; most intuitive (used: 30-week SMA stage line).
- **EMA** — weights recent prices; smoother & more reactive (5/21/63, 52-week).
- **Wilders** — Wilder's smoothing; reacts slower than EMA (used in P5).

## The six playbooks (2–3 indicators each)

### P1 — Momentum Ride · `5 EMA + 21 EMA + CCI(20)` · daily
- **Setup:** close > 5 EMA and 5 EMA > 21 EMA (riding strong momentum inside the month cycle).
- **Entry:** CCI(20) prints above **+100** (momentum confirmation), first bar only.
- **Stop:** 2×ATR below entry (engine default).
- **Exit:** close < 21 EMA, or CCI < −100.

### P2 — Swing Cycle · `21 EMA + 63 EMA + RSI(14) divergence` · daily
- **Setup:** 21 EMA > 63 EMA (month cycle above quarter cycle).
- **Entry:** pullback tags the 21 EMA (within 2%), then a close above the prior high — taken when RSI makes a **higher low** at the dip (bullish divergence) or resets to 40–60.
- **Exit:** close < 63 EMA (quarter cycle broken).

### P3 — Quarter + Stage · `63 EMA + 30-week SMA + CCI(20)` · daily + weekly
- **Setup:** daily close > 63 EMA **and** last weekly close > 30-week SMA (positive market stage).
- **Entry:** CCI turns up through **−100** (dip resolution).
- **Exit:** close < 63 EMA **or** weekly close < 30-week SMA.

### P4 — Major Cycle Shift · `30-week SMA + 52-week EMA + weekly RSI divergence` · weekly
- **Setup:** Weinstein stage shift: weekly close reclaims the 30-week SMA while 30w SMA > 52w EMA. Early bird: **weekly bullish RSI divergence** at the lows.
- **Entry:** the reclaim week (or the divergence week).
- **Exit:** weekly close back below the 30-week SMA.

### P5 — Systematic Trend Filter · `21 EMA vs 21 Wilders + CCI(20)` · daily
- **Filter (the map's whipsaw cutter):** same period on both averages — EMA above Wilders = **TREND**, below = **RANGE**.
- **Trend mode:** buy CCI > **+100** (breakouts & momentum — the map's trending playbook).
- **Range mode:** buy CCI < **−200** (mean reversion — the map's ranging playbook).
- **Exit:** trend mode: CCI < −100 · range mode: CCI back above 0.

### P6 — RSI-Divergence Bounce · `RSI(14) divergence + 63 EMA + CCI(20)` · daily
- **Setup:** price stretched ≥3% **below** the 63 EMA (counter-trend).
- **Entry:** bullish RSI divergence on the lows (lower price low, higher RSI low, RSI < 40), then CCI climbs back over **−100**.
- **Exit:** price reaches the 63 EMA (bounce complete) — it's a rental.

## Reading the trend (from the map)

- **Rising EMA** = uptrend → prefer P1–P4 longs.
- **Falling EMA** = downtrend → only P6 bounces, small size.
- **Flat EMA** = chop → P5 range mode or stand aside.

## How to run them

Backtest tab → pick the stock → Strategy dropdown → any **🗺 MA Playbook — P1…P6**
→ 3–5+ years of dates → Run backtest. Costs (commission + slippage) and ATR
stops are applied exactly like every other strategy. For education, not
financial advice.
