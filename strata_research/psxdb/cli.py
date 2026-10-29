"""``python -m strata_research.psxdb`` — PSX Data Portal ingestion CLI.

    # create the database file
    python -m strata_research.psxdb init

    # pull KSE100 + KMI30 (constituents, index levels, ~13 months of daily bars,
    # company statistics) — the only data source is dps.psx.com.pk
    python -m strata_research.psxdb ingest --indices KSE100,KMI30 --days 400

    # save the raw responses while ingesting (for air-gapped replays / audits)
    python -m strata_research.psxdb ingest --capture-dir captures/2026-10-30

    # replay a capture with no network at all
    python -m strata_research.psxdb from-capture captures/2026-10-30

    python -m strata_research.psxdb stats
    python -m strata_research.psxdb constituents KSE100
    python -m strata_research.psxdb history OGDC --limit 10
    python -m strata_research.psxdb indices
    python -m strata_research.psxdb export --table eod_bars --out data/eod.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .client import PsxPortalClient
from .ingest import ingest, ingest_from_capture
from .query import (
    constituents,
    database_stats,
    index_levels,
    latest_quotes,
    market_summary,
    price_history,
    run_fundamentals,
)
from .schema import DEFAULT_INDICES, TABLES
from .store import DEFAULT_DB_PATH, PsxDatabase


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite file (default: data/psx.db)")


def _add_indices(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--indices",
        default=",".join(DEFAULT_INDICES),
        help="comma-separated index codes (default: KSE100,KMI30)",
    )


def cmd_init(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db).initialise()
    print(f"database ready: {db.path} (schema v{db.schema_version})")
    print("tables:", ", ".join(TABLES))
    db.close()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    codes = [code.strip().upper() for code in args.indices.split(",") if code.strip()]
    db = PsxDatabase(args.db).initialise()
    client = PsxPortalClient(
        base_url=args.base_url,
        timeout=args.timeout,
        retries=args.retries,
        min_interval=args.interval,
    )
    try:
        report = ingest(
            client,
            db,
            indices=codes,
            include_company_pages=not args.no_company,
            company_limit=args.company_limit,
            workers=args.workers,
            capture_dir=Path(args.capture_dir) if args.capture_dir else None,
        )
    except Exception as exc:  # surface a clean message in CI logs
        print(f"ingest failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()
        db.close()
    if args.json:
        _print_json(report.to_dict())
    print(
        f"run {report.run_id}: {report.rows_written} rows, {report.requests} requests, "
        f"{len(report.errors)} error(s) for trade date {report.trade_date}"
    )
    for error in report.errors[: args.max_errors]:
        print("  " + error)
    if len(report.errors) > args.max_errors:
        print(f"  … {len(report.errors) - args.max_errors} more")
    for note in report.warnings[: args.max_errors]:
        print("  warning: " + note)
    # A run that fetched nothing is a failure; a few dead symbols are not.
    if report.rows_written == 0:
        return 1
    return 0


def cmd_from_capture(args: argparse.Namespace) -> int:
    codes = [code.strip().upper() for code in args.indices.split(",") if code.strip()]
    db = PsxDatabase(args.db).initialise()
    report = ingest_from_capture(
        Path(args.capture_dir),
        db,
        indices=codes,
        include_company_pages=not args.no_company,
    )
    if args.json:
        _print_json(report.to_dict())
    db.close()
    return 0 if report.rows_written else 1


def cmd_stats(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    if db.schema_version is None:
        print(f"{db.path} is not initialised — run: python -m strata_research.psxdb init")
        return 1
    stats = database_stats(db)
    if args.json:
        _print_json(stats)
        db.close()
        return 0
    print(f"database: {stats['path']} (schema v{stats['schema_version']})")
    if stats.get("memberships"):
        print("members (latest snapshot):",
              ", ".join(f"{code} {count}" for code, count in sorted(stats["memberships"].items())))
    print("rows:")
    for table, count in stats["tables"].items():
        print(f"  {table:26s} {count:>8}")
    print("coverage:")
    for table, info in stats["coverage"].items():
        if info and info.get("bars"):
            print(
                f"  {table:12s} {info['entities']:>4} entities · {info['bars']} bars · "
                f"{info['first_date']} → {info['last_date']}"
            )
    if stats["indices"]:
        print("indices:")
        for row in stats["indices"]:
            change = row.get("change")
            pct = row.get("change_pct")
            rendered = f"{row['level']:,.2f}" if row.get("level") else "n/a"
            extra = ""
            if change is not None and pct is not None:
                extra = f" ({change:+,.2f}, {pct:+.2f}%)"
            print(f"  {row['code']:10s} {rendered}{extra}  as of {row.get('as_of')}")
    run = stats["last_run"]
    if run:
        print(
            f"last run: #{run['run_id']} {run['mode']} {run['started_at']} → "
            f"{run['finished_at']} · {run['rows_written']} rows · {run['errors']} error(s)"
        )
    db.close()
    return 0


def cmd_constituents(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    rows = constituents(db, index_code=args.index, as_of=args.as_of)
    db.close()
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print(f"no constituents stored for {args.index.upper()}")
        return 1
    print(f"{args.index.upper()}: {len(rows)} constituents")
    for row in rows:
        print(f"  {row['symbol']:10s} {(row.get('sector') or 'n/a'):28s} {row.get('name') or ''}")
    return 0


def cmd_quotes(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    rows = latest_quotes(db, index_code=args.index, limit=args.limit)
    db.close()
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("no quotes stored — run an ingest first")
        return 1
    print(f"{'SYMBOL':10s} {'DATE':12s} {'CLOSE':>10s} {'CHG%':>8s} {'VOLUME':>14s}")
    for row in rows:
        change = row.get("change_pct")
        change_text = f"{change:+.2f}" if change is not None else "n/a"
        volume = row.get("volume")
        volume_text = f"{volume:,.0f}" if volume else "n/a"
        print(
            f"{row['symbol']:10s} {row['trade_date']:12s} {row['close']:>10,.2f} "
            f"{change_text:>8s} {volume_text:>14s}"
        )
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    rows = price_history(
        db,
        symbol=args.symbol,
        since=args.since,
        limit=args.limit,
        table="index_bars" if args.index else "eod_bars",
    )
    db.close()
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print(f"no bars for {args.symbol.upper()}")
        return 1
    print(f"{args.symbol.upper()}: {len(rows)} bar(s), newest first")
    for row in rows:
        close = f"{row['close']:,.2f}" if row.get("close") is not None else "n/a"
        volume = f"{row['volume']:,.0f}" if row.get("volume") else "n/a"
        print(f"  {row['trade_date']}  close {close:>12s}  volume {volume:>14s}")
    return 0


def cmd_indices(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    rows = index_levels(db)
    db.close()
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("no index levels stored")
        return 1
    for row in rows:
        print(f"{row['code']:10s} {row['level'] or 'n/a':>12} as of {row['as_of']}")
    return 0


def cmd_market(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    summary = market_summary(db)
    db.close()
    if args.json:
        _print_json(summary)
        return 0
    print(f"trade date: {summary.get('trade_date')}")
    print(
        f"symbols {summary.get('symbols', 0)} · advances {summary.get('advances', 0)} · "
        f"declines {summary.get('declines', 0)} · unchanged {summary.get('unchanged', 0)}"
    )
    for row in summary.get("indices", []):
        print(f"  {row['code']:10s} {row.get('level')}")
    return 0


def cmd_fundamentals(args: argparse.Namespace) -> int:
    db = PsxDatabase(args.db)
    payload = run_fundamentals(db, symbol=args.symbol)
    db.close()
    _print_json(payload)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    if args.table not in TABLES:
        print(f"unknown table {args.table!r}; choose from {', '.join(TABLES)}", file=sys.stderr)
        return 1
    db = PsxDatabase(args.db)
    cursor = db.conn.execute(f"SELECT * FROM {args.table} ORDER BY 1, 2")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    db.close()
    target = Path(args.out).expanduser() if args.out else None
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("w", newline="", encoding="utf-8")
    else:
        handle = sys.stdout
    try:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[column] for column in columns])
    finally:
        if target:
            handle.close()
            print(f"wrote {len(rows)} rows to {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m strata_research.psxdb",
        description="Mirror KSE100/KMI30 data from the PSX Data Portal into SQLite.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create the SQLite schema")
    _add_db(init)
    init.set_defaults(handler=cmd_init)

    ingest_parser = subparsers.add_parser("ingest", help="pull data from dps.psx.com.pk")
    _add_db(ingest_parser)
    _add_indices(ingest_parser)
    ingest_parser.add_argument(
        "--days", type=int, default=None,
        help=argparse.SUPPRESS,  # the portal no longer serves a history window
    )
    ingest_parser.add_argument("--workers", type=int, default=3, help="concurrent requests (default 3)")
    ingest_parser.add_argument("--interval", type=float, default=0.25, help="min seconds between requests")
    ingest_parser.add_argument("--timeout", type=float, default=25.0)
    ingest_parser.add_argument("--retries", type=int, default=3)
    ingest_parser.add_argument("--base-url", default="https://dps.psx.com.pk")
    ingest_parser.add_argument("--no-company", action="store_true", help="skip /company pages")
    ingest_parser.add_argument("--company-limit", type=int, default=None)
    ingest_parser.add_argument("--capture-dir", default=None, help="save raw responses here")
    ingest_parser.add_argument("--max-errors", type=int, default=15)
    ingest_parser.add_argument("--json", action="store_true")
    ingest_parser.set_defaults(handler=cmd_ingest)

    capture = subparsers.add_parser("from-capture", help="ingest a saved capture (offline)")
    _add_db(capture)
    _add_indices(capture)
    capture.add_argument("capture_dir")
    capture.add_argument("--days", type=int, default=None, help=argparse.SUPPRESS)
    capture.add_argument("--no-company", action="store_true")
    capture.add_argument("--json", action="store_true")
    capture.set_defaults(handler=cmd_from_capture)

    stats = subparsers.add_parser("stats", help="row counts, coverage and last run")
    _add_db(stats)
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(handler=cmd_stats)

    members = subparsers.add_parser("constituents", help="index members from the last snapshot")
    _add_db(members)
    members.add_argument("index", nargs="?", default="KSE100")
    members.add_argument("--as-of", default=None)
    members.add_argument("--json", action="store_true")
    members.set_defaults(handler=cmd_constituents)

    quotes = subparsers.add_parser("quotes", help="latest close per symbol")
    _add_db(quotes)
    quotes.add_argument("--index", default=None, help="restrict to an index's members")
    quotes.add_argument("--limit", type=int, default=25)
    quotes.add_argument("--json", action="store_true")
    quotes.set_defaults(handler=cmd_quotes)

    history = subparsers.add_parser("history", help="daily bars for a symbol or index")
    _add_db(history)
    history.add_argument("symbol")
    history.add_argument("--since", default=None)
    history.add_argument("--limit", type=int, default=10)
    history.add_argument("--index", action="store_true", help="read index_bars instead of eod_bars")
    history.add_argument("--json", action="store_true")
    history.set_defaults(handler=cmd_history)

    indices_parser = subparsers.add_parser("indices", help="stored index levels")
    _add_db(indices_parser)
    indices_parser.add_argument("--json", action="store_true")
    indices_parser.set_defaults(handler=cmd_indices)

    market = subparsers.add_parser("market", help="breadth summary for the latest trading day")
    _add_db(market)
    market.add_argument("--json", action="store_true")
    market.set_defaults(handler=cmd_market)

    fundamentals = subparsers.add_parser("fundamentals", help="stored statements + snapshot")
    _add_db(fundamentals)
    fundamentals.add_argument("symbol")
    fundamentals.set_defaults(handler=cmd_fundamentals)

    export = subparsers.add_parser("export", help="dump a table as CSV")
    _add_db(export)
    export.add_argument("--table", default="eod_bars")
    export.add_argument("--out", default=None)
    export.set_defaults(handler=cmd_export)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "db"):
        args.db = str(DEFAULT_DB_PATH)
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
