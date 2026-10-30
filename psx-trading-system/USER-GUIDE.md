# 📖 USER GUIDE — PSX Live & Research

*Simple English. Read section 1–2 once, then jump to any tab you want to learn.*

---

## 1. Starting & stopping

| File | When | What it does |
|---|---|---|
| `INSTALL.BAT` | once, first time | checks Python, installs all free packages |
| `RUN.BAT` | every time | starts the dashboard and opens it in your browser |
| `RUN.BAT 8005` | if port 8111 is busy | starts on another port |
| `STOP.BAT` | to stop | kills the server cleanly |
| `AUTORUN-ON.BAT` | optional | Windows starts the dashboard by itself at every boot |
| `AUTORUN-OFF.BAT` | to undo | removes the auto-start |
| `run.sh` | Linux / phone (Termux) | same as RUN.BAT |

The dashboard lives at **http://127.0.0.1:8111** on your PC. On your phone
(same Wi-Fi) open **http://YOUR-PC-IP:8111** — find your PC's IP with
`ipconfig` (Windows). It always opens on the **Dashboard** tab.

Everything is saved in two folders:
- `config\watchlist.yaml` — your settings, watchlist, API keys (keys you paste in Settings)
- `data\` — your broker book, paper account, caches

---

## 2. The top bar (visible on every tab)

- **Clock + market badge** — PSX open/closed state.
- **🔍 Search box** — type any PSX symbol, click a suggestion to open it in the Stock tab.
- **⟳ Refresh** — re-pulls live data.
- **🔔 Bell** — new PSX announcements / news since your last visit. The red badge shows the unread count; when something new arrives the bell **rings**, the badge pops, a **soft chime plays**, and a small pop-up card appears top-right. Click the bell to read the list, mark items read, or allow browser notifications.
- **🔊 / 🔇 Sound button** — next to the bell. Click it to mute or unmute the notification chime; clicking unmute plays a quick test note. Your choice is remembered on that browser.

---

## 3. 🏠 Dashboard (landing page)

Your daily starting point. Everything is **center-aligned** like a briefing page.
From the top:

1. **Market status + daily headline** — a plain-English sentence about today's market.
2. **Real Account Brief** — three small pies (open trades win/loss, closed trades
   success rate, overall book), chips with invested / market value / unrealized /
   realized, and a **"since your last visit"** progress line. This reflects your
   REAL broker book from the Trading tab.
3. **Metric cards** — KSE-100 / ALLSHR index levels, your watchlist's average
   move, market breadth (how many stocks are up vs down), and sentiment.
4. **Watchlist trend strip** — a quick up/down view of your 25 stocks.
5. **AI alerts feed** — rule-based alerts (breakouts, RSI extremes, big moves).
6. **Learning quote** — one trading lesson per open (click it for another).
7. **🤖 Morning brief** — the button under the headline writes a short
   "what to watch today" note over your 25 stocks: your AI engine when it is
   READY, otherwise a rule-based brief (strongest/weakest, oversold, breakouts,
   crosses).
8. **📰 News & Announcements (bottom of the page)** — market mood, finance-ranked
   headlines, 📢 official PSX announcements and 📄 company report filings. This
   used to be its own News tab — it now lives at the very bottom of the Dashboard.

**How to use it:** open after market close, read the headline, check the brief,
then drill into any stock that moved.

---

## 4. ⭐ Watchlist

Your 25 stocks with live prices, day change, RSI, trend vs the
10/20/50/100/200-day averages, P/E, yield, and a quick signal pill on every row.

- **Trend column** — five compact chips per stock: price above (▲) or below (▼)
  each of the **10, 20, 50, 100 and 200-day averages**. Hover any chip for the
  exact rupee value. All five ▲ = strong trend.
- **Hover a symbol** to reveal the company's full name (hidden by default to
  keep the table clean).
- **Color flags** — click the round dot in a row to cycle
  red → orange → yellow → green → blue → purple → clear. Flags are saved and
  visible in every list.
- **Multiple lists:**
  - The **⭐ Master list** is your full 25-stock list. Edit it in
    **Settings → Watchlist** (add/remove/rename). It is always the master.
  - Press **＋ New list** to create sub-lists. A sub-list can only contain
    stocks that are already in the Master list (use the *＋ add stock…*
    dropdown, and ✕ to remove one from that sub-list).
  - **🗑 Delete list** removes a sub-list — its stocks stay in the Master list.
  - **📝 Per-stock notes (sub-lists only)** — in any sub-list, click the
    pencil next to a stock to type a note just for that stock in that list.
    Hover the pencil to read the note; click again to edit or clear it
    (leave the box empty to remove). A small purple dot marks stocks that
    have a note.
  - **🔍 Hover-only indicator line** — hover any row to also see the RSI
    reading (with overbought/oversold label), the MACD reading (bullish ▲ /
    bearish ▼), and **divergence readings for both** (bullish/bearish when
    price and the indicator disagree at the latest swing).
  - **⚡ Today's swing setups** — the panel above the table scans your master
    stocks every refresh and lists the ones in a live swing setup, best first
    (breakouts, SMA crosses, MACD turns, RSI resets). Click one to research it.
  - **🚨 Condition alerts** — tick the rules you care about (RSI <30 / >70,
    crosses above SMA-20/50, 20-day breakout, 2× volume). The bell's 90-second
    poll checks them; matches ring the bell, play the chime and pop up.
  - **⬇ One-page PDF** — one click downloads a printable one-page sheet of all
    25 stocks (price, day/5d/21d %, RSI, trend, P/E, yield, signal).
- Click any row → full Stock research page. The screener, backtester and
  Money tab all know the Master list.

---

## 5. 📊 Stock (the research page)

Everything about ONE stock on one page:

- **Header** — name, live price, day change, 🌐 official PSX Data Portal link,
  and **⬇ Download PDF** (saves this stock's full executive report). Clicking
  the 🌐 portal link opens the official page AND immediately force-fetches the
  latest data for that stock (bypassing all caches), then refreshes the page.
- **Chart** — candles + volume + 20/50/200-day averages. Switch 3M / 6M / 1Y / 5Y.
  Hover any candle for its numbers.
- **Research Desk** — 🐂 bull case, 🐻 bear case, ⚖ risk/reward grade,
  final verdict (BUY / HOLD / SELL) with confidence %.
- **Trade Proposal** — trader action, entry range, stop-loss, targets,
  suggested share quantity (sized by your risk %), and the 🧠 Deep Thinking steps.
- **Fundamentals** — P/E, dividend yield, market cap, performance windows.
- **News** — recent company mentions with a mood score.
- **⟳ Refresh** recomputes everything with fresh data. Each report shows
  **Generated at** so you know how old it is.

---

## 6. 📄 Report & 🔀 Compare (one tab)

The Report and Compare tools now live together in a single **Report & Compare**
tab, with a switch at the top: **📄 Single report** and **🔀 Compare A-to-Z**.

**📄 Single report** — pick a stock → **Generate report** → an A-to-Z document on
screen: executive summary, key stats, trend, signals, quant scorecard, bull vs
bear, trade plan, fundamentals, news, a 3-year backtest check, and deep thinking.
**Download PDF** saves it as a clean 4–5 page file for printing/sharing.

**🔀 Compare A-to-Z** — put up to 5 stocks side by side: price action,
performance, valuation, profitability, growth, debt, technicals, index
membership and the latest official filing, plus a 12-month performance chart and
a combined PDF download.

---

## 7. 🔎 Screener

Scan the whole PSX (~545 stocks):
- Pick a **preset** (12 one-click quant screens — each has a "?" explaining it)
  or build your own filters (price, P/E, yield, volume, RSI, trend…).
- **Run screen** → results table. Click any row to research it.

---

## 8. 📈 Backtest

Test a strategy on history before risking money:
1. Pick **symbol + strategy + start year + capital** (minimum 3–5 years of data).
2. **Run backtest** → total return vs buy-&-hold, Sharpe, max drawdown,
   win rate, profit factor, equity curve, and the full trade list.
3. If the test ends with a trade still open you get an **Open position** line —
   that unrealized gain is inside *Total return* but NOT inside *Win rate*
   (win rate counts closed trades only), so the numbers always add up.

**33 strategies:** 6 classics + Stage-2 Breakout + the 21 📘 setups from your
PSX Long Signal Manual + the 6 🗺 MA Playbooks (P1–P6). All costs included
(0.15% commission + 0.1% slippage per side), ATR-based stops.

In **Settings → Strategy Fit Guide** you can regenerate the PDF that shows
which strategy historically fits which of your stocks.

---

## 9. 💱 Trading tab

### 🏦 Real Broker Account (the star)
Your actual book, seeded from your W615 statement, live P&L at market prices.
- **Add a trade** — symbol, BUY/SELL, qty; leave rate blank to use the live price.
- **Close a position** — red ✕ on any open row (blank qty = close all).
- **🤖 Ask AI** — your live portfolio is assessed by the configured AI engine
  (rule-based notes if no key).
- **📤 Update my stocks from a broker statement (PDF)** — upload your latest
  statement: the dashboard reads the positions, shows an EDITABLE preview,
  and only after your confirmation replaces the book with them. Every position
  becomes an opening BUY at its average cost.
- **↺ Reset** restores the original W615 trades.

### 🧪 Practice (paper) account — collapsed underneath
Fake money, same mechanics. Execute BUY/SELL orders, watch positions and
history, reset to Rs 1,000,000 anytime.

---

## 10. 💰 Money (swing money management)

Re-tuned for **PSX swing trading** — holding a stock for a few days to a few
weeks and selling into strength. No daily-target day-trading logic.

1. **📋 Swing trading plan** — set capital (Rs), risk per trade %, target per
   trade %, stop-loss per trade %, max open swings, max hold days, and a weekly
   loss limit %. Everything else on this tab uses these numbers. A one-line
   summary of your rules is shown under the form.
2. **🧮 Position size calculator** — pick a stock, enter entry / stop / target
   (or press **↺ Fill stop & target from plan %**). It tells you the exact
   shares to buy so that if your stop is hit you lose only your risk %, rounded
   to PSX 100-share board lots, plus reward:risk and rule warnings.
3. **📂 Open swings** — add each live position (qty, entry, stop, target,
   date). The tab shows its last price, open P&L and days held, and warns with
   a banner when a swing is **at stop**, **at target**, or **past your max-hold
   days**. *Close* logs it straight into the journal; ✕ removes it.
4. **📒 Swing journal** — log every closed swing with entry & exit dates, a
   setup/reason note, qty, entry and exit price. It computes hold-days, %
   gain, and an **R-multiple** (% move ÷ your stop %). P&L is net of commission.
   The four cards track Balance, This-week P&L, Win-rate/performance, and how
   much of your weekly loss limit is left.
5. **Discipline guard** — weekly loss limit hit → red STOP banner (no new
   swings until next week); 2+ losses in a row → cooldown warning; a swing held
   past your max days → time-to-re-evaluate nudge. This tab will NEVER suggest
   increasing size after a loss.
6. **📄 Trade Plan PDF** — type ANY PSX symbol → one PDF with ALL research
   data + the best-fit strategy (all 33 backtested on that stock) + a trade
   plan sized by your rules. Great before placing an order and as a record.
7. **🎲 Martingale / averaging-down ladder** — education demo ONLY. It shows
   numerically why doubling after losses (or averaging down a losing swing)
   blows accounts. Never use it.

---

## 11. 🔥 Heatmap (your Master watchlist)

A TradingView-style map of **only your Master watchlist stocks**, grouped by
sector. Tile **size = market cap**, tile **colour = today's % change**
(green up · grey flat · red down), like the PSX map.

- **Hover a tile** for everything: price, change, RSI, 10/20/50/100/200-day
  trend, P/E, dividend yield, market cap, 52-week range, volume vs average,
  ATR and the quick signal.
- **Click a tile** → full research page for that stock.
- The map **refreshes automatically** with the rest of the app while the
  market is open, and it **rebuilds itself whenever you edit the Master list**
  in Settings (add/remove a stock and it appears/disappears here).
- **Today / 1 Week / 1 Month** buttons recolour the map by 1-day, 5-day or
  21-day change — handy for spotting sector rotation.

---

## 12. ⚙ Settings

- **Watchlist** — add/remove symbols (your 25 stocks).
- **AI engine** — pick the provider (Ollama local / OpenRouter / Groq / Gemini /
  Cerebras), see ALL free models of that provider, paste your key manually
  (keys are NEVER stored anywhere except your local `config\watchlist.yaml`).
- **Cloud R2** — optional backup status.
- **Cache** — see + clear cached data.
- **📊 Strategy Fit Guide** — regenerate / download the strategy-fit PDF.
- **💰 Money rules** live on the Money tab itself.

---

## 13. Phone use

Same dashboard: open **http://YOUR-PC-IP:8111** on the phone browser.
Everything works; the layout stacks to one column. Keep the PC running.

---

## 14. Troubleshooting — quick fixes

| Problem | Fix |
|---|---|
| CMD window closes instantly | use the new .BAT files from the latest zip (they pause on every error) |
| "Python not found" / Store opens | install Python from python.org, tick **Add python.exe to PATH**, run INSTALL.BAT |
| Port 8111 busy | `RUN.BAT 8005` |
| Blank prices | check internet; press ⟳ Refresh; PSX portal occasionally rate-limits — wait a minute |
| Charts look empty for a new listing | the stock may have < 3 months of history |
| Forgot what something means | every tab has a **ℹ️ How to use this tab** box at the top |

---

## 15. Mini-glossary

- **RSI (14):** momentum 0–100. Above 70 = hot/overbought, below 30 = washed out.
- **MACD:** trend indicator; bullish when its fast line is above the signal line.
- **ATR:** average daily swing in rupees — used to place sensible stops.
- **SMA 20/50/200:** average price of the last 20/50/200 days (short/medium/long trend).
- **Drawdown:** the worst peak-to-valley drop of an equity curve.
- **Sharpe:** return per unit of risk; higher = smoother ride.
- **Profit factor:** gross wins ÷ gross losses. Must stay above 1.
- **R:R (reward:risk):** what you can win vs what you risk. Aim ≥ 2:1.
- **FIFO:** first-in-first-out — the order used to match your buys and sells.
- **Circuit breaker:** PSX daily price band (~±7.5%); orders outside it won't fill.

---

*Education tool — not financial advice. Past performance never guarantees
future results. Trade small, honor your stops.*
