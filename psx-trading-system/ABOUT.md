# ABOUT — PSX Live & Research: Complete System Document

> Written in simple English. Read this once and you will understand
> **what the system does, what steps it follows, and why.**

---

## 0. What is this system?

**PSX Live & Research** is a free stock-research helper for the **Pakistan Stock Exchange (PSX)**.
It does 5 jobs:

1. **Watches** your stocks (watchlist + live market pulse).
2. **Researches** any stock like a team of analysts (bull case, bear case, debate, verdict).
3. **Plans** trades (entry, stop-loss, targets, how many shares to buy).
4. **Tests** ideas on past data (backtesting) and **finds** new ideas (screener).
5. **Tracks** practice trades in a paper-trading diary (ledger).

It **never buys or sells real shares**. You place real orders yourself in your
broker's app. The system only thinks, calculates, and records.

**Project folder:** `psx-trading-system/`

**Where the numbers come from:** an offline SQLite mirror of the PSX Data
Portal (`data/portal.db`, shipped as `data/psx.db.gz`) answers first when the
internet is down or slow; live portal calls, Yahoo and RSS news are only used
when they actually respond. Nothing is ever invented — if a number is unknown,
the screen shows `—`. How to rebuild and what was fixed is in `BUILD-NOTES.md`.

---

## 1. Big picture — how the system thinks

```text
  DATA SOURCES (free)            BRAINS                      YOU
 ────────────────────      ────────────────────        ─────────────
  DPS PSX portal ─────┐
  Yahoo Finance ──────┼──► DATA ENGINE ──► INDICATORS ──► RESEARCHERS ──► TRADER ──► PROPOSAL ──► Dashboard
  RSS news ───────────┤         │                │              │            │                       (phone/laptop)
  Reddit (public) ────┘         │                │              │            │
                                ▼                ▼              ▼            ▼
                             SCREENER        BACKTEST        RISK checks   LEDGER (paper diary)
```

One line to remember: **Data → Indicators → Researchers → Trader → Proposal → You decide.**

---

## 2. WATCHLIST — the 5 stocks we follow

**File:** `config/watchlist.yaml`

**Purpose:** Tells the whole system which stocks matter most. The dashboard,
research, and defaults all read this one file.

**Starting list (top 5 blue chips, one per core sector)** — the owner has
since expanded this to a 25-stock swing-trading list (banks, oil & gas,
fertilizer, tech, cement, power, consumer) via the Settings tab:

| Symbol | Company | Why it is here |
|---|---|---|
| OGDC | Oil & Gas Development Company | Biggest gas/oil producer, huge dividend payer |
| HBL | Habib Bank Limited | Biggest commercial bank |
| LUCK | Lucky Cement | Cement leader + energy/chemical businesses |
| FFC | Fauji Fertilizer Company | Safe dividend company |
| MEBL | Meezan Bank | Biggest Islamic bank, fast growth |

**SOP (steps the system follows):**

1. On every start, the server reads `config/watchlist.yaml`.
2. If the file is missing or broken, it falls back to OGDC, HBL, LUCK, FFC, MEBL.
3. The Home page shows these 5 with price, RSI, trend, and signal.
4. Research and proposals use the company name from this file for news search.

**Same file also stores settings:** currency (PKR), paper cash (1,000,000),
risk per trade (1%), circuit-breaker % (7.5), commission (0.15%), slippage (0.10%).

**Commands (run inside `psx-trading-system/`):**

```bash
# see your watchlist
cat config/watchlist.yaml

# change it (Windows: use Notepad)
nano config/watchlist.yaml
```

---

## 3. DATA ENGINE — where prices come from

**File:** `src/data/psx_client.py`

**Purpose:** Downloads real PSX data and saves it on your computer (cache),
so the dashboard is fast and we never overload the source websites.

**Sources it uses (all free):**

| Data | Source | How |
|---|---|---|
| Live quotes, market snapshot (545 ALLSHR stocks) | DPS portal `dps.psx.com.pk` | via open-source `psxdata` library |
| Daily history (OHLCV) since 2019 | DPS portal | via `psxdata.stocks()` |
| Index levels (KSE-100, KSE-30, KMI-30…) | DPS homepage cards | parsed directly |
| Official market internals (advance/decline, volume, traded value, trades, status + 8 indices) | `psx.com.pk/market-summary` | parsed directly (`src/data/psx_official.py`, 5-min cache) |
| Official company filings (annual/quarterly reports + PDF links) | `financials.psx.com.pk` | POST `annQtrStmts.php` (`src/data/psx_official.py`) |
| Backup fundamentals/ratios | Yahoo Finance (`OGDC.KA` style) | via `yfinance` |

