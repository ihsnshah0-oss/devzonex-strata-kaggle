# Start Here — Guide Index

Welcome! Everything is written in **simple English**.

## 🛠️ What you can use this system for

- **Daily swing-trading research** — open it after close, see proposals/signals for your 25 stocks, read AI-style trade notes
- **Find new ideas** — screen all 545 ALLSHR stocks by price, volume, RSI, momentum, MAs
- **Validate strategies before risking money** — backtest any of the 33 strategies over 3–8 years with real costs
- **Practice risk-free** — paper-trade signals with fake rupees
- **Stay ahead of events** — announcements feed tells you about board meetings, results dates, payouts for your holdings
- **Generate/share PDF reports** on any stock
- **Run anywhere free** — laptop via `RUN.BAT`, phone via browser on the same Wi-Fi

## 📖 The guides — read in this order

| # | Guide | What you will learn |
|---|---|---|
| ★ | `../USER-GUIDE.md` | **START HERE** — how to use every tab & feature in detail, launchers, phone, troubleshooting |
| 0 | `../ABOUT.md` | **The complete document** — what every part of the system does and what steps it follows |
| 1 | `01-installation-guide.md` | Install on Windows, Mac, or Linux + first run |
| 2 | `02-phone-setup-guide.md` | Open the dashboard on your mobile |
| 3 | `03-dashboard-tour.md` | What each tab does (Home, Stock, Report, Screener, Backtest, Paper, News, Settings) |
| 4 | `04-how-to-research-a-stock.md` | Read a research report like a pro |
| 5 | `05-how-to-backtest.md` | Test strategies on past data |
| 6 | `06-how-to-screen-stocks.md` | Find new stock ideas with filters |
| 7 | `07-how-to-paper-trade.md` | Practice trading with fake money |
| 8 | `08-how-to-change-watchlist-and-settings.md` | Change stocks, cash, risk % |
| 9 | `09-how-to-enable-ollama-ai.md` | Add free local AI notes (optional) |
| 10 | `10-api-guide.md` | Use the system from code/curl |
| 11 | `11-troubleshooting-guide.md` | Fix common problems |
| 12 | `12-developer-guide.md` | Add your own indicator, strategy, or filter |
| 13 | `13-daily-routine-sop.md` | Suggested 15-minute daily habit |
| 15 | `15-psx-signal-manual-strategies.md` | The 21 PSX Long Signal Manual setups (L01–L21) for backtesting |
| 17 | `17-data-sources-and-links.md` | Every PSX link you shared — which ones the system fetches data from, and why the rest were skipped |
| 14 | `FAQ.md` | Quick answers |

**The 3 commands you need most:**

```bash
cd psx-trading-system
pip install -r requirements.txt
uvicorn src.app.server:app --host 0.0.0.0 --port 8111
```

Then open `http://localhost:8111` in your browser.
