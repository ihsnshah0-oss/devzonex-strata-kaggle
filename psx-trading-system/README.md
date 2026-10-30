# PSX Live & Research — Free & Open-Source Trading System for PSX

A complete research → strategy → risk → execution loop for the **Pakistan Stock Exchange**,
built exactly on your mind-map architecture, with every paid/proprietary block swapped for a
**free, open-source** equivalent. Runs on your laptop and your phone (same Wi-Fi).

Watchlist: **25 swing-trading stocks** (banks, oil & gas, fertilizer, tech,
cement, power, consumer — see `config/watchlist.yaml`). Change it anytime in
the ⚙ Settings tab — everything keys off that file.

## 🛠️ What you can use this for

- **Daily swing-trading research** — open it after close, see proposals/signals for your 25 stocks, read AI-style trade notes
- **Find new ideas** — screen all 545 ALLSHR stocks by price, volume, RSI, momentum, MAs
- **Validate strategies before risking money** — backtest any of the 33 strategies (6 core + 21 manual setups + 6 MA playbooks) over 3–8 years with real costs
- **Practice risk-free** — paper-trade signals with fake rupees
- **Stay ahead of events** — announcements feed tells you about board meetings, results dates, payouts for your holdings
- **Generate/share PDF reports** on any stock
- **Run anywhere free** — laptop via `RUN.BAT`, phone via browser on the same Wi-Fi

## Your architecture → what was built

| Mind-map block | Original (paid/limited) | Free / OSS replacement in this build |
|---|---|---|
| Market data | Yahoo Finance, Charts | DPS PSX portal via **`psxdata`** (OSS) + yfinance `.KA` fallback + own canvas charts |
| Social media | X / Reddit APIs (paid) | Public Reddit JSON (keyless, `r/FIREPakistan`) + offline lexicon sentiment |
| News | Bloomberg / FinHub / Reuters (paid) | Free RSS (Dawn, Tribune, ARY, The News, Dunya) **+ Investify.pk aggregator** (Recorder, Mettis, Profit…) + 📢 official PSX company announcements with original PDFs |
| Fundamentals | Profile / History / Transactions | DPS company pages + EOD history stats + Yahoo ratios |
| Researcher Team | Bullish / Bearish / Discussion / Risk-Reward | `src/analysis/researcher.py` — transparent scoring analysts |
| Trading Strategy | Trader + "OpenAI deep thinking" | `src/analysis/strategy.py` — Trader voter + **rule-based Deep Thinking** (+ optional local Ollama LLM) |
| Risk Management | — | `src/analysis/risk.py` — sizing, R:R guard, PSX circuit-breaker check, portfolio heat |
| Decision & Execution | — | Paper-trading ledger (SQLite) — no retail broker API exists in PK, so fills simulate at live prices |
| Backtesting | (your add-on) | `src/backtest/engine.py` — **33 strategies**: 6 core incl. Stage 2 Breakout + 21 📘 setups from your PSX Long Signal Manual + 6 🗺 MA Playbooks (P1–P6, mind-map edition), ATR stops, costs, full stats |
| Screener | (your add-on) | `src/screener/engine.py` — 20+ filters + 12 one-click quant screens |
| Money Management | binary-options martingale sheet | `src/analysis/money.py` — trading plan + position sizing + trade journal + discipline guard (PSX stocks, PKR, no martingale) |

## 📚 Guides & documents (all in simple English)

- **`USER-GUIDE.md`** — START HERE: how to use every tab and feature in detail,
  the launcher files, phone setup, troubleshooting quick-fixes, mini-glossary.
- **`ABOUT.md`** — the complete document: what every module does and the exact
  steps (SOP) it follows — watchlist, data engine, news, sentiment, indicators,
  researchers, strategy, risk, backtest, screener, ledger, server.
- **`docs/00-start-here.md`** — index of all step-by-step guides:
  installation, phone setup, dashboard tour, research, backtest, screener,
  paper trading, settings, Ollama AI, API, troubleshooting, developer guide,
  daily routine, signal-manual strategies, FAQ.
