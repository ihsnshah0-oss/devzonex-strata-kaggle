# PSX Live & Research — System Status Report

> **2026-10-30 — offline rebuild status.** The v3.19 backup was rebuilt and
> repaired: portal mirror as the data backbone, offline-first ladder,
> `SafeJSONResponse`, mirror-driven heatmap and sector tape, unit-safe
> statements. Build: `./build.sh` → 57 offline tests + `BUILD OK`; runtime:
> 51-route smoke test 51/51 HTTP 200 in ~9 s with `PSX_OFFLINE=1`.
> See `BUILD-NOTES.md` for the defect list and fixes. Everything below
> describes the feature set, which is unchanged.
*Feature audit 2026-10-05; rebuild verification 2026-10-30. Routes below were verified live on port 8111
(wire-by-wire audit: 63 API routes all 200 + every external data wire tested).*

## 1) WHAT IS BUILT & WORKING (✅ done)

### Dashboard (Home) — the star tab, always opens first
- Real Account Brief: 3 minimalist pies (open trades win/loss, closed trades
  success rate, overall book), chips (invested / market value / unrealized /
  realized), and a **"since your last visit" progress line**.
- Market status line, natural-language daily headline, learning quote on
  every open, bento metric cards with sparklines, composite watchlist trend,
  AI alerts feed.
- **🔥 Heatmap tab (master-watchlist treemap):** TradingView-style map of ONLY
  the Master watchlist stocks, grouped by sector — tile size = market cap,
  colour = day change; hover for full per-stock details (price, RSI, SMA trend,
  P/E, yield, mcap, 52-wk, volume, signal); click → research; auto-refreshes
  while the market is open and rebuilds when the Master list is edited.

### Tabs & features
- **Watchlist:** price, day %, RSI, P/E, yield + trend vs the **10/20/50/100/200-day
  averages** (▲/▼ chips, hover for exact values), hover a symbol to see the full
  name, **color flags** (click the dot: red/orange/yellow/green/blue/purple),
  and **multiple lists** — the ⭐ Master list (edited in Settings) plus any
  number of sub-lists that can only contain stocks already in the Master list.
- **Stock:** any PSX symbol, open-source candle chart (3M–5Y), research desk
  (bull/bear/risk), trade proposal (entry/stop/target/sizing), fundamentals,
  company news, **Report tab** (11-section A-to-Z executive report on screen +
  ⬇ PDF), 🌐 PSX Data Portal link beside the price (re-sync + re-analyze).
- **Report & Compare (one tab):** 📄 single-stock 11-section A-to-Z executive
  report on screen + ⬇ PDF, and 🔀 Compare A-to-Z side-by-side for up to 5
  stocks + ⬇ PDF — switch between them at the top of the tab.
- **Screener:** ~546-stock universe, 12 presets with ? explainers, custom filters.
- **Backtest:** **33 strategies** — 6 classics + Stage-2 Breakout + 21 manual
  setups L01–L21 + **6 🗺 MA Playbooks (P1–P6)** built from the Moving-Average
  Strategy Guide mind map (5/21/63-day EMA, 30-week SMA, 52-week EMA, EMA vs
  Wilders filter, RSI divergence, CCI) — see `docs/20-moving-average-playbooks.md`.
  Custom 3–5+ year windows, costs model, ATR stops, equity curve, and an
  **Open position** line when a trade is still held at the end (so the
  win-rate and total return always add up).
- **Trading:** Real Broker Account is the star (add/close/reset trades, live
  P&L, 🤖 advisor, **📤 broker statement PDF upload** — parsed positions shown
  in an editable preview, book replaced only after confirmation); paper trading
  kept collapsed underneath. The **Stock tab** and **Report tab** both carry a
  **⬇ Download PDF** button for that stock's executive report.
