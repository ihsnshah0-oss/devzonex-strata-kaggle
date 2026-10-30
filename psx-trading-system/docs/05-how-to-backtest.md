# 05 — How to Backtest (test ideas on past data)

Backtesting asks: *"If I traded this rule in the past, what would have happened?"*

## Steps (dashboard)

1. Open the **Backtest** tab.
2. Choose **symbol** (start with your watchlist: OGDC, HBL, LUCK, FFC, MEBL).
3. Choose **strategy** (explained below).
4. Set **dates** — use at least 2–3 years so the test sees good and bad markets.
5. Set **capital** (e.g. 1000000) and **ATR stop** (2.0 = normal; 1.5 = tight; 3.0 = loose).
6. Click **Run backtest** and read the results.

## The 6 core strategies in simple words

| Strategy | Idea in one line | Best when |
|---|---|---|
| SMA Trend (10/50) | Stay invested while price rides above its averages | Long steady trends |
| RSI Mean-Reversion | Buy panic dips (RSI<30), sell relief (RSI>55) | Sideways, jumpy markets |
| Donchian Breakout | Buy new 20-day highs on strong volume | Fresh rallies starting |
| Quarterly Momentum | Buy what rose >5% in 3 months and holds trend | Bull markets |
| MACD Bull | Stay long while MACD is above its signal | Smooth trends |
| **Stage 2 Breakout** ⭐ | Weekly close at new 52-week high on ≥1.3× volume; exit on weekly close below 30-week SMA | **1–6 week swing trades (backtest-verified winner)** |

## 📘 Plus 21 setups from your PSX Long Signal Manual

The dropdown also lists every setup from your signal manual with a 📘 prefix —
L01 Trend Pullback, L02 Breakout+Retest, L05 52-Week High, L10 Spring, the ICT
setups (L13–L16), L19 Wyckoff LPS, L20 Stopping Volume, and more. Each is the
manual's Stage-2 buy trigger coded for daily bars. Full table, mapping notes and
tuning tips: **docs/15-psx-signal-manual-strategies.md**.

## How to read results

- **Total return vs Buy & hold:** did the strategy beat doing nothing? Be honest here.
- **CAGR:** average yearly growth. Above ~15% on PSX history is decent.
- **Sharpe:** return per bumpiness. Above 1.0 is good; below 0 means pain without pay.
- **Max drawdown:** worst fall from a peak. Can you survive −30%? If not, skip it.
- **Win rate:** % of winning trades. 40–60% is normal; win rate alone means little.
- **Profit factor:** gross wins ÷ gross losses. **Must be above 1.0** or the strategy loses.
- **Equity curve:** should climb from left to right with small dips, not one lucky jump.
- **Trades list:** check *why* exits happened (signal-off is normal; all stops = too tight).

## Honest-testing rules

1. Every fill already includes commission + slippage — that is realistic, keep it.
2. Test on **more than one stock** before trusting a strategy.
3. A strategy that only wins in one year is luck, not skill.
4. Past profit never guarantees future profit. Backtests kill bad ideas — that is their job.

## Same backtest from command line

```bash
python3 -c "
from src.backtest import engine as bt
r = bt.run('OGDC', 'sma_cross', start='2022-01-01', capital=1000000)
print(r['metrics'])"
```

## 🗺 MA Playbooks (P1–P6)

Six indicator playbooks built from the Moving-Average Strategy Guide mind map
(see `docs/20-moving-average-playbooks.md` for the full rules): momentum rides
on the 5/21-day EMAs with CCI, swing cycles on 21/63 with RSI divergence,
quarter+stage buys (63 EMA + 30-week SMA), weekly major-cycle shifts
(30-week SMA + 52-week EMA), the EMA-vs-Wilders trend filter, and the
RSI-divergence bounce. Pick them in the Strategy dropdown like any other.

## "Open position" line

If the test ends while a trade is still open, the results show an extra
**Open position … unrealized** stat. That gain is inside *Total return* but
not inside *Win rate* (win rate counts closed trades only) — so the numbers
always add up.