- **`docs/17-data-sources-and-links.md`** — every PSX link you shared,
  triaged: which ones the system fetches data from, which were reviewed
  and skipped (and why), and which are learning/reference bookmarks.

## Rebuild from source (v3.19 backup → working install)

The archived drop is not runnable as-is: it reaches for the network on every
route, has NaN serialisation crashes, a mirror/ledger filename collision, a
1000× market-cap unit bug and a TradingView dependency. `BUILD-NOTES.md`
lists all 16 defects and their fixes.

```bash
cd psx-trading-system
./build.sh              # venv → deps → static checks → 57 tests → BUILD OK
./build.sh --fast       # venv already populated

# run it (offline mode — uses the PSX Data Portal mirror)
PSX_OFFLINE=1 .venv/bin/uvicorn src.app.server:app --host 0.0.0.0 --port 8111
```

- `BUILD-NOTES.md` — what was broken, what was fixed, how it is verified
- `tests/test_offline_data.py` — 57 tests that run with the network switched off
- `scripts/verify_build.py` — pre-flight check, prints `BUILD OK`

The app reads the same file the repo ships as `data/psx.db.gz`: an offline
SQLite mirror of **dps.psx.com.pk** (754 symbols, 235,583 daily bars,
2016-10-31 → 2026-10-29, KSE-100 + KMI-30 memberships). Live data is used when
it is available, the mirror when it is not, and the dashboard never goes blank.

## Quick start (laptop)

**Windows:**
1. **`INSTALL.BAT`** — run once: checks Python and installs all free packages.
2. **`RUN.BAT`** — run every time: starts the server and opens
   `http://localhost:8111`. Port changeable: `RUN.BAT 8005` / `set PSX_PORT=8005`.
3. **`STOP.BAT`** — stops the server. **`AUTORUN-ON.BAT`** (optional) makes it
   start by itself on every Windows boot; **`AUTORUN-OFF.BAT`** undoes that.

**Mac/Linux:** `./run.sh`. Or manually, all systems:

```bash
cd psx-trading-system
pip install -r requirements.txt
uvicorn src.app.server:app --host 0.0.0.0 --port 8111
# open http://localhost:8111
```

Or just `./run.sh`. On Windows: `pip install -r requirements.txt`, then
`python -m uvicorn src.app.server:app --host 0.0.0.0 --port 8111`.

**First-run speed tip:** technical screens fetch each symbol's history once, then cache it.
To make every preset instant from the start, pre-warm the cache (takes a few minutes,
run it once):

```bash
python3 scripts/warm_cache.py 150
```

## On your phone

1. Connect phone to the **same Wi-Fi** as the laptop.
2. Find laptop IP (`ipconfig` on Windows / `ifconfig` on Mac/Linux, e.g. `192.168.1.5`).
3. Open `http://192.168.1.5:8111` in the phone browser. The dashboard is mobile-responsive.

## What you need to do yourself (I can't do these for you)

- **Install Python 3.11+** on your laptop (psxdata needs it).
- **Run the server** — data refreshes automatically; first screener/backtest run downloads
  history once, then it's cached in `data/cache/`.
- **(Optional) Local AI narratives**: install [Ollama](https://ollama.com), run
  `ollama pull llama3.1`, set `ollama.enabled: true` in `config/watchlist.yaml`. Without it,
  the built-in reasoning engine does everything — nothing breaks.
- **Real orders are manual**: place them in your broker app (SCS, IMS, Investify…);
  log them in the Paper Trade tab to track honestly. PSX/DPS data is for **personal,
  non-commercial use** (see DPS legal notice) — this system is exactly that.

## API (for tinkerers)

`GET /api/pulse` · `GET /api/watchlist` · `GET /api/stock/{sym}` ·
`GET /api/stock/{sym}/research` · `GET /api/stock/{sym}/proposal` ·
`POST /api/screener/run` · `POST /api/backtest/run` · `POST /api/paper/order` ·
`POST /api/risk/check` — full docs at `http://localhost:8111/docs`.

## Disclaimer

Education only — not financial advice. Backtests don't predict the future.
Verify everything with your broker before risking real money.
