# 13 — Daily Routine SOP (your 15-minute habit)

PSX trades Monday–Friday, 9:30 AM–3:30 PM (PKT). Weekends: market closed,
but research/backtesting still work on saved data.

## Morning (before 9:30 AM) — 5 minutes

1. Start the server (if not running):
```bash
cd psx-trading-system
uvicorn src.app.server:app --host 0.0.0.0 --port 8111
```
2. Open Home → read **market pulse**: indices up or down? breadth positive?
3. Open **News** → market mood? Any big story (IMF, rates, oil, politics)?
4. Glance at **watchlist signals** — anything flipped to BUY/SELL overnight?

## Midday (optional peek) — 2 minutes

- Home → **Most Active**: where is today's money going?
- If you hold paper positions: Paper tab → any stop/target close to hitting?

## Evening (after 3:30 PM, data settles) — 8 minutes

1. Re-check watchlist (fresh closing snapshot).
2. Run 2–3 presets: **Fresh Breakout**, **Oversold Bounce**, **Volume Shockers**.
3. For 1–2 interesting names: full **Research + Proposal** (guide 04).
4. Log paper trades for ideas you believe in; SELL paper positions that hit stop/target.
5. Write one line per trade in a notebook: *why you took it, where you're wrong.*

## Weekend (30 minutes, the real edge)

1. Backtest one strategy on 2–3 stocks (guide 05). Keep what survives costs.
2. Review paper diary: win rate? Did you honor stops? What would you repeat?
3. Run **Dividend Kings** + **Value Picks** for slow-wealth ideas.
4. Warm the cache for next week:
```bash
python3 scripts/warm_cache.py 150
```

## Standing rules

- No trade without a written stop. No exceptions.
- Risk ≤1–2% per idea; total heat ≤6%.
- A red market day is for watching, not heroics — the screener keeps your list ready.
