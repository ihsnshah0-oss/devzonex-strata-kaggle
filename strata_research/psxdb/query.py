"""Read helpers over the PSX portal database."""

from __future__ import annotations

from datetime import date
from typing import Any

from .parsers import derive_trade_date
from .schema import DEFAULT_INDICES
from .store import PsxDatabase


def _db(db: PsxDatabase | None, path: str | None) -> PsxDatabase:
    if db is not None:
        return db
    from pathlib import Path

    return PsxDatabase(Path(path) if path else "data/psx.db")


def database_stats(db: PsxDatabase | None = None, path: str | None = None) -> dict[str, Any]:
    database = _db(db, path)
    counts = database.table_counts()
    coverage = {}
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
    indices = [
        dict(row)
        for row in database.conn.execute(
            "SELECT code, level, change, change_pct, as_of FROM indices ORDER BY code"
        ).fetchall()
    ]
    return {
        "path": str(database.path),
        "schema_version": database.schema_version,
        "tables": counts,
        "coverage": coverage,
        "indices": indices,
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
    sql = "SELECT symbol, name, sector, is_etf, is_debt FROM symbols"
    params: list[Any] = []
    if sector:
        sql += " WHERE LOWER(sector) LIKE ?"
        params.append(f"%{sector.lower()}%")
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
    """Members of an index as of a snapshot date (latest by default)."""
    database = _db(db, path)
    code = index_code.strip().upper()
    stamp = as_of or _latest_as_of(database, code)
    if not stamp:
        return []
    rows = database.conn.execute(
        """
        SELECT m.symbol, s.name, s.sector, m.as_of
          FROM index_memberships m
          LEFT JOIN symbols s ON s.symbol = m.symbol
         WHERE m.index_code = ? AND m.as_of = ?
         ORDER BY m.symbol
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
    database = _db(db, path)
    sql = """
        SELECT b.symbol, s.name, s.sector, b.trade_date, b.close, b.open, b.high, b.low,
               b.volume, p.close AS prev_close,
               CASE WHEN p.close IS NOT NULL AND p.close <> 0
                    THEN (b.close - p.close) / p.close * 100.0 END AS change_pct
          FROM eod_bars b
          JOIN (SELECT symbol, MAX(trade_date) AS d FROM eod_bars GROUP BY symbol) latest
            ON latest.symbol = b.symbol AND latest.d = b.trade_date
          LEFT JOIN symbols s ON s.symbol = b.symbol
          LEFT JOIN eod_bars p
            ON p.symbol = b.symbol
           AND p.trade_date = (
                 SELECT MAX(trade_date) FROM eod_bars
                  WHERE symbol = b.symbol AND trade_date < b.trade_date
               )
    """
    params: list[Any] = []
    if index_code:
        stamp = _latest_as_of(database, index_code.upper())
        sql += """
          JOIN index_memberships m
            ON m.symbol = b.symbol AND m.index_code = ? AND m.as_of = ?
        """
        params.extend([index_code.upper(), stamp])
    sql += " ORDER BY b.volume DESC NULLS LAST, b.symbol"
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
    database = _db(db, path)
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
            "SELECT code, name, level, change, change_pct, high, low, volume, as_of "
            "FROM indices ORDER BY code"
        ).fetchall()
    ]


def market_summary(db: PsxDatabase | None = None, *, path: str | None = None) -> dict[str, Any]:
    """Breadth and coverage snapshot over the most recent trading date."""
    database = _db(db, path)
    latest = database.conn.execute("SELECT MAX(trade_date) AS d FROM eod_bars").fetchone()
    trade_date = latest["d"] if latest else None
    if not trade_date:
        return {"trade_date": None, "symbols": 0}
    rows = database.conn.execute(
        """
        SELECT b.symbol, b.close, b.volume, p.close AS prev
          FROM eod_bars b
          LEFT JOIN eod_bars p
            ON p.symbol = b.symbol
           AND p.trade_date = (SELECT MAX(trade_date) FROM eod_bars
                                WHERE symbol = b.symbol AND trade_date < b.trade_date)
         WHERE b.trade_date = ?
        """,
        (trade_date,),
    ).fetchall()
    advances = sum(1 for row in rows if row["prev"] and row["close"] > row["prev"])
    declines = sum(1 for row in rows if row["prev"] and row["close"] < row["prev"])
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
    """Statements + latest snapshot for a symbol, shaped for the analyst engine."""
    database = _db(db, path)
    code = symbol.strip().upper()
    profile = database.conn.execute(
        "SELECT symbol, name, sector, is_etf, is_debt FROM symbols WHERE symbol = ?", (code,)
    ).fetchone()
    snapshots = database.conn.execute(
        "SELECT * FROM company_snapshots WHERE symbol = ? ORDER BY as_of DESC", (code,)
    ).fetchall()
    years = database.conn.execute(
        "SELECT * FROM company_financial_years WHERE symbol = ? ORDER BY fiscal_year DESC",
        (code,),
    ).fetchall()
    last_bar = database.conn.execute(
        "SELECT trade_date, close FROM eod_bars WHERE symbol = ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,),
    ).fetchone()
    memberships = database.conn.execute(
        "SELECT DISTINCT index_code FROM index_memberships WHERE symbol = ? ORDER BY index_code",
        (code,),
    ).fetchall()
    return {
        "symbol": code,
        "profile": dict(profile) if profile else None,
        "snapshot": dict(snapshots[0]) if snapshots else None,
        "financial_years": [dict(row) for row in years],
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
    "derive_trade_date",
    "date",
]
