# PSX database — KSE100 + KMI30 mirrored from the PSX Data Portal

A SQLite mirror of the **Pakistan Stock Exchange**, built only from
`https://dps.psx.com.pk`. No Yahoo, no aggregator, no invented numbers: every row records the
portal route it came from, and the raw bytes are hashed.

```bash
gunzip -c data/psx.db.gz > data/psx.db          # the committed mirror (7.4 MB gzipped)
python -m strata_research.psxdb stats           # what is in there
python -m strata_research.psxdb quotes --index KMI30
python -m strata_research.psxdb history OGDC --limit 30
```

Latest live run (2026-10-29, `data/psx.db.gz` in this repo):

| | |
|---|---|
| Trading day | 2026-10-29 (the portal's own `data-latest` stamp) |
| KSE100 / KMI30 members | **100 / 30** (derived from the portal, never hardcoded) |
| Symbols listed on the screener | 754 (701 with a sector) |
| Index levels | 18 (KSE100, KMI30, ALLSHR, KSE30, …) |
| **Daily bars** | **235 583** across 103 companies, **2016-10-31 → 2026-10-29** |
| Index bars | 2 496 (KSE100 and KMI30, 2021-11-01 → 2026-10-29) |
| Company financial line items | 3 992 rows · 103 companies · 9 metrics · 22 periods |
| Run | 317 requests, **0 errors**, 227 s |

A second run stored **identical counts with 0 new rows and 0 duplicate bars** — re-running the
ingest is idempotent, and each symbol's 0.5 MB history page is fetched once, not every night.

## The request token — why the routes looked withdrawn

Until this was found, `POST /historical`, `/symbols` and `/timeseries/*` all answered **404**, which
looked like the portal had retired them. They had not: since **2026-09-24** the portal requires a
short-lived request token on data routes.

* The token is `window.__ps._k`, embedded in **every** HTML page (43 characters, rotated roughly
  every five minutes).
* It is sent as the `X-Req-Id` header; data routes also require
  `X-Requested-With: XMLHttpRequest` and **404** (not 401) without them, which is what made the
  routes look gone.
* `strata_research/psxdb/client.py` learns the token from any page it downloads, caches it for 240
  seconds, and refreshes it once when a data route answers 401/403/404.
* `scripts/psx_probe.py` prints the token's presence and the status of every data route, so a future
  change is diagnosed in one run instead of guessed at.

Evidence (probe run 2026-10-29, `data/probe.log`):

```
history_plain       404   (no token, no xhr)
history_token       404   (token, but no X-Requested-With)
history_token_xhr   200   bytes=497628  tables=1 rows=2480
symbols_token_xhr   200   bytes=136853  json_len=1052
timeseries_eod      200   bytes=41185   json {"status":1,"data":[[epoch,close,volume,open],...]}
trading_board       200   bytes=369238  SYMBOL/NAME/BID/OFFER/LDCP/CHANGE/VOLUME
sector_summary      200   bytes=492697  39 sectors
```

## What the portal publishes (verified, not assumed)

| Route | Content | Notes |
|---|---|---|
| `GET /screener` | one row per listed symbol: sector code, LISTED IN, market cap, price, change %, 1-year change %, P/E (TTM), dividend yield, free float, 30-day average volume | market cap in **thousands of rupees**; the sector `<select>` maps codes to industry names |
| `GET /indices` | level, day high/low, change per index | index level, not a per-stock price |
| `GET /indices/{CODE}` | constituents with LDCP, current, change, weight, index points, volume, free float, market cap | authoritative constituent list |
| `POST /historical` (`symbol=`) | **full daily OHLCV** table, ~2 480 rows per symbol | needs token + XHR headers; ~0.5 MB per symbol |
| `GET /timeseries/eod/{SYM}` | `[[epoch, close, volume, open], …]`, newest first | cheap (~40 KB), **no high/low** |
| `GET /symbols` | 1 052 symbols as JSON: symbol, name, sector, `isETF`, `isDebt` | token + JSON accept |
| `GET /company/{SYM}` | quote stats, ranges, P/E, market cap, shares, free float, announcements, annual and quarterly financial tables | market cap in thousands of rupees |
| `GET /historical` | the date picker only — **but** it carries `data-latest`, the portal's latest trading date | used to stamp every row |
| `GET /trading-board/{MKT}/{BOARD}` | live bid/offer board per market (`REG`, `ODL`, …) and board (`MAIN`, `GEM`, `BNB`) | not ingested yet |
| `GET /sector-summary/sectorwise` | advance/decline, turnover, market cap per sector | not ingested yet |

The history table's markup is preserved verbatim in
`tests/fixtures/psx/history/OGDC.html` (and `data/history-sample.html` is a live copy), so the
parser is tested against the portal's real shape:

```html
<th data-name="time">DATE </th> … <th data-name="volume">VOLUME</th>
<tr><td data-order="1793271600">Oct 29, 2026</td><td class="right">306.00</td> …
```

## Schema (v2)

```
symbols                  symbol, name, sector, sector_code, listed_in, is_etf, is_debt,
                         source, first_seen, last_seen
indices                  code, name, level, change, change_pct, high, low, volume,
                         as_of, source, updated_at
index_memberships        index_code, symbol, as_of, weight_pct, index_points, source
                         (as-of snapshots — a rebalance adds rows, it never rewrites)
eod_bars                 symbol, trade_date, open, high, low, close, prev_close,
                         volume, source, captured_at          PK (symbol, trade_date)
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
meta                     key, value   ← schema version, default indices, source URL
```

Design rules:

* **Idempotent.** Every write is `INSERT … ON CONFLICT DO UPDATE` on a natural key.
* **A richer row is never overwritten by a poorer one.** All updates use `COALESCE`, so a bar that
  has a high/low keeps them when the cheap chart feed later supplies only close/volume. The 2026-10-29
  OGDC bar even records all four contributors:
  `indices + historical + timeseries/eod + company/OGDC`.
* **No hardcoded memberships.** `KSE100`/`KMI30` come from `/indices/{CODE}` on every run; if the
  portal does not say it, the database does not claim it.
* **Provenance is mandatory.** `raw_payloads` stores endpoint, URL, status, bytes, sha256 and a
  truncated body; a capture directory keeps the full pages.

## Units and definitions that bite

| Item | Portal publishes | Stored as |
|---|---|---|
| Market cap (`/screener`, `/company`) | thousands of rupees (`1 316 987 285.36`) | rupees (`1 316 987 285 360`) — one conversion in `ingest._market_cap_pkr()` |
| `MARKET CAP (M)` in `/indices/{CODE}` | absolute free-float rupees | never mixed into `company_snapshots.market_cap` |
| EPS, formula, per-share | rupees | rupees, never scaled |
| `LDCP` | previous session's close | `prev_close`, never `close` |
| History dates | `Oct 29, 2026` **and** `data-order="1793271600"` | `trade_date` in Karachi |
| `/timeseries` rows | `[epoch, close, volume, open]` | mapped positionally; high/low stay `NULL` |

Cross-check baked into the tests: `shares × price` must equal the stored market cap
(4 300 928 400 × 306.47 = Rs 1.317 trillion).

## Command reference

| Command | What it does |
|---|---|
| `init` | create the schema (`data/psx.db` by default) |
| `ingest` | pull `/screener`, `/indices`, each `/indices/{CODE}`, `POST /historical` (once per symbol), `/timeseries/eod/{SYM}` for every constituent and index, and one `/company/{SYM}` per constituent |
| `from-capture DIR` | replay a saved capture with no network at all |
| `stats` | row counts, coverage, member counts, last run |
| `constituents [CODE]` | members of the latest snapshot (or `--as-of`) |
| `quotes [--index CODE]` | latest bar per symbol with the implied change |
| `history SYMBOL [--limit N] [--since DATE] [--index]` | stored bars, newest first |
| `indices` / `market` | index levels / breadth for the latest day |
| `fundamentals SYMBOL` | snapshot + memberships + published financial periods as JSON |
| `export --table T --out F` | CSV dump of any table |

Ingest flags: `--indices KSE100,KMI30`, `--workers 3`, `--interval 0.25`, `--no-company`,
`--company-limit N`, `--no-history` (skip the expensive backfill), `--history-limit N`,
`--full-history` (refetch every history page), `--capture-dir DIR`, `--json`, `--db PATH`.

A failing symbol never aborts a run: errors are collected in the report and the run continues. A run
that stores **nothing** exits non-zero.

## How the live mirror is produced

`dps.psx.com.pk` is not reachable from every network (this project's dev sandbox blocks it), so
ingestion runs on GitHub Actions:

* `.github/workflows/psx-ingest.yml` — offline test suite, restore the committed gzip, ingest, gzip
  and **commit `data/psx.db.gz` + `data/ingest-report.json` + `data/ingest.log` back to the branch**,
  and upload the database and the raw capture as artifacts. Triggers: `workflow_dispatch`, and a push
  that touches `data/ingest-trigger.txt` (the dispatch API only accepts workflows present on the
  default branch).
* `.github/workflows/psx-probe.yml` — runs `scripts/psx_probe.py`, commits `data/probe.json`,
  `data/probe.log` and a real `data/history-sample.html`.

Both workflows rebase and retry before pushing, because two runs can land on the branch at once.

## Using the mirror in the desk

`strata_research.psx.PsxQuoteClient` reads closes from `data/psx.db` when it exists — expanding the
committed `data/psx.db.gz` on first use — then falls back to `/timeseries/eod/{SYM}` and finally to
`/company/{SYM}`.

`strata_research.data.portal_provider.PortalStatementsProvider` turns the same mirror into
fundamentals for the analyst: profile, price, market cap, and the annual Sales / Profit after
Taxation / EPS rows the portal publishes, converted to millions of PKR. That is why
`python -m strata_research analyze OGDC` works with no API key and no hand-keyed statements:

```bash
python -m strata_research analyze MARI
python -m strata_research watchlist --json     # what can the portal answer?
```

## Tests

```bash
python -m pytest tests/test_psxdb.py -q        # 56 tests, offline
python -m pytest tests/test_portal_provider.py -q
```

Covered: the token lifecycle (extract, send, refresh on 404), XHR headers on data routes, the real
history markup, the chart feed's `[epoch, close, volume, open]` rows, header-matched columns,
`AHCL XD`-style symbols, `K`/`M`/`B` magnitudes, weekend-safe trade dates, unit conversions, store
idempotency, richer-row preservation, as-of memberships, capture replay, per-symbol failure
isolation, thread-safe writes, and the CLI.

## Limits, stated up front

* **The chart feed has no high/low.** Only `POST /historical` and the company page publish an
  intraday range, so bars from the daily refresh have `high`/`low` filled by the backfill or `NULL`.
* **Financial line items are whatever the company page prints** — typically Sales, Profit after
  Taxation, EPS and published margins, sometimes bank-specific. No balance sheet, cash flow or
  EBITDA: the desk scores those as `n/a` instead of inventing them.
* **The portal is not an API.** A markup change breaks a parser loudly (with a snippet of what was
  seen); `scripts/psx_probe.py` is the first thing to run when that happens.
* **Board/market data is not ingested yet** (`/trading-board/*`, `/sector-summary/sectorwise` answer
  200 and are recorded by the probe, but nothing stores them).
* **The token is short-lived and undocumented.** If the portal changes the mechanism, ingestion fails
  loudly rather than silently falling back to another data source.

## A note on third-party PSX packages

`psxdata`, `psx-data-reader` and similar libraries wrap the same `dps.psx.com.pk` pages — and
`psxdata`'s changelog is what pointed at the `X-Req-Id` token (`#161`). They are not used here, by
design: the requirement is portal-only data, an auditable provenance trail, and a single Python
dependency (`httpx`). A wrapper would add pandas/pyarrow/beautifulsoup to the runtime, and some
wrappers quietly fail over to other providers — which would break the "portal only" guarantee.
