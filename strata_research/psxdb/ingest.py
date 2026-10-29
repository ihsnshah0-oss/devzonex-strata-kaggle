"""Ingestion pipeline: PSX Data Portal → SQLite.

Order of work (each step is independent, so a partial run still leaves a usable
database):

1. ``GET /symbols``            — the listed universe, sectors and flags.
2. ``GET /market-watch``       — today's quotes **and index membership**, which is
                                 how the KSE100 / KMI30 constituent lists are
                                 derived (nothing is hardcoded, so PSX rebalances
                                 are picked up automatically).
3. ``GET /timeseries/eod/{i}`` — daily bars for the index itself.
4. ``GET /timeseries/eod/{s}`` — daily bars for every constituent, one request
                                 each, ~5 years of history per call.
5. ``GET /company/{s}``        — company statistics (market cap, P/E, free float,
                                 52-week range) plus any annual financials the
                                 page exposes.
6. ``GET /indices``            — fallback levels if a step above failed.

Failures are collected per item: one dead symbol never aborts a run. The run is
recorded in ``ingest_runs`` with request/row/error counts, and every response's
size and sha256 is stored in ``raw_payloads`` so a figure can be traced back.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .capture import save_capture
from .client import PortalError, PortalSchemaError
from .parsers import (
    ParseError,
    parse_company_financials,
    parse_company_stats,
    parse_eod_series,
    parse_indices,
    parse_market_watch,
)
from .schema import DEFAULT_INDICES
from .store import PsxDatabase

SOURCE = "dps.psx.com.pk"


@dataclass
class IngestReport:
    run_id: int
    mode: str
    indices: list[str] = field(default_factory=list)
    requests: int = 0
    rows: dict[str, int] = field(default_factory=dict)
    constituents: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0

    @property
    def rows_written(self) -> int:
        return sum(self.rows.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "source": SOURCE,
            "indices": self.indices,
            "requests": self.requests,
            "rows": self.rows,
            "rows_written": self.rows_written,
            "errors": self.errors,
            "constituents": {code: len(symbols) for code, symbols in self.constituents.items()},
            "notes": self.notes,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.duration_s, 2),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_raw(db: PsxDatabase, run_id: int, response: Any, *, keep_body: bool) -> None:
    try:
        db.log_raw(
            run_id,
            response.endpoint,
            response.url,
            getattr(response, "status", None),
            response.body if keep_body else "",
            response.sha256,
            max_bytes=200_000 if keep_body else 0,
        )
    except Exception:  # provenance must never break ingestion
        pass


def ingest(
    client: Any,
    db: PsxDatabase,
    *,
    indices: Sequence[str] = DEFAULT_INDICES,
    history_days: int = 400,
    include_company_pages: bool = True,
    company_limit: int | None = None,
    workers: int = 3,
    as_of: date | None = None,
    capture_dir: Path | None = None,
    log: Callable[[str], None] = print,
    expected_constituents: dict[str, set[str]] | None = None,
) -> IngestReport:
    """Run the full ingestion and return a report (also stored in the database)."""
    db.initialise()
    codes = [code.strip().upper() for code in indices if code and code.strip()]
    report = IngestReport(run_id=db.start_run("live", codes), mode="live", indices=codes)
    report.started_at = _now()
    started = datetime.now(timezone.utc)
    report.rows = {key: 0 for key in (
        "symbols", "memberships", "market_bars", "index_bars", "snapshots", "financial_years"
    )}
    target_date = as_of or date.today()

    def note(message: str) -> None:
        report.errors.append(message) if message.startswith("ERROR ") else None
        log(message)

    # 1 ---------------------------------------------------------- universe
    try:
        symbols = client.symbols()
        _log_raw(db, report.run_id, client.responses[-1], keep_body=False)
        report.rows["symbols"] = db.upsert_symbols(symbols, SOURCE)
        log(f"symbols: {report.rows['symbols']} listed instruments")
    except (PortalError, ParseError) as exc:
        note(f"ERROR symbols: {exc}")
        symbols = []
    sector_by_symbol = {row["symbol"]: row.get("sector") for row in symbols}

    # 2 ------------------------------------------------------- market watch
    membership: dict[str, list[str]] = {code: [] for code in codes}
    watch_quotes: dict[str, Any] = {}
    try:
        page = client.market_watch()
        _log_raw(db, report.run_id, page, keep_body=True)
        watch_rows = parse_market_watch(page.body)
        for row in watch_rows:
            watch_quotes[row.symbol] = row
            for code in codes:
                if code in row.indices:
                    membership[code].append(row.symbol)
            for token in row.indices:
                if token not in membership:
                    membership.setdefault(token, []).append(row.symbol)
        log(
            "market-watch: {rows} quotes; membership found -> {summary}".format(
                rows=len(watch_rows),
                summary=", ".join(f"{code}:{len(membership.get(code, []))}" for code in codes),
            )
        )
        for code in codes:
            if not membership.get(code):
                note(
                    f"ERROR membership: no {code} constituents found in market-watch "
                    "(the membership column may have moved)"
                )
    except (PortalError, ParseError) as exc:
        note(f"ERROR market-watch: {exc}")

    # If the portal's membership column was unusable, fall back to an explicit list.
    if expected_constituents:
        for code, symbols_for_code in expected_constituents.items():
            if not membership.get(code):
                membership[code] = sorted(symbols_for_code)
                report.notes.setdefault("membership_overrides", []).append(code)

    for code in codes:
        unique = sorted(dict.fromkeys(membership.get(code, [])))
        report.constituents[code] = unique
        if unique:
            report.rows["memberships"] += db.upsert_memberships(
                code, unique, target_date, SOURCE
            )

    # today's bars from the watch table (the only source with intraday high/low)
    watch_bars = {
        symbol: {
            "trade_date": target_date,
            "ts": None,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.current if row.current is not None else row.ldcp,
            "volume": row.volume,
        }
        for symbol, row in watch_quotes.items()
        if (row.current is not None or row.ldcp is not None)
    }
    if watch_bars:
        for symbol, bar in watch_bars.items():
            report.rows["market_bars"] += db.upsert_bars(symbol, [bar], f"{SOURCE}/market-watch")

    # 3/4 ------------------------------------------------ daily price series
    cutoff = target_date - timedelta(days=max(30, history_days))
    constituent_set = sorted({symbol for symbols_for_code in membership.values() for symbol in symbols_for_code})
    index_codes_in_universe = sorted(set(codes) | set(membership.keys()) & set(codes))
    price_targets = sorted(set(constituent_set) | set(index_codes_in_universe))

    lock = threading.Lock()

    def fetch_eod(symbol: str) -> tuple[str, str | None]:
        is_index = symbol in codes
        try:
            series = parse_eod_series(client.eod(symbol).json(), symbol)
        except (PortalError, PortalSchemaError, ParseError) as exc:
            return symbol, f"{symbol}: {exc}"
        bars = [bar for bar in series if bar["trade_date"] >= cutoff]
        if not bars:
            return symbol, f"{symbol}: no bars on/after {cutoff.isoformat()}"
        with lock:
            if is_index:
                report.rows["index_bars"] += db.upsert_bars(
                    symbol, bars, f"{SOURCE}/timeseries/eod", table="index_bars",
                    key_column="index_code",
                )
            else:
                report.rows["market_bars"] += db.upsert_bars(
                    symbol, bars, f"{SOURCE}/timeseries/eod"
                )
        return symbol, None

    if price_targets:
        log(f"price series: {len(price_targets)} symbols since {cutoff.isoformat()}")
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_eod, symbol): symbol for symbol in price_targets}
            for future in as_completed(futures):
                symbol, error = future.result()
                if error:
                    report.errors.append(f"ERROR eod: {error}")

    # index levels from the stored series
    index_rows = []
    for code in codes:
        row = db.conn.execute(
            "SELECT close, trade_date FROM index_bars WHERE index_code = ? "
            "ORDER BY trade_date DESC LIMIT 2",
            (code,),
        ).fetchall()
        if row:
            latest = row[0]
            previous = row[1] if len(row) > 1 else None
            change = None
            change_pct = None
            if previous and previous["close"]:
                change = latest["close"] - previous["close"]
                change_pct = change / previous["close"] * 100.0
            index_rows.append(
                {
                    "code": code,
                    "name": f"{code} Index",
                    "level": latest["close"],
                    "change": change,
                    "change_pct": change_pct,
                    "as_of": latest["trade_date"],
                }
            )
    if index_rows:
        db.upsert_indices(index_rows, f"{SOURCE}/timeseries/eod")

    # 6 ---------------------------------------------- fallback index levels
    try:
        page = client.indices_page()
        _log_raw(db, report.run_id, page, keep_body=True)
        fallback = [
            {
                "code": row.code,
                "name": row.name,
                "level": row.level,
                "change": row.change,
                "change_pct": row.change_pct,
                "high": row.high,
                "low": row.low,
                "volume": row.volume,
                "as_of": target_date,
            }
            for row in parse_indices(page.body)
            if row.code in codes
        ]
        if fallback:
            db.upsert_indices(fallback, f"{SOURCE}/indices")
            report.notes["index_levels_from"] = [row["code"] for row in fallback]
    except (PortalError, ParseError) as exc:
        report.notes.setdefault("warnings", []).append(f"indices page: {exc}")

    # 5 -------------------------------------------------- company snapshots
    company_targets = sorted(constituent_set)
    if company_limit is not None:
        company_targets = company_targets[: max(0, company_limit)]
    if include_company_pages and company_targets:
        log(f"company pages: {len(company_targets)}")

        def fetch_company(symbol: str) -> tuple[str, str | None]:
            try:
                page = client.company(symbol)
            except PortalError as exc:
                return symbol, f"{symbol}: {exc}"
            try:
                stats = parse_company_stats(page.body)
                financials = parse_company_financials(page.body)
            except ParseError as exc:
                return symbol, f"{symbol}: {exc}"
            with lock:
                _log_raw(db, report.run_id, page, keep_body=True)
                db.upsert_snapshot(
                    symbol,
                    target_date,
                    stats,
                    f"{SOURCE}/company",
                    sector=sector_by_symbol.get(symbol),
                    raw_hash=page.sha256,
                )
                report.rows["snapshots"] += 1
                if financials:
                    report.rows["financial_years"] += db.upsert_financial_years(
                        symbol, financials, f"{SOURCE}/company"
                    )
            return symbol, None

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_company, symbol): symbol for symbol in company_targets}
            for future in as_completed(futures):
                symbol, error = future.result()
                if error:
                    report.errors.append(f"ERROR company: {error}")

    # ------------------------------------------------------------ finalise
    report.requests = int(getattr(client, "requests_made", 0))
    report.finished_at = _now()
    report.duration_s = (datetime.now(timezone.utc) - started).total_seconds()
    report.notes.update(
        {
            "history_days": history_days,
            "cutoff": cutoff.isoformat(),
            "constituents": {code: len(items) for code, items in report.constituents.items()},
            "errors": len(report.errors),
        }
    )
    db.finish_run(
        report.run_id,
        requests=report.requests,
        rows_written=report.rows_written,
        errors=len(report.errors),
        notes=report.notes,
    )

    if capture_dir is not None:
        responses = getattr(client, "responses", [])
        if responses:
            manifest = save_capture(responses, Path(capture_dir))
            report.notes["capture"] = {
                "directory": str(capture_dir),
                "files": len(manifest.get("files", [])),
            }
            log(f"capture saved: {capture_dir} ({len(manifest.get('files', []))} files)")

    log(
        "done: {rows} rows, {requests} requests, {errors} error(s) in {secs:.1f}s".format(
            rows=report.rows_written,
            requests=report.requests,
            errors=len(report.errors),
            secs=report.duration_s,
        )
    )
    return report


def ingest_from_capture(
    capture_dir: Path,
    db: PsxDatabase,
    *,
    indices: Sequence[str] = DEFAULT_INDICES,
    history_days: int = 400,
    include_company_pages: bool = True,
    log: Callable[[str], None] = print,
) -> IngestReport:
    """Ingest from a saved capture directory (no network access at all)."""
    from .capture import CaptureClient

    client = CaptureClient(Path(capture_dir))
    report = ingest(
        client,
        db,
        indices=indices,
        history_days=history_days,
        include_company_pages=include_company_pages,
        workers=1,
        log=log,
    )
    report.mode = "capture"
    with db.transaction() as connection:
        connection.execute(
            "UPDATE ingest_runs SET mode = 'capture' WHERE run_id = ?", (report.run_id,)
        )
    return report
