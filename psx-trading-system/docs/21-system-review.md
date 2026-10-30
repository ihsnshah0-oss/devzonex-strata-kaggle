# Independent System Review — PSX Live & Research (v3.18.0, 2026-10-08)

Reviewed end-to-end: backend, data layer, frontend, agents, docs, launchers.

## What is strong
1. **100% free, no paid APIs** — DPS/PSX scraping, TradingView public scanner, Yahoo `.KA`, RSS. Cross-checks (Yahoo→TV→DPS) protect price integrity.
2. **Complete trader loop** — Dashboard → Watchlist → Research → Screener → Backtest → Paper/Real broker → Money manager → PDF reports. Nothing essential is missing for a swing workflow.
3. **Caching + background agents** — every expensive feed is disk-cached; six analysis agents warm the watchlist at boot so UI/PDF open instantly.
4. **Official-source wiring** — sector tape, eligible scrips, monthly indices, filings, announcements all pulled from exchange pages, labelled with provenance.
5. **Home-deployment ergonomics** — .bat launchers, same-Wi-Fi mobile access, no stored keys, YAML config editable by hand.

## Gaps & risks (honest list)
| # | Gap | Severity | Note |
|---|-----|----------|------|
| 1 | Server binds 0.0.0.0 **without auth/TLS** | High if exposed | Fine on home Wi-Fi; dangerous on any other network. Add basic-auth + HTTPS before ever opening beyond LAN. |
| 2 | Unofficial scraping endpoints (DPS token lift, TV scanner) | Medium | Can break without notice. Mitigated by graceful fallbacks + health check; add an automated daily probe + alert. |
| 3 | No persistent EOD store | Medium | History refetched each session; SQLite (`data/psx.db`) under-used. Store incremental EOD for offline charts + faster backtests. |
| 4 | No automated test-suite | Medium | Regressions (e.g. this week's scope bug) caught by hand. Keep the node scope/canvas probes as a `make test`. |
| 5 | Dividend **history** & ex-date calendar absent | Medium | Only live yield/payout; announcements already contain cash-div declarations — parse into an ex-div calendar. |
| 6 | Valuation assumptions are single-point | Low-Med | One discount rate (14%), FCF proxies for banks. Add sensitivity table (r × g) and a banks-specific excess-return model. |
| 7 | 162 KB monolithic app.js | Low | Works, but maintenance risk; split into ES modules when adding more tabs. |
| 8 | Alerts are in-browser chime only | Low | A swing trader on mobile misses them when the tab is closed; add a free Telegram webhook channel. |
| 9 | No portfolio-level analytics | Low | Sector exposure / correlation across watchlist would complete the money tab. |
| 10 | Qualitative intel curated for ~45 majors only | Low | Others get sector templates + data-driven signals — acceptable, but grow the KB over time. |

## Prioritized suggestions
- **P1** — Optional passcode + HTTPS toggle in Settings (for non-LAN use); daily source-probe with 🔔 alert when a feed dies.
- **P1** — `scripts/selftest.js` (scope + wheel canvas + endpoints) run from STOP/RUN cycle.
- **P2** — Incremental EOD SQLite writer fed by DPS historical; charts/backtest read local first.
- **P2** — Ex-dividend & results calendar parsed from announcements into Dashboard.
- **P2** — DCF sensitivity grid (r 12–16% × g 0–6%) in Deep Analysis + PDF.
- **P3** — Telegram alerts for swing setups & signal flips (user-provided bot token).
- **P3** — Portfolio exposure card (sector weights vs KSE-100 weights) on Money tab.
- **P3** — app.js modular split; CSV export for peers table.

## Verdict
Fit-for-purpose as a personal, free, PSX-only swing-trading cockpit. The data
plumbing is the fragile part — invest next in persistence (P2-3), self-tests
(P1-2) and an auth toggle (P1-1) before adding more features.
