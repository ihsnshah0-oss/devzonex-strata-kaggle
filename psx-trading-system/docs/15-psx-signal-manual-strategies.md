# 📘 PSX Long Signal Manual — 21 Backtest Strategies (L01–L21)

Added **22 Sep 2026** from your "PSX LONG Entries — Detailed Signal Manual"
(26 pages, kept in `docs/psx-long-signal-manual.txt`). All 21 entry setups are
now selectable in the **Backtest** tab — the dropdown shows them with the 📘 prefix.

## How the manual maps to backtests

The manual trades in two stages live: **Stage 1** = evening pre-signal (watch),
**Stage 2** = exact buy trigger. In backtests the stages are merged: the signal
fires on the day the Stage-2 trigger candle **closes**, and the engine buys at
the **next morning's open** — exactly the manual's Window-A execution.

Two honest approximations:
* **Index regime gates** (KSE-100 vs its 50MA) are proxied by the stock's own
  trend (close vs 200MA / rising 50MA) — per-stock backtests don't carry the index.
* **L04 Results-Week Momentum** needs an earnings calendar we don't have, so the
  "results day" is approximated by a +4% high-volume catalyst candle closing near its high.

**L00** (regime scan) and **L-PYR** (pyramiding) are routine rules, not entries —
not backtestable, so they're not in the list.

## The 21 strategies

| ID | Setup | Class | Exit extras |
|----|-------|-------|-------------|
| l01_trend_pullback | Trend Pullback (20MA dip + prior-high close) | 1% standard | out on close < 20MA |
| l02_breakout_retest | Breakout + holding retest of resistance | 1% standard | — |
| l03_range_bounce | Range floor bounce (2+ touches) | 1% standard | — |
| l04_results_momentum | Post-catalyst day-1/2 continuation | 1% standard | — |
| l05_52wk_high | 52-week-high breakout on volume | 1% standard | — |
| l06_bull_flag | Pole + low-volume flag break | 1% standard | — |
| l07_cup_handle | Rounded base + handle, rim break | 1% standard | — |
| l08_ascending_triangle | Flat top + rising lows, ceiling break | 1% standard | — |
| l09_double_bottom | Double/triple bottom, neckline break | 0.5% ADV | — |
| l10_spring | Failed breakdown, reclaim on volume | 0.5% ADV | — |
| l11_rsi_divergence | Lower price low + higher RSI low | 0.5% ADV | out at 50MA (bounce rental) |
| l12_inv_hs | Inverse head & shoulders, neck break | 0.5% ADV | — |
| l13_ict_sweep_mss_fvg | Sweep + market-structure shift + FVG | 0.5% ADV | — |
| l14_ict_ob_bounce | Order-block bounce after BOS | 0.5% ADV | — |
| l15_ict_ote | OTE 62–79% pullback of a displacement leg | 0.5% ADV | — |
| l16_turtle_soup | Failed break of obvious lows | 0.5% ADV | — |
| l17_momentum_burst | +5% burst, day-2 continuation | 0.5% ADV | — |
| l18_bb_snapback | Washout + band reclaim | 0.5% ADV | out at 20MA (manual's target) |
| l19_wyckoff_lps | SOS + light-volume LPS | 0.5% ADV | — |
| l20_stopping_volume | Stopping bar + low-volume test | 0.5% ADV | — |
| l21_val_rejection | Value-area-low rejection wick | 0.5% ADV | — |

## Using them well

* The manual's risk box says **1% risk standard / 0.5% advanced**. The backtest
  deploys full capital per trade, so compare strategies on **win rate, profit
  factor and drawdown**, not just total return.
* The manual exits with stops/targets: set **ATR stop ON**, multiplier ~2, and a
  **take-profit multiple** of 2–3 to mimic the manual's R:R frames.
* Signals are sparse by design (these are selective setups). On a single stock
  expect a handful of trades per year — run them over 3–5+ year windows.
* Verified firing on: OGDC, MCB, HBL, LUCK, FFC, SYS, TRG, PPL, HUBC (Sept 2026 tests).