**SOP — what it does, step by step:**

1. **Quote** (`get_quote`): if a saved quote is fresher than 15 minutes, use it.
   Otherwise download a new one and save it.
2. **History** (`get_history`): if saved history is fresher than 12 hours, use it.
   Otherwise download full history, sort oldest → newest, remove bad rows, save as CSV.
3. **Lite history** (`lite=True`): downloads only ~520 days. Used only by the
   screener so first-time screens stay fast (small file, same math).
4. **Market snapshot**: one row per stock (price, change %, P/E, yield, market cap,
   average volume). Refreshed every 15 minutes. This powers the pulse page + screener.
5. **Index levels**: reads the DPS homepage cards. If that fails, tries Yahoo `^KSE100`.
   If both fail, shows breadth only (never crashes).
6. **KSE-100 list**: downloads the 100 members once a day; strips XD/XR/XB suffixes
   so matching stays stable.

**Cache files (in `data/cache/`):** `quote_*.json`, `eod_*.csv` (full),
`eod_*_lite.csv` (small), `screener.csv`, `sectors.csv`, `indices.json`, `kse100.json`.

**Commands:**

```bash
# live quote for one stock
python3 -c "from src.data import psx_client as psx; print(psx.get_quote('OGDC'))"

# download full history for one stock
python3 -c "from src.data import psx_client as psx; df = psx.get_history('HBL'); print(len(df), 'rows')"

# clear ALL saved data (forces fresh download next time)
python3 -c "from src.data import psx_client as psx; psx.clear_cache()"
```

---

## 4. NEWS — free business headlines

**File:** `src/data/news.py`

**Purpose:** Collects Pakistani business headlines without any paid API.

**Feeds used (all verified working):** Dawn Business, Express Tribune Business,
ARY Business, The News, Dunya News. (Business Recorder and Profit publish no
public RSS feed, so they are excluded.)

**SOP:**

1. Downloads each RSS feed (12-second timeout each; a dead feed is skipped quietly).
2. Keeps title, link, date, and a short summary per story.
3. Saves everything for 30 minutes (cache), so pages load instantly.
4. **Ranks market stories first** using finance keywords (PSX, KSE, rupee, dividend,
   IMF, profit…), because some feeds mix in general news.
5. `get_stock_news(symbol, company)`: filters stories that mention the company
   name or ticker (e.g. "OGDC", "Habib", "Lucky").

---

## 5. SENTIMENT — measuring the mood

**File:** `src/data/sentiment.py`

**Purpose:** Turns words into a number: is the news mood positive or negative?
100% offline — no AI API, no downloads, works without internet after news is fetched.

**SOP:**

1. Keeps two small finance word-lists: ~60 positive words (profit, rally, dividend,
   breakout, upgrade…) and ~60 negative words (loss, crash, downgrade, debt, probe…).
2. `score_text`: counts positive vs negative words, divides by article length,
   returns a score from **-1 (very negative) to +1 (very positive)**.
3. `label`: converts the number to words — Positive / Mildly positive / Neutral /
   Mildly negative / Negative.
4. `analyze_items`: averages all stories and counts how many are positive/negative/neutral.
5. `reddit_mentions`: also tries public Reddit search (`r/FIREPakistan` etc.)
   with **no API key**. Reddit often blocks bots, so failure is silent — the
   system simply continues with news only.

**Commands:**

```bash
# mood of any sentence
python3 -c "from src.data import sentiment as s; print(s.score_text('OGDC profit surges to record on strong growth'))"
```

---

## 6. INDICATORS — the maths on every chart

**File:** `src/analysis/indicators.py`

**Purpose:** Pure maths (no paid library). Turns raw prices into readings like
RSI, MACD, moving averages. Every chart, researcher, screener, and backtest
uses these same functions, so numbers always match everywhere.

**SOP:** `compute_all(df)` adds all columns to the price table; `snapshot(df)`
reads only the **latest day** and returns one dict of readings + true/false flags
(above 50-day average? golden cross today? 20-day breakout?).

**What each indicator means (simple English):**

