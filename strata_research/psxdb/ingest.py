"""Ingestion pipeline: PSX Data Portal → SQLite.

Order of work (each step is independent, so a partial run still leaves a usable
database and every failure is reported rather than fatal):

1. ``GET /historical``   — the portal's own "latest trading date" stamp, so
                           every row is filed under the trading day the portal
                           is actually showing.
2. ``GET /screener``     — the whole listed market in one page: every symbol
                           with its sector code, index memberships, market cap,
                           price, change, 1-year change, P/E, dividend yield,
                           free float and 30-day average volume.
3. ``GET /indices``      — level, day high/low and change for each published
                           index (this is where KSE100 / KMI30 levels come from).
4. ``GET /indices/{CODE}``— the constituents of each tracked index, with LDCP,
                           today's price, volume, index weight and points. This
                           is the authoritative constituent list — nothing is
                           hardcoded, so a rebalance is picked up automatically.
5. ``GET /company/{SYM}`` — per-constituent company page: open/high/low/volume,
                           ranges, circuit breaker, ratios, and the financial
                           line items the company publishes.

What the portal does **not** publish any more (all returning 404 from nginx):
``/symbols``, ``/market-watch``, ``/timeseries/eod/{symbol}``. There is
therefore no historical price series to backfill. Each run stores the trading
day the portal shows plus LDCP, so running the ingest daily builds a genuine
day-by-day series — and nothing is ever filled in from another provider.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .capture import save_capture
from .client import PortalError, PortalSchemaError
from .parsers import (
    ParseError,
    parse_company_financials,
    parse_company_meta,
    parse_company_stats,
    parse_index_constituents,
    parse_indices,
    parse_latest_trade_date,
    parse_screener,
)
from .schema import DEFAULT_INDICES
from .store import PsxDatabase

SOURCE = "dps.psx.com.pk"

#: Raw HTML kept in ``raw_payloads`` is truncated; the sha256 is the audit trail
#: and the full body lives in the capture directory.
RAW_BODY_LIMIT = 8_000


@dataclass
class IngestReport:
    run_id: int
    mode: str
    indices: list[str] = field(default_factory=list)
    trade_date: str | None = None
    requests: int = 0
    rows: dict[str, int] = field(default_factory=dict)
    constituents: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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
            "trade_date": self.trade_date,
            "requests": self.requests,
            "rows": self.rows,
            "rows_written": self.rows_written,
            "errors": self.errors,
            "warnings": self.warnings,
            "constituents": {code: len(symbols) for code, symbols in self.constituents.items()},
            "notes": self.notes,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round(self.duration_s, 2),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_raw(db: PsxDatabase, run_id: int, response: Any, *, keep_body: bool) -> None:
    """Record provenance. Never allowed to break ingestion."""
    try:
        db.log_raw(
            run_id,
            response.endpoint,
            response.url,
            getattr(response, "status", None),
            response.body if keep_body else "",
            response.sha256,
            max_bytes=RAW_BODY_LIMIT if keep_body else 0,
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _fallback_trade_date(today: date | None = None) -> date:
    """Last weekday on/before ``today`` (Karachi), used only if the portal is mute."""
    day = today or date.today()
    while day.weekday() >= 5:
        day = date.fromordinal(day.toordinal() - 1)
    return day


def ingest(
    client: Any,
    db: PsxDatabase,
    *,
    indices: Sequence[str] = DEFAULT_INDICES,
    include_company_pages: bool = True,
    company_limit: int | None = None,
    workers: int = 3,
    as_of: date | None = None,
    capture_dir: Path | None = None,
    log: Callable[[str], None] = print,
) -> IngestReport:
    """Run the full ingestion and return a report (also stored in the database)."""
    db.initialise()
    codes = [code.strip().upper() for code in indices if code and code.strip()]
    report = IngestReport(run_id=db.start_run("live", codes), mode="live", indices=codes)
    report.requests = 0
    report.started_at = _now()
    started = datetime.now(timezone.utc)
    report.rows = {
        key: 0
        for key in (
            "symbols",
            "memberships",
            "market_bars",
            "index_bars",
            "index_levels",
            "snapshots",
            "financials",
        )
    }
    lock = threading.Lock()

    def warn(message: str) -> None:
        report.warnings.append(message)
        log(f"warning: {message}")

    def fail(message: str) -> None:
        report.errors.append(message)
        log(f"error: {message}")

    # 0 ------------------------------------------------------- trading date
    target_date = as_of
    if target_date is None:
        try:
            page = client.historical_page()
            _log_raw(db, report.run_id, page, keep_body=False)
            stamp_date, stamp_source = parse_latest_trade_date(page.body)
        except (PortalError, PortalSchemaError) as exc:
            stamp_date, stamp_source = None, "unavailable"
            warn(f"historical page: {exc}")
        target_date = stamp_date or as_of or _fallback_trade_date()
        report.notes["trade_date_source"] = stamp_source if stamp_date else "computed-last-weekday"
    else:
        report.notes["trade_date_source"] = "caller-supplied"
    report.trade_date = target_date.isoformat()

    # 1 --------------------------------------------------------- the universe
    screener_rows: dict[str, Any] = {}
    try:
        page = client.screener()
        _log_raw(db, report.run_id, page, keep_body=True)
        rows = parse_screener(page.body)
        snapshot_as_of = target_date
        symbols_payload = [
            {
                "symbol": row.symbol,
                "name": row.name,
                "sector_code": row.sector_code,
                "listed_in": row.listed_in,
            }
            for row in rows
        ]
        report.rows["symbols"] = db.upsert_symbols(symbols_payload, f"{SOURCE}/screener")
        for row in rows:
            screener_rows[row.symbol] = row
            db.upsert_snapshot(
                row.symbol,
                snapshot_as_of,
                {
                    "price": row.price,
                    "market_cap": row.market_cap,
                    "pe": row.pe,
                    "dividend_yield": row.dividend_yield,
                    "free_float": row.free_float,
                    "year_change_pct": row.year_change_pct,
                    "avg_volume_30d": row.avg_volume_30d,
                },
                f"{SOURCE}/screener",
                raw_hash=page.sha256,
            )
            report.rows["snapshots"] += 1
        log(f"screener: {len(rows)} listed symbols")
    except (PortalError, ParseError) as exc:
        fail(f"screener: {exc}")

    # 2 ------------------------------------------------------- index levels
    try:
        page = client.indices_page()
        _log_raw(db, report.run_id, page, keep_body=True)
        levels = parse_indices(page.body)
        payload = [
            {
                "code": row.code,
                "name": row.name,
                "level": row.level,
                "change": row.change,
                "change_pct": row.change_pct,
                "high": row.high,
                "low": row.low,
                "as_of": target_date,
            }
            for row in levels
        ]
        report.rows["index_levels"] = db.upsert_indices(payload, f"{SOURCE}/indices")
        bars = [
            {
                "trade_date": target_date,
                "open": None,
                "high": row.high,
                "low": row.low,
                "close": row.level,
                # the portal publishes change, so the previous level is derivable
                "prev_close": (row.level - row.change)
                if row.level is not None and row.change is not None
                else None,
                "volume": None,
            }
            for row in levels
            if row.level is not None
        ]
        for row in levels:
            if row.level is not None:
                report.rows["index_bars"] += db.upsert_bars(
                    row.code,
                    [
                        {
                            "trade_date": target_date,
                            "high": row.high,
                            "low": row.low,
                            "close": row.level,
                            "prev_close": (row.level - row.change)
                            if row.change is not None
                            else None,
                        }
                    ],
                    f"{SOURCE}/indices",
                    table="index_bars",
                    key_column="index_code",
                )
        del bars
        log(f"indices: {len(levels)} levels stored")
    except (PortalError, ParseError) as exc:
        fail(f"indices: {exc}")
        levels = []

    # 3 -------------------------------------------------- index constituents
    membership: dict[str, list[str]] = {code: [] for code in codes}
    quotes: dict[str, dict[str, Any]] = {}
    for code in codes:
        try:
            page = client.index_constituents(code)
            _log_raw(db, report.run_id, page, keep_body=True)
            members = parse_index_constituents(page.body, code)
        except (PortalError, ParseError) as exc:
            fail(f"indices/{code}: {exc}")
            continue

        membership[code] = sorted({member.symbol for member in members})
        report.rows["memberships"] += db.upsert_memberships(
            code,
            [
                {
                    "symbol": member.symbol,
                    "weight_pct": member.weight_pct,
                    "index_points": member.index_points,
                }
                for member in members
            ],
            target_date,
            f"{SOURCE}/indices/{code}",
        )
        db.upsert_symbols(
            [
                {"symbol": member.symbol, "name": member.name, "listed_in": {code}}
                for member in members
            ],
            f"{SOURCE}/indices/{code}",
        )
        for member in members:
            previous = quotes.get(member.symbol, {})
            quotes[member.symbol] = {
                "close": member.close if member.close is not None else previous.get("close"),
                "prev_close": member.ldcp if member.ldcp is not None else previous.get("prev_close"),
                "volume": member.volume if member.volume is not None else previous.get("volume"),
                "change": member.change,
                "change_pct": member.change_pct,
            }
        log(f"indices/{code}: {len(members)} constituents")

    constituent_set = sorted({symbol for symbols in membership.values() for symbol in symbols})
    report.constituents = {code: symbols for code, symbols in membership.items()}
    for code, symbols in membership.items():
        if not symbols:
            fail(f"membership: no {code} constituents could be parsed")

    # today's bars from the constituent tables (close + previous close + volume)
    for symbol, quote in quotes.items():
        bar = {
            "trade_date": target_date,
            "close": quote.get("close"),
            "prev_close": quote.get("prev_close"),
            "volume": quote.get("volume"),
        }
        if bar["close"] is None and bar["prev_close"] is None:
            continue
        report.rows["market_bars"] += db.upsert_bars(symbol, [bar], f"{SOURCE}/indices")

    # 4 -------------------------------------------------- company snapshots
    company_targets = list(constituent_set)
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
                meta = parse_company_meta(page.body)
            except (ParseError, PortalSchemaError) as exc:
                return symbol, f"{symbol}: {exc}"
            except Exception as exc:  # pragma: no cover - defensive
                return symbol, f"{symbol}: {type(exc).__name__}: {exc}"
            with lock:
                _log_raw(db, report.run_id, page, keep_body=True)
                db.upsert_snapshot(
                    symbol,
                    target_date,
                    stats,
                    f"{SOURCE}/company/{symbol}",
                    sector=meta.get("sector"),
                    raw_hash=page.sha256,
                )
                report.rows["snapshots"] += 1
                if meta.get("name"):
                    db.upsert_symbols(
                        [
                            {
                                "symbol": symbol,
                                "name": meta["name"],
                                "sector": meta.get("sector"),
                            }
                        ],
                        f"{SOURCE}/company/{symbol}",
                    )
                if financials:
                    report.rows["financials"] += db.upsert_financials(
                        symbol, financials, f"{SOURCE}/company/{symbol}"
                    )
            return symbol, None

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_company, symbol): symbol for symbol in company_targets}
            for future in as_completed(futures):
                symbol, error = future.result()
                if error:
                    fail(f"company: {error}")

    # -------------------------------------------------------------- finalise
    report.requests = int(getattr(client, "requests_made", 0))
    report.finished_at = _now()
    report.duration_s = (datetime.now(timezone.utc) - started).total_seconds()
    report.notes.update(
        {
            "constituents": {code: len(items) for code, items in report.constituents.items()},
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "withdrawn_routes": ["/symbols", "/market-watch", "/timeseries/eod/{symbol}"],
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
        responses = getattr(client, "responses", []) or []
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


__all__ = ["IngestReport", "SOURCE", "ingest", "ingest_from_capture"]
