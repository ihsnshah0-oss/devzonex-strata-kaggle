"""Read helpers over the PSX portal database.

Everything here is a plain SQL read: no network, no derivation beyond arithmetic
the portal itself publishes (a change percentage from two closes, for example).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import DEFAULT_INDICES
from .store import DEFAULT_DB_PATH, PsxDatabase


def _db(db: PsxDatabase | None, path: str | None) -> PsxDatabase:
    if db is not None:
        return db
    return PsxDatabase(Path(path) if path else DEFAULT_DB_PATH)


def database_stats(db: PsxDatabase | None = None, path: str | None = None) -> dict[str, Any]:
    """Row counts, coverage and the last run — the ``stats`` command's payload."""
    database = _db(db, path)
    if database.schema_version is None:
        return {
            "path": str(database.path),
            "schema_version": None,
            "tables": {},
            "coverage": {},
            "indices": [],
            "last_run": None,
        }
    counts = database.table_counts()
    coverage: dict[str, dict[str, Any]] = {}
    for table, key in (("eod_bars", "symbol"), ("index_bars", "index_code")):
        row = database.conn.execute(
            f"""
            SELECT COUNT(DISTINCT {key}) AS entities,
                   MIN(trade_date) AS first_date,
                   MAX(trade_date) AS last_date,
                   COUNT(*) AS bars
              FROM {table}
            """
        ).fetchone()
        coverage[table] = dict(row) if row else {}
    latest_run = database.conn.execute(
        "SELECT run_id, mode, started_at, finished_at, requests, rows_written, errors, notes "
        "FROM ingest_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    memberships = {
        row["index_code"]: row["members"]
        for row in database.conn.execute(
            "SELECT index_code, COUNT(*) AS members FROM index_memberships "
            "WHERE as_of = (SELECT MAX(as_of) FROM index_memberships) GROUP BY index_code"
        ).fetchall()
    }
    return {
        "path": str(database.path),
        "schema_version": database.schema_version,
        "tables": counts,
        "coverage": coverage,
        "memberships": memberships,
        "indices": index_levels(database),
        "last_run": dict(latest_run) if latest_run else None,
    }