| Indicator | Simple meaning | How the system reads it |
|---|---|---|
| SMA 10/20/50/200 | Average closing price of last N days | Price above average = uptrend |
| EMA 12/26 | Average that reacts faster to new prices | Used inside MACD |
| RSI 14 (0–100) | Is it overheated or washed out? | >70 overbought (careful), <30 oversold (bounce possible), 50–70 healthy |
| MACD | Difference of two fast/slow averages | MACD above signal line = bullish; fresh cross = stronger |
| Bollinger Bands | Average ± 2× volatility | Touching top band = stretched; bottom band = washed out |
| ATR 14 | Average daily jump size (volatility in rupees) | Sets stop-loss distance; ATR% = ATR ÷ price |
| Stochastic | Where price sits inside the recent high–low range | <25 oversold, >75 overbought |
| OBV | Running total of volume on up-days minus down-days | Confirms if money follows the move |
| ROC 12 | % price change in 12 days | Positive = rising momentum |
| Donchian 20 | Highest high / lowest low of 20 days | Close above = breakout; below = breakdown |
| Volume ratio | Today's volume ÷ 20-day average | ≥1.5× with rising price = strong confirmation |
| 52-week high/low | Highest/lowest close in ~252 trading days | Shows how far price is from the top |
| Support/Resistance | Repeated swing lows/highs of last 120 days | Price often bounces here; used for stops & targets |
| Golden/Death cross | 50-day average crosses 200-day average up/down | Major trend-change signal |

**Commands:**

```bash
# full indicator snapshot for a stock
python3 -c "
from src.data import psx_client as psx
from src.analysis import indicators as ind
print(ind.snapshot(psx.get_history('LUCK')))"
```

---

## 7. RESEARCHERS — the analyst team

**File:** `src/analysis/researcher.py`

**Purpose:** Copies a real research desk: one analyst argues **for** buying,
one argues **against**, then they **debate** and agree on one verdict.

### 7a. Bullish analyst (`bullish_case`) — starts at 50, adds points

| +Points | When |
|---|---|
| +9 | Price above both 50-day and 200-day averages |
| +7 | Golden cross just happened |
| +4 | MACD bullish / fresh MACD cross up (each) |
| +6 | 20-day breakout |
| +4 | RSI 50–70 (healthy) or 3-month gain >10% |
| +3 | RSI 30–45 (bounce setup) or oversold stochastic |
| +5 | Volume ≥1.5× on rising price, or P/E below 12 |
| +4/+2 | News mood positive / dividend yield high |

### 7b. Bearish analyst (`bearish_case`) — starts at 50, adds points

Mirror image: downtrend +9, death cross +7, MACD bearish +4, breakdown +6,
RSI ≥70 +5, distribution volume +5, P/E ≥25 +5, negative news +4,
high volatility +2, no dividend +2, etc.

### 7c. Internal discussion (`internal_discussion`) — the debate SOP

1. `net = (bull − bear) ÷ 2 + 50` → one score 0–100.
2. If scores differ by <8 points → "team is split, be careful."
3. Verdict table: **≥75 Strong Buy · ≥60 Buy · >45 Hold · >30 Sell · else Strong Sell**.
4. Confidence = 30 + distance from 50 + evidence count (max 95).

### 7d. Risk/Reward (`evaluate_risk_reward`) — SOP

1. Stop = lower of (support-1, close − 1×ATR).
2. Target-1 = higher of (resistance-1, close + 1.5×ATR); Target-2 similar with 2.5×ATR.
3. R:R = reward ÷ risk. ≥1.5 = Favourable, ≥1.0 = Fair, else Poor.
4. Also reports the day's circuit-breaker band in rupees (±7.5% of close).

### 7e. Full report (`full_report`) — master SOP

1. Load history → indicators → fundamentals → stock news → news mood.
2. Run bull case + bear case → debate → risk/reward.
3. Return one package: snapshot, fundamentals, news, both cases, verdict, R:R.

**Commands:**

```bash
# full research report for a stock
python3 -c "
from src.analysis import researcher as R
r = R.full_report('FFC', 'Fauji Fertilizer Company')
print(r['discussion'])"
```

---

## 8. STRATEGY — the trader + deep thinking + proposal

**File:** `src/analysis/strategy.py`

**Purpose:** The Trader listens to 6 mini-strategies, blends them with the
researchers' verdict, thinks out loud (Deep Thinking), and writes a
**transaction proposal** you can act on.

### 8a. Strategy votes (`strategy_votes`) — 6 judges

