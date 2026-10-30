# 06 — How to Screen Stocks (find new ideas)

The screener searches the **545 KSE All-Share (ALLSHR) constituents** and keeps only matches.

## Fast path — one-click presets

1. Open the **Screener** tab (or Home → ⚡ screens).
2. Click a preset card. Done — results appear below.

**What each preset hunts:**

| Preset | Hunts for |
|---|---|
| Fresh Breakout | New 20-day highs + rising volume (rally starters) |
| Volume Shockers | Volume exploding today (something is happening) |
| Momentum Surge | Uptrend + strong RSI + volume (healthy runners) |
| Oversold Bounce | RSI washed out (snap-back candidates — risky) |
| Golden Cross | 50-day average just crossed above 200-day (trend birth) |
| Near 52-Week High | Within 5% of yearly top (leaders) |
| Value Picks | P/E under 10, liquid, decent size (cheap earnings) |
| Dividend Kings | Yield 7%+, profitable, liquid (income) |
| Blue-Chip Quality | KSE-100 + uptrend + pays dividend (safe core) |
| Hidden Accumulation | Volume building but price calm (quiet buying?) |
| Falling Knives | 20-day breakdowns (avoid — or stalk for later) |
| Low Liquidity | Thinnest stocks (trade with care) |

## Custom path — your own filters

1. Fill any boxes (leave the rest empty = "don't care"):
   - **Min/max price, market cap, P/E, yield %** — valuation & size.
   - **Min avg vol** — liquidity guard. Use 100000+ to avoid dead stocks.
   - **Day % / 1Y %** — today's move and long trend.
   - **RSI min/max** — e.g. max 35 = oversold only; min 55 = strength only.
   - **Above 50/200DMA, MACD bullish** — trend yes/no.
   - **Golden cross, breakout, breakdown** — events yes/no.
   - **Min vol ×** — e.g. 2.0 = double normal volume.
   - **Near 52W hi %** — e.g. 5 = within 5% of the top.
   - **KSE-100 only** — big trusted names only.
2. Pick **Sort by** (e.g. `dividend_yield` for income hunting) and **Limit**.
3. Click **Run screen**. First technical run downloads data once (a minute or two);
   after that it answers in seconds. Click any result to research it.

## Example ideas to try

- **Safe income:** `KSE-100 only = Yes`, `Min yield = 7`, sort `dividend_yield`.
- **Bounce hunt:** `RSI max = 32`, `Min avg vol = 200000`, sort `rsi14` (ascending needs API; on dashboard just eyeball lowest RSI).
- **Leaders:** `Near 52W hi % = 5`, `Above 50DMA = Yes`.

## From command line

```bash
python3 -c "
from src.screener import engine as s
d = s.run({'min_yield': 7, 'exclude_zero_pe': True, 'min_avgvol': 100000, 'limit': 5})
print('matches:', d['count'])
for r in d['rows']: print(r['symbol'], r['price'], r['dividend_yield'])"
```
