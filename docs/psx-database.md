# PSX database — KSE100 + KMI30 mirrored from the PSX Data Portal

A SQLite mirror of the **Pakistan Stock Exchange** indices, built only from
`https://dps.psx.com.pk`. No Yahoo, no aggregator, no invented numbers: every
row records the portal route it came from and a sha256 of the bytes that carried
it.

```bash
python -m strata_research.psxdb init                       # create data/psx.db
python -m strata_research.psxdb ingest                     # pull from the portal
python -m strata_research.psxdb stats                     # what is in there
python -m strata_research.psxdb constituents KSE100       # 100 members
python -m strata_research.psxdb quotes --index KMI30      # latest closes
```

Last live run (2026-10-29, `data/psx.db.gz` in this repo):

| | |
|---|---|
| Trading day | 2026-10-29 (the portal's own `data-latest` stamp) |
| KSE100 / KMI30 members | **100 / 30** (derived from the portal, not hardcoded) |
| Symbols listed on the screener | **754** |
| Symbols with a sector | **701** |
| Index levels | 18 (KSE100, KMI30, ALLSHR, KSE30, …) |
| Daily bars | 103 (KSE100 ∪ KMI30), each with open/high/low/close/prev_close/volume |
| Published financial line items | 3 992 rows across 103 companies and 22 periods |
| Requests / errors / duration | 110 / 0 / 70 s |
| Database size | 271 KB gzipped (`data/psx.db.gz`) |

A second run 6 minutes later stored **exactly the same counts with 0 new rows and 0
duplicate bars** — re-running the ingest is idempotent, and the portal was still serving the
2026-10-29 session (the market had closed), so no phantom trade date was invented.

## What the portal publishes (verified, not assumed)

`scripts/psx_probe.py` reads the portal the way a browser does and reports what
each route returns. As of 2026-10-29:

| Route | Content | Units / notes |
|---|---|---|
| `/screener` | one row per listed symbol: SECTOR code, LISTED IN, MARKET CAP., PRICE, CHANGE (%), 1-YEAR CH. (%), PE RATIO (TTM), DIVIDEND YIELD (%), FREE FLOAT, 30D VOLUME AVG. | market cap in **thousands of rupees**; the page's sector filter maps codes to industry names |
| `/indices` | Index, High, Low, Current, Change, % Change | index level, not a per-stock price |
| `/indices/KSE100`, `/indices/KMI30` | SYMBOL, NAME, LDCP, CURRENT, CHANGE, CHANGE (%), IDX WTG (%), IDX POINT, VOLUME, FREEFLOAT (M), MARKET CAP (M) | this is the **authoritative constituent list**; `data-order` carries unrounded values |
| `/company/{SYMBOL}` | Open, High, Low, Volume, CIRCUIT BREAKER, DAY RANGE, 52-WEEK RANGE, LDCP, Close, P/E (TTM), 1-year/YTD change, announcements, annual and quarterly financial tables | market cap in thousands of rupees |
| `/historical` | the date picker only — **but** it carries `data-latest`, the portal's own latest trading date | used to stamp every row with the right trading day |

### What it no longer publishes

These routes returned `404` from `nginx/1.20.2` when checked with `curl`
HTTP/1.1, `curl --http2`, `httpx` HTTP/1.1 and `httpx` HTTP/2, with and without
browser XHR headers:

```
/symbols               /market-watch          /timeseries/eod/{symbol}
/timeseries/int/{sym}  POST /historical       POST /daily-downloads
/historical/{symbol}   /performers            /trading-board/{symbol}
```

Consequences, stated plainly:

* **There is no historical price series to backfill.** A run stores the trading
  day the portal is showing plus **LDCP** (the previous close), so a cold start
  seeds two days and a daily schedule builds a real day-by-day series. Nothing
  is ever synthesised, interpolated or pulled from another provider.
* **OHLCV comes from two pages.** The constituent table supplies close, LDCP and
  volume; the company page supplies open/high/low. A bar therefore lists *both*
  contributors in `source`, and the market's own print stays authoritative for
  the close.
* **Financial line items are whatever the company page prints** — typically
  Sales, Profit after Taxation, EPS, and margin/ratio lines, sometimes bank
  specific (Mark-up Earned, Total Income). That is enough for margins, P/E and
  EPS trends; it is **not** enough for a full EV/EBITDA or free-cash-flow model,
  and the desk says so instead of inventing the missing statements.

## Schema (v2)

```
symbols                  symbol, name, sector, sector_code, listed_in, is_etf, is_debt,
                         source, first_seen, last_seen
indices                  code, name, level, change, change_pct, high, low, volume,
                         as_of, source, updated_at
index_memberships        index_code, symbol, as_of, weight_pct, index_points, source
                         (as-of snapshots — a rebalance adds a row, it never rewrites)
eod_bars                 symbol, trade_date, open, high, low, close, prev_close,
                         volume, source, captured_at
index_bars               index_code, trade_date, … same shape
company_snapshots        symbol, as_of, price, open, high, low, prev_close, volume,
                         high_52w, low_52w, circuit_high, circuit_low, pe, pb,
                         shares, free_float, free_float_pct, market_cap,
                         dividend_yield, avg_volume_30d, year_change_pct,
                         ytd_change_pct, sector, raw_hash, source, captured_at
company_financials       symbol, period, metric, fiscal_year, quarter, label, value,
                         source, captured_at
ingest_runs              run_id, started_at, finished_at, mode, indices, requests,
                         rows_written, errors, notes
raw_payloads             run_id, endpoint, url, http_status, bytes, sha256,
                         captured_at, body
meta                     key, value   ← trading day, schema version, last run
```

Design rules:

* **Idempotent.** Every write is an `INSERT … ON CONFLICT DO UPDATE` on a
  natural key, so re-running converges instead of duplicating.
* **A richer row is never overwritten by a poorer one.** All updates use
  `COALESCE`, so a bar that has a high/low keeps them when a later page only
  publishes a close.
* **No hardcoded memberships.** The constituent lists come from `/indices/{CODE}` on every run;
  `ingest(expected_constituents=...)` exists for callers who want a sanity check, but the mirror
  never falls back to a list baked into the code — if the portal does not say it, the database does
  not claim it.
* **Memberships are as-of snapshots.** A KSE100 rebalance adds a new snapshot
  instead of rewriting history: `constituents KSE100 --as-of 2026-06-30` still
  answers the old question.
* **Financials are narrow on purpose.** `(period, metric, value)` with the
  published `label` kept beside a canonical `metric`, because the portal prints
  whatever each company reports.
* **Provenance is mandatory.** `raw_payloads` stores the endpoint, URL, status,
  byte count, sha256 and a truncated body (the full page is in the capture), and
  every bar/snapshot names its source page.

## Units and definitions that bite

| Item | Portal publishes | Stored as |
|---|---|---|
| Market capitalisation (`/screener`, `/company`) | thousands of rupees (`1 316 987 285.36`) | rupees (`1 316 987 285 360`), one conversion in `ingest.MARKET_CAP_UNIT` |
| `MARKET CAP (M)` in `/indices/{CODE}` | absolute **free-float** rupees | not mixed into `company_snapshots.market_cap` |
| Formula, EPS, per-share values | rupees | rupees, never scaled |
| `LDCP` | previous session's close | `prev_close`, never `close` |
| `IDX WTG (%)` | percent | `index_memberships.weight_pct` |
| Timestamps | Pakistan wall-clock (ms epoch in `data-latest`) | `trade_date` in Karachi (weekend-safe `derive_trade_date`) |

The market-cap conversion is the classic PSX trap: the portal's number is
`1 316 987 285.36`, which reads like Rs 1.3 billion but is Rs 1.317 **trillion**
for 4 300 928 400 shares at Rs 306. The mirror cross-checks nothing silently —
`shares × price` and the stored value agree, and the test suite asserts the
conversion.

## Command reference

| Command | What it does |
|---|---|
| `init` | create the schema (`data/psx.db` by default) |
| `ingest` | pull `/screener`, `/indices`, each tracked `/indices/{CODE}`, and one `/company/{SYMBOL}` per constituent |
| `from-capture DIR` | replay a saved capture with no network at all |
| `stats` | row counts, coverage, member counts, last run |
| `constituents [CODE]` | members of the latest snapshot (or `--as-of`) |
| `quotes [--index CODE]` | latest bar per symbol with the implied change |
| `history SYMBOL` | stored bars, newest first (`--index` reads index bars) |
| `indices` / `market` | index levels / breadth for the latest day |
| `fundamentals SYMBOL` | snapshot + published financial periods as JSON |
| `export --table T --out F` | CSV dump of any table |

Ingest flags: `--indices KSE100,KMI30`, `--workers 2`, `--interval 0.4`,
`--no-company` (skip company pages, ~4 requests instead of ~110),
`--company-limit N`, `--capture-dir DIR`, `--json`, `--db PATH`.

A failing symbol or a moved column never aborts a run: errors are collected in
the report and the run continues. A run that stores **nothing** exits non-zero.

## How the live mirror is produced

`dps.psx.com.pk` is not reachable from every network (this project's dev sandbox
blocks it), so ingestion runs on GitHub Actions:

* `.github/workflows/psx-ingest.yml` — runs the offline test suite, ingests,
  commits `data/psx.db.gz` + `data/ingest-report.json` + `data/ingest.log` back
  to the branch, and uploads the full database and the raw capture as artifacts.
  Triggers: `workflow_dispatch`, and a push that touches
  `data/ingest-trigger.txt` (the `workflow_dispatch` API only accepts workflows
  present on the default branch).
* `.github/workflows/psx-probe.yml` — runs `scripts/psx_probe.py` and commits
  `data/probe.json`, so a future route change is diagnosed in one run instead of
  guessed at.

Reproduce locally:

```bash
gunzip -c data/psx.db.gz > data/psx.db      # the committed mirror
python -m strata_research.psxdb stats
python -m strata_research.psxdb export --table eod_bars --out /tmp/eod.csv
```

## Using the mirror in the desk

`strata_research.psx.PsxQuoteClient` reads closes from `data/psx.db` when it
exists (offline, exact), then falls back to `/company/{SYMBOL}` for a live
quote — the old `/historical` form route is gone. `run_fundamentals(symbol)`
returns one symbol's snapshot, memberships and published financials for the
analyst to consume.

## Tests

```bash
python -m pytest tests/test_psxdb.py -q      # 47 tests, offline
```

Covered: parser behaviour against the portal's real markup (including `data-order`
values, `AHCL XD`-style markers, `K`/`M`/`B` suffixes and empty P/E cells),
unit conversions, weekend-safe trade dates, store idempotency, richer-row
preservation, as-of membership, capture replay, per-symbol failure isolation,
thread-safe writes, the CLI, and mirror-backed desk quotes.

## Limits, stated up front

* **One trading day per run.** Daily history accrues only while the ingest runs;
  the portal offers nothing to backfill it.
* **No per-stock high/low or open from the history route** (it is gone). Today's
  range comes from the company page; earlier days have close/prev_close/volume.
* **No shares outstanding, free float or total assets for many companies** — the
  screener/company pages simply do not print them.
* **Banks and insurers** report different line items; the narrow financials table
  stores what they print instead of forcing them into an industrial template.
* **The portal is not an API.** If its markup changes, the parser raises a
  diagnosable error and the run continues for everything it could still read —
  run `scripts/psx_probe.py` to see the new shape.