| # | Judge | BUY when | SELL when |
|---|---|---|---|
| 1 | SMA trend | Price > 50DMA and 10DMA > 50DMA | Opposite |
| 2 | RSI regime | RSI <30 (oversold) or >55 (bull zone) | RSI >70 or <45 |
| 3 | MACD | Fresh cross up (strong) or above signal (mild) | Mirror |
| 4 | Donchian breakout | 20-day high breakout | 20-day low breakdown |
| 5 | Bollinger | Tags lower band (washed out) | Tags upper band (stretched) |
| 6 | Volume thrust | Volume ≥2× on up-move | Volume ≥2× on down-move |

Each vote carries a strength (0.2–0.8). No vote → neutral.

### 8b. Trader action (`trader_action`) — the blending SOP

1. Technical bias = weighted votes, squeezed to −1…+1.
2. Research bias = (net score − 50) ÷ 50.
3. **Combined = 0.55 × technical + 0.45 × research.**
4. Action table: **≥0.45 BUY · ≥0.15 ACCUMULATE · ≤−0.45 SELL · ≤−0.15 REDUCE · else HOLD.**

### 8c. Deep Thinking (`deep_think`) — 6 written reasoning steps

1. Regime check (trend + RSI + MACD in one line).
2. Debate result (bull vs bear score).
3. Strategy votes (each judge's call).
4. Risk context (ATR, supports, resistances, R:R).
5. News layer (mood score).
6. Final decision (how the two biases blended into the action).

If you enabled Ollama (local, free AI), step 7 adds a 5-line AI note. If Ollama
is off, nothing breaks — the 6 rule-based steps are the real engine.

### 8d. Transaction proposal (`build_proposal`) — SOP

1. Entry range = close ± 0.5%.
2. Stop/targets come from the researcher's risk/reward.
3. `risk Rs = capital × risk%`; `qty = risk Rs ÷ (entry − stop)` (rounded down).
4. Collects **Buy Evidence** (all bull factors + buy votes) and **Sell Evidence**.
5. Stamp: valid 5 days, swing timeframe (2–8 weeks), education disclaimer.

**Commands:**

```bash
# full trade proposal (Rs 500k capital, 1.5% risk)
python3 -c "
from src.analysis import strategy as S
import json
p = S.build_proposal('MEBL', 'Meezan Bank', 500000, 1.5)
print(p['trader']['action'], json.dumps(p['proposal'], indent=1))"
```

---

## 9. RISK — the safety officer

**File:** `src/analysis/risk.py`

**Purpose:** Checks every trade idea before you risk money. It can say NO
(or "smaller size") even when the trader says BUY.

**SOPs:**

1. **Position size** (`position_size`):
   `qty = (capital × risk%) ÷ (entry − stop)`, but never more than 20% of
   capital in one stock. Reports whether risk-budget or max-position capped it.
2. **Trade check** (`check_trade`) — warns when:
   - R:R below 1.0 → setup rejected (`ok: false`); below 1.5 → thin warning.
   - Position >25% of capital → concentration warning.
   - Single-trade risk >3% of capital → reduce size.
   - Stop above entry (for a long trade) → rejected.
   - Entry outside today's ±7.5% circuit band → warning.
3. **Portfolio heat** (`portfolio_heat`): sums the open risk of all positions.
   ≤6% = OK, ≤10% = HIGH, above = DANGER, cut risk.

**Commands:**

```bash
# check a trade idea
python3 -c "
from src.analysis import risk
print(risk.check_trade('OGDC', entry=320, stop=305, target=345, qty=100, capital=1000000))"
```

---

## 10. BACKTEST ENGINE — the time machine

**File:** `src/backtest/engine.py`

**Purpose:** Tests "what if I traded this rule in the past?" on real PSX history.

**The 6 core strategies (all long-only — PSX has no easy retail shorting).**
Since this document was written the engine also carries the Stage 2 Breakout and all **21 setups from the PSX Long Signal Manual (L01–L21, 📘 prefix)** — see `docs/15-psx-signal-manual-strategies.md`. Since then the **6 🗺 MA Playbooks (P1–P6)** from the Moving-Average Strategy Guide joined as well — `docs/20-moving-average-playbooks.md` (33 total).

| ID | Name | Buys when | Exits when |
|---|---|---|---|
| `sma_cross` | SMA Trend (10/50) | Price + fast SMA above slow SMA | Signal turns off, or ATR stop |
| `rsi_meanrev` | RSI Mean-Reversion | RSI <30 | RSI >55, or ATR stop |
| `breakout` | Donchian Breakout | 20-day high + volume ≥1.2× | ATR stop (no signal exit) |
| `momentum` | Quarterly Momentum | 3-month gain >5% and above 50DMA | Falls below 50DMA, or ATR stop |
| `macd` | MACD Bull | MACD above signal | Signal turns off, or ATR stop |
| `stage2_breakout` | Stage 2 Breakout (52w high + volume) | Weekly close at new 52-week high on ≥1.3× avg weekly volume | Weekly close below 30-week SMA, or ATR stop |

**SOP (how every backtest runs):**

1. Load history for the chosen dates (needs ≥60 days).
2. Walk day by day: check **exits first** (stop/target/signal), then entries.
3. Entries/exits fill at **next day's open** (realistic — no cheating on same-day close).
4. Every fill pays **commission + slippage** (default 0.15% + 0.10% per side).
5. Default safety: **2× ATR stop-loss** under entry; optional take-profit multiple.
6. Records equity daily + every trade (dates, prices, qty, return %, reason).

**Metrics explained simply:** total return, buy-and-hold comparison, CAGR (yearly
growth rate), Sharpe (return per unit of bumpiness), max drawdown (worst fall from
a peak), win rate, profit factor (gross wins ÷ gross losses — above 1.0 = profitable).

**Commands:**

```bash
# backtest RSI strategy on MEBL since 2023
python3 -c "
from src.backtest import engine as bt
r = bt.run('MEBL', 'rsi_meanrev', start='2023-01-01')
print(r['metrics'])"
```

---

## 11. SCREENER — the stock finder

**File:** `src/screener/engine.py`

**Purpose:** Searches the 545 KSE All-Share (ALLSHR) constituents and returns only the ones matching
your rules. Two stages keep it fast.

**SOP:**

1. **Stage 1 (fundamental):** filters the 15-minute market snapshot —
   price, market cap, P/E, dividend yield, average volume, day change, 1-year
   change, sector, KSE-100 membership. No history downloads needed.
2. **Stage 2 (technical):** takes survivors (most liquid first, max 80),
   loads their history (reuses full cache, else small lite cache, 4 at a time),
   computes RSI/SMAs/MACD/volume-spike/52-week position/crosses.
3. Applies technical filters, sorts, returns top N rows.

**The 12 one-click presets:** Fresh Breakout · Volume Shockers · Momentum Surge ·
Oversold Bounce · Golden Cross · Near 52-Week High · Value Picks ·
Dividend Kings · Blue-Chip Quality · Hidden Accumulation · Falling Knives ·
Low Liquidity (Avoid).

**Commands:**

```bash
# KSE-100 liquid stocks, no technicals (instant)
python3 -c "
from src.screener import engine as s
print(s.run({'kse100_only': True, 'min_avgvol': 200000, 'limit': 5, 'include_technicals': False})['count'])"

# pre-download data so presets are instant (run once)
python3 scripts/warm_cache.py 150
```

---

## 12. LEDGER — the paper-trading diary

**File:** `src/paper/ledger.py` · **Database:** `data/psx.db` (SQLite — one file, no server)

**Purpose:** Records your practice trades with real market prices, so every
proposal is tracked honestly. This is the Decision & Execution layer.

**Tables:** `orders` (time, symbol, side, qty, price, note) and `account`
(one row: cash balance).

**SOP:**

1. `place_order`: BUY checks cash; SELL checks you hold enough shares.
   Blank price = fills at the live quote. Writes the order + new cash.
2. `positions`: rebuilds holdings from all orders; values them at live prices;
   computes **realized P&L by FIFO** (first shares bought are first counted sold).
3. `history`: last 100 orders, newest first. `reset`: wipes diary, restores cash.

**Commands:**

```bash
# buy 10 OGDC at live price, then see account
python3 -c "
from src.paper import ledger
print(ledger.place_order('OGDC', 'buy', 10))
print(ledger.positions())"

# reset diary to Rs 1,000,000
python3 -c "from src.paper import ledger; print(ledger.reset(1000000))"
```

---

## 13. SERVER + DASHBOARD — the front door

**File:** `src/app/server.py` · **Pages:** `src/app/static/` (`index.html`, `styles.css`, `app.js`, `charts.js`)

**Purpose:** The server (FastAPI) connects the brains to your screen. It serves
the dashboard and a JSON API. Charts are hand-drawn on `<canvas>` with **zero
outside libraries**, so the dashboard works on any phone/laptop browser, even
on a weak connection.

**API endpoints (full list):**

| Method | Address | What it returns |
|---|---|---|
| GET | `/api/health` | alive? + watchlist |
| GET | `/api/pulse` | indices, breadth, gainers, losers, most-active |
| GET | `/api/watchlist` | 5 blue chips + snapshots |
| GET | `/api/stock/{sym}` | profile + technicals + fundamentals |
| GET | `/api/stock/{sym}/history` | chart bars + SMAs + RSI |
| GET | `/api/stock/{sym}/research` | full analyst-team report |
| GET | `/api/stock/{sym}/proposal?capital=&risk=` | trader action + proposal |
| GET | `/api/stock/{sym}/report` | A-to-Z executive report (JSON) |
| GET | `/api/stock/{sym}/report.pdf` | same report as PDF download |
| GET | `/api/stock/{sym}/news` | stock news + mood |
| GET | `/api/news?limit=` | ranked market news + mood |
| GET | `/api/universe` | 545 ALLSHR symbols (search box) |
| GET | `/api/screener/presets` | 12 presets |
| POST | `/api/screener/run` | `{"filters": {...}}` → matches |
| GET | `/api/backtest/strategies` | 33 strategies |
| POST | `/api/backtest/run` | `{symbol, strategy, …}` → metrics + equity + trades |
| GET/POST | `/api/paper/account`, `/history`, `/order`, `/reset` | paper diary |
| POST | `/api/risk/check` | safety verdict on a trade idea |
| GET | `/api/signals/status` | server PKT time, market OPEN/CLOSED, last-signals timestamps |
| POST | `/api/refresh` | `{"full": false}` → fresh data + recomputed signals + `refreshed_at` |
| GET/PUT | `/api/settings` | read / save all config (watchlist, trading, AI, display) — validated, instant |
| POST | `/api/settings/test-ollama` | checks local AI connection, returns speed or plain-English fix |
| GET/POST | `/api/cache/info`, `/api/cache/clear` | saved-data size / wipe (timestamps kept) |
| GET | `/` | the dashboard · `/docs` = interactive API docs |

**Clock / freshness SOP:** the nav clock ticks in PKT (browser-side). The server stamps
every research/proposal with `generated_at` and records all stamps in
`data/cache/signals_meta.json`. Refresh clears quotes + snapshot + indices + news
caches (history only with `full: true`), rebuilds pulse + watchlist, and stamps
`watchlist_signals_at`. The dashboard then drops its saved reports so everything
recomputes from the new data.

**Commands:**

```bash
# start the system (laptop + phones on same Wi-Fi)
uvicorn src.app.server:app --host 0.0.0.0 --port 8111
# open:  http://localhost:8111   (phone: http://<laptop-ip>:8111)
```

---

## 14. Master SOP — how one BUY is born (end to end)

1. You open a stock → server loads history + snapshot + fundamentals + news.
2. Indicators compute RSI, MACD, SMAs, ATR, supports…
3. Bull analyst scores the good + bear analyst scores the bad → debate → verdict.
4. 6 strategy-judges vote; trader blends votes (55%) + research (45%) → BUY/HOLD/…
5. Deep Thinking writes the 6 reasoning steps.
6. Proposal sets entry ±0.5%, stop, targets, and share count from your risk %.
7. Risk officer re-checks R:R, size, circuit band.
8. You paper-trade it in the Ledger — or place the real order in your broker app.

## 15. Golden rules (system limits — read once)

- Data is 15-min delayed snapshot + daily history — not tick-by-tick.
- Backtests include costs but **cannot predict the future**.
- DPS data is for **personal, non-commercial use**.
- No auto-trading: no retail broker API exists in Pakistan.
- **Education only — not financial advice.** Verify with your broker before real money.

## 16. Glossary (10 words)

**OHLCV** = Open, High, Low, Close price + Volume per day · **EOD** = end-of-day
data · **LDCP** = yesterday's closing price · **Circuit breaker** = max allowed
daily move (±7.5%) · **R:R** = reward ÷ risk · **Drawdown** = fall from a peak ·
**Liquidity** = how easily you can buy/sell · **FIFO** = first-bought shares counted
first · **KSE-100** = top-100 companies index · **Blue chip** = big, trusted company.