def symbols(
    db: PsxDatabase | None = None,
    *,
    path: str | None = None,
    sector: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    database = _db(db, path)
    sql = "SELECT symbol, name, sector, sector_code, listed_in FROM symbols"
    params: list[Any] = []
    if sector:
        sql += " WHERE LOWER(COALESCE(sector, '')) LIKE ? OR sector_code = ?"
        params.extend([f"%{sector.lower()}%", sector])
    sql += " ORDER BY symbol"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [dict(row) for row in database.conn.execute(sql, params).fetchall()]


def _latest_as_of(database: PsxDatabase, index_code: str) -> str | None:
    row = database.conn.execute(
        "SELECT MAX(as_of) AS stamp FROM index_memberships WHERE index_code = ?",
        (index_code,),
    ).fetchone()
    return row["stamp"] if row and row["stamp"] else None


def constituents(
    db: PsxDatabase | None = None,
    *,
    path: str | None = None,
    index_code: str = "KSE100",
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Members of an index as of a snapshot date (the latest by default)."""
    database = _db(db, path)
    code = index_code.strip().upper()
    stamp = as_of or _latest_as_of(database, code)
    if not stamp:
        return []
    rows = database.conn.execute(
        """
        SELECT m.symbol, s.name, s.sector, m.weight_pct, m.index_points, m.as_of
          FROM index_memberships m
          LEFT JOIN symbols s ON s.symbol = m.symbol
         WHERE m.index_code = ? AND m.as_of = ?
         ORDER BY COALESCE(m.weight_pct, 0) DESC, m.symbol
        """,
        (code, stamp),
    ).fetchall()
    return [dict(row) for row in rows]


def latest_quotes(
    db: PsxDatabase | None = None,
    *,
    path: str | None = None,
    index_code: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Most recent bar per symbol, with the change the portal implies."""
    database = _db(db, path)
    sql = """
        SELECT b.symbol, s.name, s.sector, b.trade_date, b.close, b.open, b.high, b.low,
               b.prev_close, b.volume,
               CASE WHEN b.prev_close IS NOT NULL AND b.prev_close <> 0
                    THEN (b.close - b.prev_close) / b.prev_close * 100.0 END AS change_pct
          FROM eod_bars b
          JOIN (SELECT symbol, MAX(trade_date) AS d FROM eod_bars GROUP BY symbol) latest
            ON latest.symbol = b.symbol AND latest.d = b.trade_date
          LEFT JOIN symbols s ON s.symbol = b.symbol
    """
    params: list[Any] = []
    if index_code:
        stamp = _latest_as_of(database, index_code.upper())
        sql += """
          JOIN index_memberships m
            ON m.symbol = b.symbol AND m.index_code = ? AND m.as_of = ?
        """
        params.extend([index_code.upper(), stamp])
    sql += " ORDER BY COALESCE(b.volume, 0) DESC, b.symbol"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [dict(row) for row in database.conn.execute(sql, params).fetchall()]


def price_history(
    db: PsxDatabase | None = None,
    *,
    path: str | None = None,
    symbol: str,
    since: str | None = None,
    limit: int | None = None,
    table: str = "eod_bars",
) -> list[dict[str, Any]]:
    """Stored bars for a symbol (or an index), newest first."""
    database = _db(db, path)
    if table not in {"eod_bars", "index_bars"}:
        raise ValueError(f"unsupported table {table!r}")
    key = "index_code" if table == "index_bars" else "symbol"
    sql = f"SELECT * FROM {table} WHERE {key} = ?"
    params: list[Any] = [symbol.strip().upper()]
    if since:
        sql += " AND trade_date >= ?"
        params.append(since)
    sql += " ORDER BY trade_date DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [dict(row) for row in database.conn.execute(sql, params).fetchall()]


def index_levels(db: PsxDatabase | None = None, *, path: str | None = None) -> list[dict[str, Any]]:
    database = _db(db, path)
    return [
        dict(row)
        for row in database.conn.execute(
            "SELECT code, name, level, change, change_pct, high, low, as_of "
            "FROM indices ORDER BY code"
        ).fetchall()
    ]


def market_summary(db: PsxDatabase | None = None, *, path: str | None = None) -> dict[str, Any]:
    """Breadth for the most recent stored trading date."""
    database = _db(db, path)
    latest = database.conn.execute("SELECT MAX(trade_date) AS d FROM eod_bars").fetchone()
    trade_date = latest["d"] if latest else None
    if not trade_date:
        return {"trade_date": None, "symbols": 0, "indices": index_levels(database)}
    rows = database.conn.execute(
        "SELECT symbol, close, prev_close, volume FROM eod_bars WHERE trade_date = ?",
        (trade_date,),
    ).fetchall()
    advances = sum(1 for row in rows if row["prev_close"] and row["close"] and row["close"] > row["prev_close"])
    declines = sum(1 for row in rows if row["prev_close"] and row["close"] and row["close"] < row["prev_close"])
    unchanged = len(rows) - advances - declines
    traded_value = sum((row["close"] or 0) * (row["volume"] or 0) for row in rows)
    return {
        "trade_date": trade_date,
        "symbols": len(rows),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "approx_value_pkr": round(traded_value, 2),
        "indices": index_levels(database),
    }


def run_fundamentals(
    db: PsxDatabase | None = None, *, path: str | None = None, symbol: str
) -> dict[str, Any]:
    """Everything the database holds for one symbol, shaped for the analyst desk."""
    database = _db(db, path)
    code = symbol.strip().upper()
    profile = database.conn.execute(
        "SELECT symbol, name, sector, sector_code, listed_in FROM symbols WHERE symbol = ?",
        (code,),
    ).fetchone()
    snapshots = database.conn.execute(
        "SELECT * FROM company_snapshots WHERE symbol = ? ORDER BY as_of DESC", (code,)
    ).fetchall()
    financials = database.conn.execute(
        "SELECT period, metric, fiscal_year, quarter, label, value "
        "FROM company_financials WHERE symbol = ? "
        "ORDER BY fiscal_year DESC, COALESCE(quarter, 0) DESC, metric",
        (code,),
    ).fetchall()
    last_bar = database.conn.execute(
        "SELECT trade_date, close, prev_close, volume FROM eod_bars WHERE symbol = ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    memberships = database.conn.execute(
        "SELECT DISTINCT index_code FROM index_memberships WHERE symbol = ? ORDER BY index_code",
        (code,),
    ).fetchall()

    periods: dict[str, dict[str, Any]] = {}
    for row in financials:
        entry = periods.setdefault(
            row["period"],
            {
                "period": row["period"],
                "fiscal_year": row["fiscal_year"],
                "quarter": row["quarter"],
                "metrics": {},
            },
        )
        entry["metrics"][row["metric"]] = row["value"]
    ordered_periods = sorted(
        periods.values(),
        key=lambda item: (item["fiscal_year"] or 0, item["quarter"] or 0),
        reverse=True,
    )
    return {
        "symbol": code,
        "profile": dict(profile) if profile else None,
        "snapshot": dict(snapshots[0]) if snapshots else None,
        "periods": ordered_periods,
        "financials": [dict(row) for row in financials],
        "last_close": dict(last_bar) if last_bar else None,
        "indices": [row["index_code"] for row in memberships],
    }


def ensure_initialised(db: PsxDatabase | None = None, path: str | None = None) -> PsxDatabase:
    database = _db(db, path)
    database.initialise()
    return database


__all__ = [
    "DEFAULT_INDICES",
    "constituents",
    "database_stats",
    "ensure_initialised",
    "index_levels",
    "latest_quotes",
    "market_summary",
    "price_history",
    "run_fundamentals",
    "symbols",
]
