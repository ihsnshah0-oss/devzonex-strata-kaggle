"""SQLite schema for the PSX Data Portal mirror.

Scope
-----
Every column here is filled from a page on ``https://dps.psx.com.pk``. Nothing
is derived from another provider and nothing is invented; a field the portal
does not publish stays ``NULL``.

Design notes
------------
* One database file holds the whole mirror (default ``data/psx.db``).
* Every refresh is an idempotent upsert on a natural key, so re-running an
  ingest converges instead of duplicating.
* ``index_memberships`` is an *as-of* snapshot: rebalances are preserved, so a
  report can say which index a stock belonged to on a given date.
* ``company_financials`` is a narrow ``(period, metric, value)`` table because
  the portal publishes whatever line items a company reports — storing the
  published label next to a canonical metric keeps that honest.
* ``ingest_runs`` and ``raw_payloads`` carry provenance: endpoint, timestamp,
  HTTP status and the sha256 of the bytes, so a figure can be traced back.

History caveat
--------------
The portal's per-symbol history route (``/timeseries/eod/{symbol}``) returns
404 from the current deployment, and the historical-data form no longer serves
rows. A run therefore records **the trading day the portal is showing**, plus
LDCP (the previous close). Running the ingest daily builds the series one real
trading day at a time; nothing is back-filled from any other source.
"""

from __future__ import annotations

SCHEMA_VERSION = 2

DDL = [
    # ---------------------------------------------------------------- symbols
    """
    CREATE TABLE IF NOT EXISTS symbols (
        symbol        TEXT PRIMARY KEY,
        name          TEXT,
        sector        TEXT,
        sector_code   TEXT,
        listed_in     TEXT,
        is_etf        INTEGER NOT NULL DEFAULT 0,
        is_debt       INTEGER NOT NULL DEFAULT 0,
        source        TEXT NOT NULL,
        first_seen    TEXT NOT NULL,
        last_seen     TEXT NOT NULL
    )
    """,
    # ---------------------------------------------------------------- indices
    """
    CREATE TABLE IF NOT EXISTS indices (
        code          TEXT PRIMARY KEY,
        name          TEXT,
        level         REAL,
        change        REAL,
        change_pct    REAL,
        high          REAL,
        low           REAL,
        volume        REAL,
        as_of         TEXT,
        source        TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )
    """,
    # ------------------------------------------------------------ membership
    """
    CREATE TABLE IF NOT EXISTS index_memberships (
        index_code    TEXT NOT NULL,
        symbol        TEXT NOT NULL,
        as_of         TEXT NOT NULL,
        weight_pct    REAL,
        index_points  REAL,
        source        TEXT NOT NULL,
        PRIMARY KEY (index_code, symbol, as_of)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memberships_symbol
        ON index_memberships (symbol, as_of)
    """,
    # ------------------------------------------------------------- price bars
    """
    CREATE TABLE IF NOT EXISTS eod_bars (
        symbol        TEXT NOT NULL,
        trade_date    TEXT NOT NULL,
        open          REAL,
        high          REAL,
        low           REAL,
        close         REAL,
        prev_close    REAL,
        volume        REAL,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (symbol, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS index_bars (
        index_code    TEXT NOT NULL,
        trade_date    TEXT NOT NULL,
        open          REAL,
        high          REAL,
        low           REAL,
        close         REAL,
        prev_close    REAL,
        volume        REAL,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (index_code, trade_date)
    )
    """,
    # --------------------------------------------------------- company stats
    """
    CREATE TABLE IF NOT EXISTS company_snapshots (
        symbol          TEXT NOT NULL,
        as_of           TEXT NOT NULL,
        price           REAL,
        open            REAL,
        high            REAL,
        low             REAL,
        prev_close      REAL,
        volume          REAL,
        high_52w        REAL,
        low_52w         REAL,
        circuit_high    REAL,
        circuit_low     REAL,
        pe              REAL,
        pb              REAL,
        shares          REAL,
        free_float      REAL,
        free_float_pct  REAL,
        market_cap      REAL,
        dividend_yield  REAL,
        avg_volume_30d  REAL,
        year_change_pct REAL,
        ytd_change_pct  REAL,
        sector          TEXT,
        raw_hash        TEXT,
        source          TEXT NOT NULL,
        captured_at     TEXT NOT NULL,
        PRIMARY KEY (symbol, as_of)
    )
    """,
    # ----------------------------------------------------- published financials
    """
    CREATE TABLE IF NOT EXISTS company_financials (
        symbol        TEXT NOT NULL,
        period        TEXT NOT NULL,
        metric        TEXT NOT NULL,
        fiscal_year   INTEGER,
        quarter       INTEGER,
        label         TEXT,
        value         REAL,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (symbol, period, metric)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_financials_metric
        ON company_financials (symbol, metric)
    """,
    # ----------------------------------------------------------- provenance
    """
    CREATE TABLE IF NOT EXISTS ingest_runs (
        run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at    TEXT NOT NULL,
        finished_at   TEXT,
        mode          TEXT NOT NULL,
        indices       TEXT,
        requests      INTEGER NOT NULL DEFAULT 0,
        rows_written  INTEGER NOT NULL DEFAULT 0,
        errors        INTEGER NOT NULL DEFAULT 0,
        notes         TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_payloads (
        run_id        INTEGER NOT NULL,
        endpoint      TEXT NOT NULL,
        url           TEXT NOT NULL,
        http_status   INTEGER,
        bytes         INTEGER,
        sha256        TEXT,
        captured_at   TEXT NOT NULL,
        body          TEXT,
        PRIMARY KEY (run_id, endpoint, url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key           TEXT PRIMARY KEY,
        value         TEXT
    )
    """,
]

#: Tables written by the ingester, used by ``stats`` and by tests.
TABLES = (
    "symbols",
    "indices",
    "index_memberships",
    "eod_bars",
    "index_bars",
    "company_snapshots",
    "company_financials",
    "ingest_runs",
    "raw_payloads",
)

#: Indices this project tracks by default.
DEFAULT_INDICES = ("KSE100", "KMI30")
