# FAQ — Quick Answers

**Is everything really free?**
Yes. Data (DPS portal, Yahoo, RSS), code libraries, and the optional AI (Ollama)
are all free. You pay nothing to anyone.

**Does it trade automatically with real money?**
No — and it cannot. No retail broker in Pakistan offers an order API.
You place real orders in your broker's app; the system plans + tracks.

**How fresh is the data?**
Market snapshot refreshes every 15 minutes; history refreshes every 12 hours;
news every 30 minutes. Fine for daily/swing decisions, not for second-level scalping.

**Why is a stock missing from the screener?**
It may be suspended, newly listed (<60 days), or filtered out by your rules.
Loosen filters or search it directly.

**Why do RSI numbers differ slightly from my broker app?**
Different apps use slightly different formulas/day-counts. Ours is Wilder's
standard RSI on DPS end-of-day data. Direction and zones matter more than decimals.

**Can I add more than 5 watchlist stocks?**
Yes — unlimited. See guide 08. But 5–10 keeps you focused.

**Can I use it without internet?**
Partly. Saved (cached) data, research, backtests, and paper diary work offline.
Fresh prices, news, and new symbols need internet.

**Where is my data stored?**
`data/cache/` (downloaded market data) and `data/psx.db` (paper diary).
Both stay on your computer. Copy the folder = full backup.

**Is this financial advice?**
No. Education and research assistance only. Always verify with your broker
and never risk money you cannot afford to lose.

**Who can I share this with?**
Anyone, for personal use. DPS data is for non-commercial use — don't sell
the data or charge others for access to a hosted copy.
