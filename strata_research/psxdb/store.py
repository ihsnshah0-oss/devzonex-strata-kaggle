"""SQLite store for the PSX Data Portal mirror.

All writes are idempotent upserts keyed on natural keys, so re-running an ingest
(refresh, backfill, or a re-run after a partial failure) converges to the same
database. Reads live in :mod:`strata_research.psxdb.query`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .schema import DDL, DEFAULT_INDICES, SCHEMA_VERSION, TABLES

DEFAULT_DB_PATH = Path("data/psx.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class PsxDatabase:
    """File-backed SQLite database for portal data."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path).expanduser()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.path.parent and str(self.path.parent) not in {"", "."}:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path), timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "PsxDatabase":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.conn
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()

    # ------------------------------------------------------------------
    def initialise(self) -> "PsxDatabase":
        with self.transaction() as connection:
            for statement in DDL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('default_indices', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (",".join(DEFAULT_INDICES),),
            )
        return self

    @property
    def schema_version(self) -> int | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else None

    def table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in TABLES:
            try:
                counts[table] = int(
                    self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                )
            except sqlite3.OperationalError:
                counts[table] = -1  # table missing (pre-init database)
        return counts

    # ------------------------------------------------------------- symbols
    def upsert_symbols(self, rows: Iterable[dict[str, Any]], source: str) -> int:
        now = utc_now()
        payload = [
            (
                row["symbol"], row.get("name"), row.get("sector"),
                int(row.get("is_etf") or 0), int(row.get("is_debt") or 0),
                source, now, now,
            )
            for row in rows
            if row.get("symbol")
        ]
        if not payload:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO symbols (symbol, name, sector, is_etf, is_debt, source,
                                     first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = COALESCE(excluded.name, symbols.name),
                    sector = COALESCE(excluded.sector, symbols.sector),
                    is_etf = excluded.is_etf,
                    is_debt = excluded.is_debt,
                    last_seen = excluded.last_seen
                """,
                payload,
            )
        return len(payload)

    # ---------------------------------------------------------- membership
    def upsert_memberships(
        self, index_code: str, symbols: Sequence[str], as_of: date | str, source: str
    ) -> int:
        stamp = _iso(as_of) or utc_now()
        payload = [(index_code, symbol, stamp, source) for symbol in dict.fromkeys(symbols)]
        if not payload:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO index_memberships (index_code, symbol, as_of, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(index_code, symbol, as_of) DO UPDATE SET
                    source = excluded.source
                """,
                payload,
            )
        return len(payload)

    # --------------------------------------------------------------- bars
    def upsert_bars(
        self,
        symbol: str,
        bars: Iterable[dict[str, Any]],
        source: str,
        *,
        table: str = "eod_bars",
        key_column: str = "symbol",
    ) -> int:
        if table not in {"eod_bars", "index_bars"}:
            raise ValueError(f"unsupported bar table {table!r}")
        captured = utc_now()
        payload = []
        for bar in bars:
            trade_date = _iso(bar.get("trade_date"))
            if not trade_date:
                continue
            payload.append(
                (
                    symbol, trade_date, bar.get("ts"), bar.get("open"), bar.get("high"),
                    bar.get("low"), bar.get("close"), bar.get("volume"), source, captured,
                )
            )
        if not payload:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                f"""
                INSERT INTO {table} ({key_column}, trade_date, ts, open, high, low,
                                      close, volume, source, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT({key_column}, trade_date) DO UPDATE SET
                    ts = COALESCE(excluded.ts, {table}.ts),
                    close = COALESCE(excluded.close, {table}.close),
                    open = COALESCE(excluded.open, {table}.open),
                    high = COALESCE(excluded.high, {table}.high),
                    low = COALESCE(excluded.low, {table}.low),
                    volume = COALESCE(excluded.volume, {table}.volume),
                    source = excluded.source,
                    captured_at = excluded.captured_at
                """,
                payload,
            )
        return len(payload)

    # ------------------------------------------------------------ indices
    def upsert_indices(self, rows: Iterable[dict[str, Any]], source: str) -> int:
        now = utc_now()
        payload = [
            (
                row["code"], row.get("name"), row.get("level"), row.get("change"),
                row.get("change_pct"), row.get("high"), row.get("low"), row.get("volume"),
                row.get("as_of") or now, source, now,
            )
            for row in rows
            if row.get("code")
        ]
        if not payload:
            return 0
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO indices (code, name, level, change, change_pct, high, low,
                                     volume, as_of, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = COALESCE(excluded.name, indices.name),
                    level = COALESCE(excluded.level, indices.level),
                    change = COALESCE(excluded.change, indices.change),
                    change_pct = COALESCE(excluded.change_pct, indices.change_pct),
                    high = COALESCE(excluded.high, indices.high),
                    low = COALESCE(excluded.low, indices.low),
                    volume = COALESCE(excluded.volume, indices.volume),
                    as_of = excluded.as_of,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
        return len(payload)

    # ---------------------------------------------------------- companies
    def upsert_snapshot(
        self,
        symbol: str,
        as_of: date | str,
        stats: dict[str, Any],
        source: str,
        *,
        sector: str | None = None,
        raw_hash: str | None = None,
    ) -> None:
        stamp = _iso(as_of) or utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO company_snapshots (
                    symbol, as_of, market_cap, shares, free_float, free_float_pct, pe, pb,
                    high_52w, low_52w, year_change_pct, ytd_change_pct, sector, raw_hash,
                    source, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, as_of) DO UPDATE SET
                    market_cap = COALESCE(excluded.market_cap, company_snapshots.market_cap),
                    shares = COALESCE(excluded.shares, company_snapshots.shares),
                    free_float = COALESCE(excluded.free_float, company_snapshots.free_float),
                    free_float_pct = COALESCE(excluded.free_float_pct, company_snapshots.free_float_pct),
                    pe = COALESCE(excluded.pe, company_snapshots.pe),
                    pb = COALESCE(excluded.pb, company_snapshots.pb),
                    high_52w = COALESCE(excluded.high_52w, company_snapshots.high_52w),
                    low_52w = COALESCE(excluded.low_52w, company_snapshots.low_52w),
                    year_change_pct = COALESCE(excluded.year_change_pct, company_snapshots.year_change_pct),
                    ytd_change_pct = COALESCE(excluded.ytd_change_pct, company_snapshots.ytd_change_pct),
                    sector = COALESCE(excluded.sector, company_snapshots.sector),
                    raw_hash = COALESCE(excluded.raw_hash, company_snapshots.raw_hash),
                    source = excluded.source,
                    captured_at = excluded.captured_at
                """,
                (
                    symbol, stamp, stats.get("market_cap"), stats.get("shares"),
                    stats.get("free_float"), stats.get("free_float_pct"), stats.get("pe"),
                    stats.get("pb"), stats.get("high_52w"), stats.get("low_52w"),
                    stats.get("year_change_pct"), stats.get("ytd_change_pct"), sector,
                    raw_hash, source, utc_now(),
                ),
            )

    def upsert_financial_years(
        self, symbol: str, years: Iterable[dict[str, Any]], source: str
    ) -> int:
        fields = (
            "revenue", "gross_profit", "operating_income", "pretax_income",
            "income_tax_expense", "net_income", "eps", "interest_expense",
            "depreciation_amortization", "total_assets", "total_equity", "total_debt",
            "cash_and_equivalents", "current_assets", "current_liabilities", "inventory",
            "operating_cash_flow", "capex", "dividend_per_share",
        )
        captured = utc_now()
        payload = []
        for year in years:
            fiscal_year = year.get("fiscal_year")
            if not fiscal_year:
                continue
            payload.append(
                (symbol, int(fiscal_year), *[year.get(field) for field in fields], source, captured)
            )
        if not payload:
            return 0
        columns = ", ".join(fields)
        placeholders = ", ".join(["?"] * (len(fields) + 4))
        updates = ", ".join(f"{field} = COALESCE(excluded.{field}, company_financial_years.{field})"
                            for field in fields)
        with self.transaction() as connection:
            connection.executemany(
                f"""
                INSERT INTO company_financial_years
                    (symbol, fiscal_year, {columns}, source, captured_at)
                VALUES ({placeholders})
                ON CONFLICT(symbol, fiscal_year) DO UPDATE SET
                    {updates}, source = excluded.source, captured_at = excluded.captured_at
                """,
                payload,
            )
        return len(payload)

    # --------------------------------------------------------- provenance
    def start_run(self, mode: str, indices: Sequence[str]) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO ingest_runs (started_at, mode, indices) VALUES (?, ?, ?)",
                (utc_now(), mode, ",".join(indices)),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        requests: int,
        rows_written: int,
        errors: int,
        notes: dict[str, Any] | None = None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE ingest_runs
                   SET finished_at = ?, requests = ?, rows_written = ?, errors = ?, notes = ?
                 WHERE run_id = ?
                """,
                (utc_now(), requests, rows_written, errors,
                 json.dumps(notes or {}, default=str), run_id),
            )

    def log_raw(
        self,
        run_id: int,
        endpoint: str,
        url: str,
        status: int | None,
        body: str,
        sha256: str | None = None,
        *,
        max_bytes: int = 400_000,
    ) -> None:
        stored = body if len(body) <= max_bytes else body[:max_bytes] + "…[truncated]"
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO raw_payloads
                    (run_id, endpoint, url, http_status, bytes, sha256, captured_at, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, endpoint, url) DO UPDATE SET
                    http_status = excluded.http_status,
                    bytes = excluded.bytes,
                    sha256 = excluded.sha256,
                    body = excluded.body
                """,
                (run_id, endpoint, url, status, len(body), sha256, utc_now(), stored),
            )
