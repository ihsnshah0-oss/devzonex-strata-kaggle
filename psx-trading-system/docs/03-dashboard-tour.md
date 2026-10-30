# 03 — Dashboard Tour (what each tab does)

Open `http://localhost:8111`. Top bar has search + 6 tabs.

## 🕐 Clock, market badge, signals time, Refresh (top bar)

- **Clock:** live Pakistan time (PKT), ticks every second.
- **Market badge:** green `● MARKET OPEN` during trading hours (Mon–Fri 9:30–15:30 PKT),
  otherwise `○ MARKET CLOSED` with a note (pre-open / post-close / weekend).
- **Signals time:** when watchlist signals were last computed, e.g. `Signals: 10 Sep, 15:59:49`.
- **⟳ Refresh button:** fetches the latest quotes, market snapshot, indices, and news,
  then recomputes all signals and reloads the current view. Research/Proposal reports
  each show their own `Generated … PKT` line. (History is daily data — a full
  re-download is rarely needed; API users can `POST /api/refresh` with `{"full": true}`.)

## ℹ️ In-dashboard help

Every tab starts with a yellow **"How to use this tab"** box — click it to expand
steps + how-it-works for that exact tab. The details below are the same content.

## 🔍 Search (top bar)

- Type any symbol (`LUCK`, `SYS`, `FFC`) and press Enter → jumps to that stock.
- Shortcut: `Ctrl+K` (or `Cmd+K` on Mac) focuses the search box.

## ⚙ Settings

- The 7th tab. Change **everything** without coding: watchlist, trading defaults,
  AI on/off, auto-refresh, cache, paper reset. Full details in guide 08.
- Every save validates your input and explains mistakes in plain words.

## ⭐ Watchlist (tab)

- **Trend column:** five compact chips per stock — price above (▲) or below (▼)
  each of the 10/20/50/100/200-day averages. Hover a chip for the exact value.
- **Hover a symbol** to reveal the company's full name.
- **Color flags:** click the round dot to cycle red/orange/yellow/green/blue/purple.
- **Multiple lists:** ⭐ Master (the full list, edited in Settings) + sub-lists
  made with **＋ New list**. Sub-lists can only hold Master-list stocks;
  add with the *＋ add stock…* dropdown, remove with ✕, delete a sub-list with 🗑.

## 🏠 Dashboard (landing page — Stalwart design)

The dashboard opens as a calm, dark landing screen and reveals its data as you scroll:

1. **Fold 1 — the AI Pulse Ring:** a breathing ring at the top.
   - Emerald glow = stable market, long bias.
   - Amber glow = high volatility, defensive stance.
   Below it: a one-sentence natural-language market read (positions tracked,
   sentiment, whether you need to act) and a daily discipline quote.
2. **Fold 1.5 — the data bento grid:** four big-number cards (KSE-100 move,
   value traded, breadth, watchlist average). **Hover (or tap) a card** to
   expand it and see the sparkline + the exact stocks driving the number.
   Beside it: the **AI Price Trend** chart (your watchlist composite, indexed
   to 100) and the **Recent AI Alerts** feed (official PSX filings).
3. **Fold 2 — Sector Heatmap:** uniform tiles grouped by sector across the
   ALLSHR universe. Hover a tile for its directional confidence score; click
   it to open full research.
4. **Fold 3 — Deep dives (everything from before, restyled):** index strip +
   official market internals, **Blue-Chip Watchlist** (price, day change, RSI,
   10/20/50/100/200-day trend chips, P/E, yield, quick signal, color flags,
   multiple lists — click any row for full detail),
   Today's market (Gainers / Losers / Most Active), and one-click screens.
5. **Fold 4 — 📰 News & Announcements (at the very bottom):** market mood +
   headlines, 📢 PSX announcements, 📄 company report filings (moved here from
   the old News tab).

## 📊 Stock (detail page)

- Header: price, day change, verdict pill (after research loads).
- **Chart:** candles + volume + SMA 20/50/200 lines. Switch 3M / 6M / 1Y / 5Y.
  Hover any candle to see its numbers.
