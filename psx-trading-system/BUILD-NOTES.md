# BUILD NOTES — rebuilding PSX Live & Research from the v3.19 backup

This file explains how the system is built today and exactly what had to be
repaired to get it from the archived `psx-trading-system_BACKUP_2026-10-08_v3.19`
drop to a working installation. Keep it next to the code: when the app is
restored on another machine, this is the checklist.

---

## 1. Build it

```bash
cd psx-trading-system
./build.sh              # venv → dependencies → static checks → tests → verification
./build.sh --fast       # skip dependency install when .venv already has them
```

`build.sh` stops on the first failure and prints what broke. Its last step is
`scripts/verify_build.py`, which answers the only question that matters —
*can this install serve the desk right now?* — and ends with `BUILD OK` or a
list of problems.

Run the server:

```bash
PSX_OFFLINE=1 .venv/bin/uvicorn src.app.server:app --host 0.0.0.0 --port 8111
```

`PSX_OFFLINE=1` forces the offline data ladder, which is how the system is
verified here (this sandbox has no route to `dps.psx.com.pk`). Without it the
app tries the live portal first and falls back to the mirror automatically.

Windows users keep using `INSTALL.BAT` → `RUN.BAT` → `STOP.BAT`; those call the
same Python app.

---

## 2. Where the data comes from

`data/portal.db` is a SQLite mirror of **dps.psx.com.pk**, produced by the
portal ingest job in the parent repository and shipped compressed as
`data/psx.db.gz` (7.5 MB). On first use `src/data/mirror.py` finds the gzip
(local `data/portal.db.gz`, `data/psx.db.gz`, then `../data/psx.db.gz`) and
expands it to `data/portal.db`.

Tables: `company_snapshots`, `eod_bars`, `index_bars`, `index_memberships`,
`symbols`, `company_financials`.

Current contents: **754 listed symbols, 103 with price history, 235,583 daily
bars from 2016-10-31 to 2026-10-29, 18 indices, 3,992 financial rows**, KSE-100
= 100 members, KMI-30 = 30.

The mirror is deliberately **not** `data/psx.db` — that filename belongs to the
paper-trading ledger (account, orders, trades). Conflating the two was one of
the original bugs; `verify_build.py` now asserts they are different files.

### Data ladder (`src/data/psx_client.py`)

```
fresh disk cache  →  portal mirror  →  live psxdata/DPS  →  Yahoo .KA  →  stale cache
```

A ten-minute connectivity circuit breaker stops every request from paying a
timeout when the network is down, and `PSX_OFFLINE=1` skips the live rungs
entirely. The mirror usually wins anyway: it carries ten years of bars where
the live path pulls a couple of years.

---

## 3. What was broken in v3.19 and how it was fixed

| # | Symptom in the backup | Cause | Fix |
|---|---|---|---|
| 1 | Dashboard empty without internet; 17 of 47 routes failed | Everything routed straight to live HTTP | Wrote `src/data/mirror.py` (portal SQLite reader) and rebuilt `psx_client` around an offline-first ladder |
| 2 | `HTTP 500 … Out of range float values` on random endpoints | NaN/inf reached `json.dumps` | `SafeJSONResponse` + `_json_safe()` scrub at the response boundary; set as `default_response_class` |
| 3 | App crashed at import on a minimal install | `import feedparser` unguarded | Guarded optional imports (`feedparser`, `psxdata`, `yfinance`) |
| 4 | `data/psx.db` overwritten / ledger lost | Mirror reused the ledger filename | Mirror is `data/portal.db(.gz)`; verifier enforces separation |
| 5 | Total market cap ≈ 41 *quadrillion* PKR | 562 of 754 portal caps stored in thousands | `_fix_market_cap()` normalises units; mcap source recorded per symbol |
| 6 | P/E showed `—` and sector showed `—` for real stocks | Degraded/offline results were cached for an hour | `_worth_caching()` — only cache payloads that carry a price; stale `fund_*.json` deleted |
| 7 | Fundamentals sector read `Sector 820` | Portal sends numeric sector codes | `_sector_name()` resolves code → portal name via the sectors table, then the snapshot label |
| 8 | Sector filter in the screener returned nothing | UI sent names, engine compared codes | `_sector_key()` normalises `"0820"`, `820`, `820.0` and names on both sides |
| 9 | Heatmap blank when TradingView was unreachable | Heatmap called a third-party scanner | Rebuilt from the mirror (`mirror.snapshot()` + `mirror.week_changes()`), 96 of 100 tiles on the current capture |
| 10 | Sectors tab took minutes, then showed nothing | TradingView scanner in 180-symbol chunks, 25 s each | `_sector_tape()` builds the same row shape from the mirror, cached 15 min |
| 11 | `/api/market/overview` empty whenever psx.com.pk was slow | Scrapes one URL, returns `{}` on failure | Mirror fallback computes breadth, volume, traded value and index levels |
| 12 | Market summary / DPS company page calls hung offline | No connectivity gate | `network_up()` circuit breaker; DPS fetch only when the network is up |
| 13 | Statements crashed on short histories (`IndexError`) | `rev[-1]`/`rev[1]` assumed ≥2 years | `_first()` guards; empty series returned instead of raising |
| 14 | Backtest reported trades that never opened | Entry index re-used from the previous trade | Explicit `entry_i = None` reset per position |
| 15 | Reports showed revenue in thousands, EPS ×1000 | Portal money is in thousands of PKR, EPS already rupees | `mirror.statements()` scales money ×1000 and EPS ×1 — one unit-safe producer |
| 16 | 23 of 39 tests "skipped" but looked green | `fastapi.testclient` needs `httpx` | `httpx` pinned in `requirements-dev.txt` |

Verification after the fixes: **57 offline tests pass**, `verify_build.py` →
`BUILD OK`, and a **51-route smoke test returns 51/51 HTTP 200 in ~9 s** (the
v3.19 original managed 30/47 in 181 s with the network up).

---

## 4. Tests and the verifier

```bash
.venv/bin/python -m pytest -q tests/test_offline_data.py   # 57 tests, no network
.venv/bin/python scripts/verify_build.py                   # BUILD OK / problem list
```

`tests/test_offline_data.py` forces `PSX_OFFLINE=1` and asserts things a demo
would hide: units (revenue in rupees, EPS in rupees, market cap not ×1000),
ordering (history chronological, statements newest-first), derived fields
(`change_pct` consistent with price/prev_close), coverage (every watchlist
symbol has a quote, KSE-100 = 100 members), and the failure paths (unknown
symbol returns empty, not an exception).

---

## 5. Known limits

- **No outbound internet in this build environment** — live rungs of the ladder
  are exercised only by the code path, not by real responses. The mirror is the
  verified source.
- **103 of 754 symbols have price history.** The snapshot covers all 754, so
  quotes and the heatmap work everywhere; charts, backtests and technicals need
  bars. `verify_build.py` and the UI both degrade instead of guessing.
- **News and announcements need the network.** Offline they return empty lists —
  the panel says so, it does not invent headlines.
- **Paper trading only.** Nothing in this build can place a real order.