- **USER-GUIDE.md** — full feature-by-feature usage guide (simple English).
- **💰 Money (swing-tuned):** swing trading-plan card (capital, risk per trade %,
  target per trade %, stop %, max open swings, max hold days, weekly loss limit),
  position-size calculator tuned to your 25-stock watchlist (reuses the risk
  engine — sizing, R:R, circuit-breaker checks, rounded to PSX 100-share lots),
  swing journal with entry/exit dates, hold-days, %-move, R-multiples and
  commission-deducted P&L, live this-week P&L and weekly-loss-budget tracking,
  STOP banner when the weekly loss limit is hit, an education-only
  martingale/averaging-down ladder with a danger warning (never suggests doubling
  after a loss), and a **📄 Trade Plan PDF** — one click downloads a per-stock PDF
  combining ALL research data + the best-fit strategy (all 33 backtested on it) +
  a trade plan sized by the saved money rules.
- **News (bottom of the Dashboard):** market news + sentiment, PSX announcements,
  company reports — moved from its own tab to the very bottom of the Dashboard;
  🔔 bell notifications with per-browser read state.
- **Settings:** AI engine picker (free model lists per provider), cloud R2
  status, cache manager, and a **📊 Strategy Fit Guide** card — one click
  re-runs every backtest and rebuilds `strategy_fit_guide.pdf`
  ("which strategy is preferred for which stock").

### Data plumbing — every wire tested 2026-10-04
- DPS portal (psxdata): trading-panel, symbols, historical, indices,
  financial-reports, screener, eligible-scrips, debt-market ✅ (with the
  `X-Req-Id` token flow).
- **Sector summary 403 fix:** the system opens
  `https://dps.psx.com.pk/sector-summary`, lifts PSX's token from the page,
  and pulls the sector table with it — works even where PSX blocks the raw
  endpoint; degrades gracefully (no crash) if fully blocked.
- psx.com.pk market-summary ✅ · financials.psx.com.pk filings (47 rows for
  OGDC, 483-row 2026 calendar) ✅ · Yahoo `.KA` history + statements fallback
  ✅ (your home network blocks DPS EOD — this keeps charts alive) ·
  5 news RSS feeds ✅ · OpenRouter public model list ✅.
- Reddit stays disabled (403 by design); SBP stays disabled (401).

## 2) PARTIALLY DONE — needs something from you (🟡)
| Item | Status | What's needed |
|---|---|---|
| AI deep narratives & full AI advisor | wired, idle | Paste a free key (Groq/Gemini/Cerebras/OpenRouter) or run Ollama — Settings → AI. Nothing is pre-stored (your rule). |
| SBP macro data | blocked | SBP API returns 401; needs official auth docs. |
| Cloud R2 | credentials saved, status shown | Cross-device sync not built (was deliberately rolled back with v3.0.0). |

## 3) KNOWN LIMITS (honest list)
- Free data is end-of-day: the mind map's intraday EMAs (78 on 5-min, 130 on
  15-min, 126 on 65-min) are a **manual execution ladder**, not auto-backtested.
- Exotic small-caps may show "—" where no free source publishes the figure.
- Bell read-state is per browser, not synced PC↔phone.
- LUCK prints as LUCKXD (PSX ex-entitlement naming).
- Win-rate counts closed trades; a still-open position is reported separately
  as "Open position … unrealized" (also `(*)` in the Fit Guide).

## 4) RUN IT ON YOUR PC
```
INSTALL.BAT            :: once - checks Python + installs all free packages
RUN.BAT                :: every time - starts on port 8111 + opens browser
RUN.BAT 8005           :: another port if 8111 is taken
set PSX_PORT=8005      :: or via environment variable
STOP.BAT               :: stops the dashboard server
AUTORUN-ON.BAT         :: optional: auto-start on every Windows boot
AUTORUN-OFF.BAT        :: undo the auto-start
run.sh                 :: Linux / Termux (phone)
```
Keep ONE folder only; rename old copies to OLD-BACKUP; always close the black
CMD window before starting again (the server memorizes code at startup).

## 5) SUGGESTED NEXT STEPS (pick any)
1. Paste a free Groq/OpenRouter key → AI advisor + narratives fully live.
2. Dividend calendar / ex-date alerts from PSX announcements.
3. SBP macro widgets once you share the auth docs.
4. Auto-refresh the Fit Guide weekly (script + Settings button already exist).