- **Stat boxes:** RSI, MACD, trend, ATR, volume ×, 52-week range, support/resistance.
- Beside the price: 🌐 **PSX Data Portal** link and a **⬇ Download PDF** link
  that saves that stock's full A-to-Z executive report.
- **Sub-tabs:**
  - *Research Desk* → bull case, bear case, debate, verdict, risk/reward.
  - *Trade Proposal* → trader action, entry/stop/targets/qty, buy & sell evidence, Deep Thinking steps.
  - *Fundamentals* → valuation, performance windows, ratios, data sources.
  - *News* → company mentions + mood score.

## 📄 Report & Compare (one tab)

A switch at the top of the tab chooses the mode:

**📄 Single report** — pick any watchlist stock → **Generate report** → full
A-to-Z analysis on one page: executive summary, key stats, trend, signals,
quant scorecard, bull vs bear, trade plan, fundamentals, news, 3-year backtest
check, deep thinking. **Download PDF** saves it as a clean 4–5 page document.

**🔀 Compare A-to-Z** — add up to 5 stocks → side-by-side price, performance,
valuation, profitability, growth, debt, technicals, index membership, latest
filing + a 12-month performance chart + combined PDF download.

## 🔎 Screener

- Filter form (price, P/E, yield, volume, RSI, trend…) + preset cards on top.
- **Run screen** → results table. Click a row to research it.

## 📈 Backtest

- Pick symbol + strategy + dates + capital → **Run backtest**.
- Read: return vs buy-and-hold, Sharpe, drawdown, win rate, equity curve, trade list.

## 💰 Paper Trade

(Trading tab) The **🏦 Real Broker Account** panel is the star: add/close
trades, live P&L, 🤖 AI advisor, and **📤 Update my stocks from a broker
statement (PDF)** — upload your statement, check the detected positions in an
editable preview, then Apply (each becomes an opening BUY at avg cost).

- Top cards: equity, cash, invested, realized profit.
- Order form: symbol, BUY/SELL, qty, price (blank = live price) → Execute.
- Positions table + full order history. **Reset** restores Rs 1,000,000.

## 💰 Money (money management)

Tuned to YOUR watchlist and PKR — the anti-martingale version of a trading
plan. Four cards up top: Balance, Today P&L, Daily target, Daily loss limit.

- **📋 Trading plan:** set capital, daily target %, risk per trade %, daily
  loss limit %, max open positions. **Save plan.**
- **🧮 Position size calculator:** pick a stock + entry/stop/target →
  it tells you exactly how many shares to buy to respect your risk rule,
  plus reward:risk and rule warnings (uses the same risk engine as proposals).
- **📒 Trade journal:** log each closed trade (symbol, qty, entry, exit, date).
  P&L is net of commission. Delete with ✕.
- **Discipline guard:** when your daily loss limit is hit, a red **STOP** banner
  appears; a losing streak of 2+ shows a "don't revenge-trade" warning; hitting
  the daily target shows a "consider stopping while ahead" note.
- **📄 Trade Plan PDF:** type ANY PSX symbol → one downloadable PDF with ALL its
  research data (verdict, technicals, fundamentals, news), the **best-fit
  strategy** (all 33 backtested on that stock), and a trade plan sized by YOUR
  saved money rules. Takes ~15–30 s to build.
- **🎲 Martingale ladder (education only):** shows how the doubling-after-loss
  idea blows up. It is a warning, not a strategy.

## 📰 News & Announcements (bottom of the Dashboard)

No longer a separate tab — it is the last fold on the Dashboard page:

- Market mood + finance-ranked headlines from Dawn, Tribune, ARY, The News, Dunya,
  plus the **Investify.pk** aggregator (Dawn, Tribune, Recorder, Mettis, Profit) linking to the original articles.
- **📢 PSX Announcements** pane — official company filings (board meetings, results, payouts, AGMs,
  insider buys) summarized by Investify with links to the original PSX PDFs. Tick *My watchlist only*.
- **📄 Company Reports** pane — newest annual/quarterly filings calendar.
- Click any headline to read the full story on the source site.
