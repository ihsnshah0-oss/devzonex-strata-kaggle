"""SQLite schema for the PSX Data Portal mirror.

Design notes
------------
* One database file holds the whole portal mirror (default ``data/psx.db``).
* Every table that can be refreshed is keyed so that re-running an ingest is
  idempotent (``INSERT … ON CONFLICT DO UPDATE``).
* ``index_memberships`` is an *as-of* snapshot: rebalances are preserved instead
  of overwritten, so a historical report can say which index a stock was in on
  the day it was written.
* ``ingest_runs`` and ``raw_payloads`` carry provenance: which endpoint, when,
  HTTP status and a hash of the bytes, so a number can always be traced back.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = [
    # ---------------------------------------------------------------- symbols
    """
    CREATE TABLE IF NOT EXISTS symbols (
        symbol        TEXT PRIMARY KEY,
        name          TEXT,
        sector        TEXT,
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
        ts            INTEGER,
        open          REAL,
        high          REAL,
        low           REAL,
        close         REAL,
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
        ts            INTEGER,
        open          REAL,
        high          REAL,
        low           REAL,
        close         REAL,
        volume        REAL,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (index_code, trade_date)
    )
    """,
    # --------------------------------------------------------- company stats
    """
    CREATE TABLE IF NOT EXISTS company_snapshots (
        symbol        TEXT NOT NULL,
        as_of         TEXT NOT NULL,
        market_cap    REAL,
        shares        REAL,
        free_float    REAL,
        free_float_pct REAL,
        pe            REAL,
        pb            REAL,
        high_52w      REAL,
        low_52w       REAL,
        year_change_pct REAL,
        ytd_change_pct REAL,
        sector        TEXT,
        raw_hash      TEXT,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (symbol, as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_financial_years (
        symbol        TEXT NOT NULL,
        fiscal_year   INTEGER NOT NULL,
        revenue       REAL,
        gross_profit  REAL,
        operating_income REAL,
        pretax_income REAL,
        income_tax_expense REAL,
        net_income    REAL,
        eps           REAL,
        interest_expense REAL,
        depreciation_amortization REAL,
        total_assets  REAL,
        total_equity  REAL,
        total_debt    REAL,
        cash_and_equivalents REAL,
        current_assets REAL,
        current_liabilities REAL,
        inventory     REAL,
        operating_cash_flow REAL,
        capex         REAL,
        dividend_per_share REAL,
        source        TEXT NOT NULL,
        captured_at   TEXT NOT NULL,
        PRIMARY KEY (symbol, fiscal_year)
    )
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
    "company_financial_years",
    "ingest_runs",
    "raw_payloads",
)

#: Indices this project tracks by default.
DEFAULT_INDICES = ("KSE100", "KMI30")
