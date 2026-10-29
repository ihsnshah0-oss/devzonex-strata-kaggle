"""Tests for the PSX Data Portal mirror (``strata_research.psxdb``).

Everything here runs offline against hand-written fixtures modelled on the
portal's markup: the parsers must survive real-world HTML quirks, the store must
be idempotent, and a full capture replay must produce a queryable database.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from strata_research.psxdb import (
    PsxDatabase,
    PsxPortalClient,
    constituents,
    database_stats,
    index_levels,
    ingest,
    ingest_from_capture,
    latest_quotes,
    market_summary,
    price_history,
    run_fundamentals,
    symbols,
)
from strata_research.psxdb.capture import CaptureClient, save_capture
from strata_research.psxdb.cli import main as cli_main
from strata_research.psxdb.parsers import (
    ParseError,
    derive_trade_date,
    parse_company_financials,
    parse_company_stats,
    parse_eod_series,
    parse_indices,
    parse_market_watch,
    to_float,
)
from strata_research.psxdb.schema import TABLES

FIXTURES = Path(__file__).parent / "fixtures" / "psx"


# --------------------------------------------------------------------- helpers
def _epoch(day: str, hour: int = 15, minute: int = 30) -> int:
    """PSX emits Pakistan wall-clock seconds, so a 15:30 close is stored as 15:30 UTC."""
    naive = datetime.strptime(f"{day} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    return int(naive.replace(tzinfo=timezone.utc).timestamp())


def build_capture(directory: Path, *, symbols_list: list[str] | None = None) -> Path:
    """Assemble a capture directory from the fixtures (the air-gapped replay input)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "market-watch.html").write_text(
        (FIXTURES / "market-watch.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (directory / "indices.html").write_text(
        (FIXTURES / "indices.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (directory / "symbols.json").write_text(
        (FIXTURES / "symbols.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    company_dir = directory / "company"
    company_dir.mkdir(exist_ok=True)
    for symbol in ("OGDC", "PPL", "MEBL", "FFC"):
        shutil.copy(FIXTURES / "company" / "OGDC.html", company_dir / f"{symbol}.html")
    eod_dir = directory / "timeseries_eod"
    eod_dir.mkdir(exist_ok=True)
    for series in symbols_list or ["OGDC", "PPL", "MEBL", "FFC", "KSE100", "KMI30"]:
        shutil.copy(FIXTURES / "timeseries_eod" / f"{series}.json", eod_dir / f"{series}.json")
    return directory


@pytest.fixture()
def db(tmp_path: Path) -> PsxDatabase:
    database = PsxDatabase(tmp_path / "psx.db")
    database.initialise()
    yield database
    database.close()


@pytest.fixture()
def capture(tmp_path: Path) -> Path:
    return build_capture(tmp_path / "capture")


# -------------------------------------------------------------------- parsers
def test_parse_market_watch_reads_quotes_and_membership():
    rows = parse_market_watch((FIXTURES / "market-watch.html").read_text(encoding="utf-8"))
    by_symbol = {row.symbol: row for row in rows}

    assert set(by_symbol) == {"OGDC", "PPL", "MEBL", "FFC"}

    ogdc = by_symbol["OGDC"]
    assert ogdc.ldcp == pytest.approx(215.40)
    assert ogdc.open == pytest.approx(216.00)
    assert ogdc.high == pytest.approx(219.90)
    assert ogdc.low == pytest.approx(214.10)
    assert ogdc.current == pytest.approx(218.75)
    assert ogdc.change_pct == pytest.approx(1.56)
    assert ogdc.volume == pytest.approx(4_512_300)
    assert ogdc.sector.startswith("Oil & Gas")
    assert ogdc.indices == {"KSE100"}

    # membership written three different ways on the portal
    assert by_symbol["PPL"].indices == {"KSE100", "KMI30"}
    assert by_symbol["MEBL"].indices == {"KMI30"}
    assert by_symbol["FFC"].indices == {"KSE100", "KMI30"}


def test_parse_market_watch_rejects_a_page_without_a_table():
    with pytest.raises(ParseError):
        parse_market_watch("<html><body><p>maintenance</p></body></html>")


def test_parse_indices_reads_levels():
    rows = parse_indices((FIXTURES / "indices.html").read_text(encoding="utf-8"))
    by_code = {row.code: row for row in rows}
    assert by_code["KSE100"].level == pytest.approx(118420.55)
    assert by_code["KSE100"].change_pct == pytest.approx(0.35)
    assert by_code["KMI30"].change == pytest.approx(-96.30)
    assert "ALLSHR" in by_code


def test_parse_company_stats_finds_every_metric():
    stats = parse_company_stats((FIXTURES / "company" / "OGDC.html").read_text(encoding="utf-8"))
    assert stats["market_cap"] == pytest.approx(940_123_456_789)
    assert stats["shares"] == pytest.approx(4_300_000_000)
    assert stats["free_float"] == pytest.approx(129_000_000)
    assert stats["free_float_pct"] == pytest.approx(3.00)  # not overwritten by free_float
    assert stats["pe"] == pytest.approx(6.85)
    assert stats["pb"] == pytest.approx(0.92)
    assert stats["high_52w"] == pytest.approx(241.50)
    assert stats["low_52w"] == pytest.approx(148.20)
    assert stats["year_change_pct"] == pytest.approx(24.10)
    assert stats["ytd_change_pct"] == pytest.approx(11.60)


def test_parse_company_financials_keeps_tax_out_of_net_income():
    years = parse_company_financials((FIXTURES / "company" / "OGDC.html").read_text(encoding="utf-8"))
    assert [year["fiscal_year"] for year in years] == [2025, 2024, 2023]
    newest = years[0]
    assert newest["revenue"] == pytest.approx(1_412_000_000)
    assert newest["gross_profit"] == pytest.approx(612_400_000)
    # "Profit After Tax" must land in net_income, and "Taxation" in income_tax_expense
    assert newest["net_income"] == pytest.approx(338_900_000)
    assert newest["income_tax_expense"] == pytest.approx(188_400_000)
    assert newest["eps"] == pytest.approx(78.81)
    assert newest["dividend_per_share"] == pytest.approx(11.50)


def test_parse_company_financials_returns_empty_when_page_has_no_table():
    assert parse_company_financials("<html><body>nothing here</body></html>") == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.56", 1234.56),
        ("(12.3)", -12.3),
        ("5.2%", 5.2),
        ("Rs. 99.10", 99.10),
        ("n/a", None),
        ("-", None),
        ("", None),
        ("abc", None),
    ],
)
def test_to_float_handles_portal_formatting(raw, expected):
    assert to_float(raw) == (pytest.approx(expected) if expected is not None else None)


def test_derive_trade_date_maps_karachi_wall_clock_to_the_trading_day():
    # Thursday 15:30 PKT (PSX close) belongs to Thursday, not Friday UTC
    assert derive_trade_date(_epoch("2026-10-29")) == date(2026, 10, 29)
    # A UTC-midnight timestamp for the same day also resolves to that day
    assert derive_trade_date(_epoch("2026-10-29", 0, 0)) == date(2026, 10, 29)
    # Friday evening still belongs to Friday
    assert derive_trade_date(_epoch("2026-10-30", 16, 0)) == date(2026, 10, 30)
    # Milliseconds and junk
    assert derive_trade_date(_epoch("2026-10-29") * 1000) == date(2026, 10, 29)
    assert derive_trade_date(0) is None
    assert derive_trade_date(None) is None


def test_parse_eod_series_payload_is_newest_first_and_sorted_by_date():
    payload = json.loads((FIXTURES / "timeseries_eod" / "OGDC.json").read_text(encoding="utf-8"))
    bars = parse_eod_series(payload, "OGDC")

    assert [bar["trade_date"] for bar in bars] == [
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
        date(2026, 10, 29),
    ]
    assert bars[-1]["close"] == pytest.approx(218.75)
    assert bars[-1]["open"] == pytest.approx(216.00)
    assert bars[-1]["volume"] == pytest.approx(4_512_300)
    # the EOD route publishes no high/low — they must stay NULL, never invented
    assert bars[-1]["high"] is None and bars[-1]["low"] is None


def test_parse_eod_series_rejects_error_status():
    with pytest.raises(ParseError):
        parse_eod_series({"status": 0, "message": "invalid symbol", "data": []}, "NOPE")


# ---------------------------------------------------------------------- store
def test_schema_creates_every_table(db: PsxDatabase):
    assert set(db.table_counts()) == set(TABLES)
    assert db.schema_version == 1


def test_symbol_and_bar_upserts_are_idempotent(db: PsxDatabase):
    rows = [
        {"symbol": "OGDC", "name": "Oil & Gas Development Company", "sector": "Oil & Gas"},
    ]
    db.upsert_symbols(rows, "dps.psx.com.pk")
    db.upsert_symbols(rows, "dps.psx.com.pk")
    assert db.table_counts()["symbols"] == 1

    bars = [{"trade_date": date(2026, 10, 29), "close": 218.75, "volume": 4512300}]
    db.upsert_bars("OGDC", bars, "dps.psx.com.pk/timeseries/eod")
    db.upsert_bars("OGDC", bars, "dps.psx.com.pk/timeseries/eod")
    assert db.table_counts()["eod_bars"] == 1


def test_a_richer_row_is_never_overwritten_by_a_poorer_one(db: PsxDatabase):
    db.upsert_bars(
        "OGDC",
        [{"trade_date": date(2026, 10, 29), "open": 216.0, "high": 219.9, "low": 214.1, "close": 218.75,
          "volume": 4512300}],
        "dps.psx.com.pk/market-watch",
    )
    # the EOD route carries no high/low: re-ingesting must not wipe them
    db.upsert_bars(
        "OGDC",
        [{"trade_date": date(2026, 10, 29), "open": 216.0, "high": None, "low": None, "close": 218.75,
          "volume": 4512300}],
        "dps.psx.com.pk/timeseries/eod",
    )
    bar = price_history(db, symbol="OGDC")[0]
    assert bar["high"] == pytest.approx(219.9)
    assert bar["low"] == pytest.approx(214.1)


def test_memberships_are_snapshotted_as_of(db: PsxDatabase):
    db.upsert_memberships("KSE100", ["OGDC", "PPL"], date(2026, 6, 30), "dps.psx.com.pk")
    db.upsert_memberships("KSE100", ["OGDC", "MEBL"], date(2026, 9, 30), "dps.psx.com.pk")

    latest = constituents(db, index_code="KSE100")
    assert [row["symbol"] for row in latest] == ["MEBL", "OGDC"]
    older = constituents(db, index_code="KSE100", as_of="2026-06-30")
    assert [row["symbol"] for row in older] == ["OGDC", "PPL"]


def test_log_raw_records_provenance(db: PsxDatabase):
    run_id = db.start_run("live", ["KSE100"])
    db.log_raw(run_id, "market-watch", "https://dps.psx.com.pk/market-watch", 200, "<html/>", "abc123")
    row = db.conn.execute("SELECT * FROM raw_payloads").fetchone()
    assert row["sha256"] == "abc123"
    assert row["bytes"] == len("<html/>")


# -------------------------------------------------------------------- capture
def test_capture_roundtrip_writes_manifest(tmp_path: Path):
    client = CaptureClient(build_capture(tmp_path / "in"))
    responses = [client.market_watch(), client.company("OGDC")]
    manifest = save_capture(responses, tmp_path / "out")

    assert manifest["source"] == "https://dps.psx.com.pk"
    assert (tmp_path / "out" / "market-watch.html").is_file()
    assert (tmp_path / "out" / "company" / "OGDC.html").is_file()
    assert len(json.loads((tmp_path / "out" / "manifest.json").read_text())["files"]) == 2


def test_ingest_from_capture_builds_a_queryable_database(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest_from_capture(capture, database, indices=["KSE100", "KMI30"], log=lambda _m: None)

    assert report.mode == "capture"
    assert report.errors == []
    assert report.constituents["KSE100"] == ["FFC", "OGDC", "PPL"]
    assert report.constituents["KMI30"] == ["FFC", "MEBL", "PPL"]

    kse100 = [row["symbol"] for row in constituents(database, index_code="KSE100")]
    assert kse100 == ["FFC", "OGDC", "PPL"]
    # sector comes from /symbols, joined at query time
    assert {row["sector"] for row in constituents(database, index_code="KMI30")} == {
        "Fertilizer",
        "Commercial Banks",
        "Oil & Gas Exploration Companies",
    }

    # 6 series x bars, deduplicated onto trading dates
    bars = price_history(database, symbol="OGDC")
    assert [bar["trade_date"] for bar in bars] == ["2026-10-29", "2026-10-28", "2026-10-27", "2026-10-26"]
    assert bars[0]["close"] == pytest.approx(218.75)
    assert bars[0]["high"] == pytest.approx(219.90)  # today's high came from market-watch

    assert price_history(database, symbol="KSE100", table="index_bars")[0]["close"] == pytest.approx(118420.55)

    levels = {row["code"]: row for row in index_levels(database)}
    assert levels["KSE100"]["level"] == pytest.approx(118420.55)
    assert levels["KMI30"]["level"] == pytest.approx(178905.40)

    quotes = {row["symbol"]: row for row in latest_quotes(database, index_code="KMI30")}
    assert set(quotes) == {"FFC", "MEBL", "PPL"}
    assert quotes["MEBL"]["close"] == pytest.approx(92.31)
    assert quotes["MEBL"]["change_pct"] == pytest.approx((92.31 - 92.55) / 92.55 * 100, rel=1e-6)

    summary = market_summary(database)
    assert summary["trade_date"] == "2026-10-29"
    assert summary["symbols"] == 4
    # OGDC/PPL/FFC closed up on the 29th, MEBL down: breadth is computed from the bars
    assert (summary["advances"], summary["declines"]) == (3, 1)

    stats = database_stats(database)
    assert stats["last_run"]["mode"] == "capture"
    assert stats["tables"]["eod_bars"] > 0
    assert stats["coverage"]["eod_bars"]["entities"] == 4

    fundamentals = run_fundamentals(database, symbol="OGDC")
    assert fundamentals["profile"]["sector"] == "Oil & Gas Exploration Companies"
    assert fundamentals["snapshot"]["pe"] == pytest.approx(6.85)
    assert fundamentals["financial_years"][0]["fiscal_year"] == 2025
    assert fundamentals["last_close"]["close"] == pytest.approx(218.75)
    assert fundamentals["indices"] == ["KSE100"]
    database.close()


def test_ingest_is_idempotent_across_runs(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    first = ingest_from_capture(capture, database, log=lambda _m: None)
    counts_first = database.table_counts()
    second = ingest_from_capture(capture, database, log=lambda _m: None)
    counts_second = database.table_counts()

    for table in ("symbols", "eod_bars", "index_bars", "index_memberships"):
        assert counts_first[table] == counts_second[table], table
    # provenance accumulates: two runs, one snapshot per symbol (same as_of)
    assert counts_second["ingest_runs"] == 2
    assert first.run_id != second.run_id
    assert counts_second["company_snapshots"] == counts_first["company_snapshots"]
    database.close()


def test_concurrent_workers_share_one_connection_safely(capture: Path, tmp_path: Path):
    """The ingester writes from worker threads onto a single SQLite connection."""
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    client = CaptureClient(capture)
    report = ingest(client, database, indices=["KSE100", "KMI30"], workers=4, log=lambda _m: None)
    assert report.errors == []
    assert database.table_counts()["eod_bars"] >= 12
    database.close()


def test_one_broken_symbol_does_not_abort_the_run(capture: Path, tmp_path: Path):
    # PPL's series is missing from the capture: the run must still store the rest
    (capture / "timeseries_eod" / "PPL.json").unlink()
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest_from_capture(capture, database, log=lambda _m: None)

    assert any("PPL" in error for error in report.errors)
    assert price_history(database, symbol="OGDC")
    assert [row["symbol"] for row in constituents(database, index_code="KSE100")] == [
        "FFC", "OGDC", "PPL",
    ]  # membership survives even though the price series is missing
    database.close()


def test_capture_client_reports_missing_files(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    client = CaptureClient(empty)
    with pytest.raises(Exception):
        client.market_watch()


# ------------------------------------------------------------------------ CLI
def test_cli_init_stats_and_constituents(capture: Path, tmp_path: Path, capsys):
    db_path = tmp_path / "cli.db"
    assert cli_main(["init", "--db", str(db_path)]) == 0
    assert cli_main(["stats", "--db", str(db_path)]) == 0
    assert "schema v1" in capsys.readouterr().out

    assert cli_main(["from-capture", str(capture), "--db", str(db_path), "--indices", "KSE100,KMI30"]) == 0
    capsys.readouterr()

    assert cli_main(["constituents", "KMI30", "--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "KMI30: 3 constituents" in out and "MEBL" in out

    assert cli_main(["quotes", "--db", str(db_path), "--index", "KSE100", "--limit", "2"]) == 0
    assert "OGDC" in capsys.readouterr().out

    assert cli_main(["history", "OGDC", "--db", str(db_path), "--limit", "1"]) == 0
    assert "2026-10-29" in capsys.readouterr().out

    stats_db = tmp_path / "cli.db"
    assert cli_main(["stats", "--db", str(stats_db), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tables"]["symbols"] == 5


def test_cli_export_writes_csv(capture: Path, tmp_path: Path, capsys):
    db_path = tmp_path / "cli.db"
    cli_main(["init", "--db", str(db_path)])
    cli_main(["from-capture", str(capture), "--db", str(db_path)])
    capsys.readouterr()

    out = tmp_path / "eod.csv"
    assert cli_main(["export", "--db", str(db_path), "--table", "eod_bars", "--out", str(out)]) == 0
    lines = out.read_text().splitlines()
    assert lines[0].startswith("symbol,trade_date")
    assert len(lines) > 5


def test_cli_rejects_an_unknown_table(tmp_path: Path):
    assert cli_main(["export", "--db", str(tmp_path / "x.db"), "--table", "nope"]) == 1


# ------------------------------------------------------------------- client
def test_client_headers_look_like_a_browser():
    client = PsxPortalClient(min_interval=0, retries=1)
    try:
        assert "Mozilla" in client.headers["User-Agent"]
        assert client.headers["Referer"].startswith("https://dps.psx.com.pk")
    finally:
        client.close()


def test_month_windows_covers_a_range():
    from strata_research.psxdb.client import month_windows

    windows = list(month_windows(date(2025, 11, 15), date(2026, 2, 3)))
    assert windows == [(11, 2025), (12, 2025), (1, 2026), (2, 2026)]


# ------------------------------------------------------------------ metadata
def test_history_window_default_is_about_thirteen_months():
    """A sanity guard: the CLI default must be wide enough for a 1-year comparison."""
    from strata_research.psxdb.ingest import ingest as ingest_fn

    default_days = ingest_fn.__kwdefaults__["history_days"]
    assert 300 <= default_days <= 500
    assert date.today() - timedelta(days=default_days) < date.today()


def test_symbols_query_filters_by_sector(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    ingest_from_capture(capture, database, log=lambda _m: None)
    banks = symbols(database, sector="bank")
    assert [row["symbol"] for row in banks] == ["MEBL"]
    assert len(symbols(database)) == 5
    database.close()
