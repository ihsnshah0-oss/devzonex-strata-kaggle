"""Tests for the PSX Data Portal mirror (``strata_research.psxdb``).

Everything runs offline against fixtures modelled on the portal's live markup
(``/screener``, ``/indices``, ``/indices/{CODE}``, ``/company/{SYMBOL}``,
``/historical``): the parsers must survive that markup, the store must be
idempotent, and a capture replay must produce a queryable database.
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
    magnitude_to_float,
    parse_company_financials,
    parse_company_meta,
    parse_company_stats,
    parse_index_constituents,
    parse_indices,
    parse_latest_trade_date,
    parse_screener,
    to_float,
)
from strata_research.psxdb.schema import TABLES

FIXTURES = Path(__file__).parent / "fixtures" / "psx"


def _epoch(day: str, hour: int = 15, minute: int = 30) -> int:
    """PSX emits Pakistan wall-clock seconds, so a 15:30 close is stored as 15:30 UTC."""
    naive = datetime.strptime(f"{day} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    return int(naive.replace(tzinfo=timezone.utc).timestamp())


def build_capture(directory: Path) -> Path:
    """Assemble a capture directory from the fixtures (the air-gapped replay input)."""
    directory.mkdir(parents=True, exist_ok=True)
    for source, target in (
        (FIXTURES / "screener.html", directory / "screener.html"),
        (FIXTURES / "indices.html", directory / "indices.html"),
        (FIXTURES / "historical.html", directory / "historical.html"),
    ):
        shutil.copy(source, target)
    for index_code in ("KSE100", "KMI30"):
        target = directory / "indices" / f"{index_code}.html"
        target.parent.mkdir(exist_ok=True)
        shutil.copy(FIXTURES / "indices" / f"{index_code}.html", target)
    company_dir = directory / "company"
    company_dir.mkdir(exist_ok=True)
    for symbol in ("OGDC", "PPL", "MEBL", "FFC"):
        shutil.copy(FIXTURES / "company" / "OGDC.html", company_dir / f"{symbol}.html")
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


# --------------------------------------------------------------- screener
def test_parse_screener_reads_every_published_column():
    rows = parse_screener((FIXTURES / "screener.html").read_text(encoding="utf-8"))
    by_symbol = {row.symbol: row for row in rows}
    assert list(by_symbol) == ["OGDC", "PPL", "MEBL", "FFC", "NBPGETF"]

    ogdc = by_symbol["OGDC"]
    assert ogdc.name == "Oil & Gas Development Company Limited"
    assert ogdc.sector_code == "0813"
    assert ogdc.listed_in == {"KSE100"}
    assert ogdc.market_cap == pytest.approx(940_123_456_789)   # data-order, not "940.1B"
    assert ogdc.price == pytest.approx(218.75)
    assert ogdc.change_pct == pytest.approx(1.5553)
    assert ogdc.year_change_pct == pytest.approx(24.1)
    assert ogdc.pe == pytest.approx(6.85)
    assert ogdc.dividend_yield == pytest.approx(5.26)
    assert ogdc.free_float == pytest.approx(129_000_000)
    assert ogdc.avg_volume_30d == pytest.approx(3_812_044.5)

    # membership arrives in three different spellings on the portal
    assert by_symbol["PPL"].listed_in == {"KSE100", "KMI30"}
    assert by_symbol["MEBL"].listed_in == {"KMI30"}
    assert by_symbol["FFC"].listed_in == {"KSE100", "KMI30"}

    # a missing P/E is published as an empty cell: None, never 0
    assert by_symbol["NBPGETF"].pe is None


def test_parse_screener_rejects_a_page_without_a_table():
    with pytest.raises(ParseError):
        parse_screener("<html><body><p>maintenance</p></body></html>")


# ---------------------------------------------------- index constituents
def test_parse_index_constituents_reads_quotes_weights_and_scale():
    rows = parse_index_constituents(
        (FIXTURES / "indices" / "KSE100.html").read_text(encoding="utf-8"), "KSE100"
    )
    by_symbol = {row.symbol: row for row in rows}
    assert set(by_symbol) == {"OGDC", "PPL", "FFC"}

    ogdc = by_symbol["OGDC"]
    assert ogdc.name == "Oil & Gas Development Company Limited"
    assert ogdc.ldcp == pytest.approx(215.40)
    assert ogdc.close == pytest.approx(218.75)
    assert ogdc.change == pytest.approx(3.35)
    assert ogdc.change_pct == pytest.approx(1.5553)   # not confused with CHANGE
    assert ogdc.weight_pct == pytest.approx(0.42)
    assert ogdc.index_points == pytest.approx(1.5924)
    assert ogdc.volume == pytest.approx(4_512_300)
    # FREEFLOAT (M) / MARKET CAP (M) columns publish absolute values in data-order
    assert ogdc.free_float == pytest.approx(129_000_000)
    assert ogdc.market_cap == pytest.approx(940_123_456_789)


def test_parse_index_constituents_reports_a_missing_table():
    with pytest.raises(ParseError):
        parse_index_constituents("<html><body>no table here</body></html>", "KMI30")


def test_parse_indices_reads_levels_and_ranges():
    rows = parse_indices((FIXTURES / "indices.html").read_text(encoding="utf-8"))
    by_code = {row.code: row for row in rows}
    assert by_code["KSE100"].level == pytest.approx(167193.43)
    assert by_code["KSE100"].high == pytest.approx(167483.48)
    assert by_code["KSE100"].low == pytest.approx(165907.29)
    assert by_code["KSE100"].change == pytest.approx(1456.68)
    assert by_code["KMI30"].level == pytest.approx(265804.12)
    assert by_code["KSE30"].change == pytest.approx(-88.10)
    # an index whose name carries a timestamp still resolves to its code
    assert by_code["HBLTTI"].level == pytest.approx(999.55)


# ------------------------------------------------------------ company page
def test_parse_company_stats_handles_every_block():
    stats = parse_company_stats((FIXTURES / "company" / "OGDC.html").read_text(encoding="utf-8"))
    assert stats["open"] == pytest.approx(216.00)
    assert stats["volume"] == pytest.approx(4_512_300)
    assert stats["prev_close"] == pytest.approx(215.40)
    assert stats["market_cap"] == pytest.approx(940_123_456_789)
    assert stats["shares"] == pytest.approx(4_300_000_000)
    assert stats["free_float"] == pytest.approx(129_000_000)
    assert stats["free_float_pct"] == pytest.approx(3.00)   # not clobbered by free_float
    assert stats["pe"] == pytest.approx(6.85)
    assert stats["pb"] == pytest.approx(0.92)
    assert stats["year_change_pct"] == pytest.approx(24.10)
    assert stats["ytd_change_pct"] == pytest.approx(11.60)
    # "low — high" blocks yield both bounds
    assert (stats["low_52w"], stats["high_52w"]) == (pytest.approx(148.20), pytest.approx(241.50))
    assert (stats["day_low"], stats["day_high"]) == (pytest.approx(214.10), pytest.approx(219.90))
    assert (stats["circuit_low"], stats["circuit_high"]) == (pytest.approx(193.86), pytest.approx(236.94))


def test_parse_company_financials_normalises_both_orientations():
    entries = parse_company_financials((FIXTURES / "company" / "OGDC.html").read_text(encoding="utf-8"))
    keyed = {(entry["period"], entry["metric"]): entry["value"] for entry in entries}

    # orientation A: fiscal years across the top
    assert keyed[("2026", "revenue")] == pytest.approx(1_412_000_000)
    assert keyed[("2026", "net_income")] == pytest.approx(338_900_000)
    assert keyed[("2026", "eps")] == pytest.approx(78.81)
    assert keyed[("2025", "eps")] == pytest.approx(72.37)

    # orientation B: quarters down the side
    assert keyed[("Q3 2026", "revenue")] == pytest.approx(372_000_000)
    assert keyed[("Q3 2026", "net_income")] == pytest.approx(91_500_000)
    assert keyed[("Q2 2026", "eps")] == pytest.approx(20.56)

    # the published label is kept next to the canonical metric
    label = next(entry["label"] for entry in entries if entry["metric"] == "net_income")
    assert label == "Profit after Taxation"


def test_parse_company_financials_returns_nothing_for_a_page_without_tables():
    assert parse_company_financials("<html><body>no financials</body></html>") == []


def test_parse_company_meta_reads_name_and_sector():
    meta = parse_company_meta((FIXTURES / "company" / "OGDC.html").read_text(encoding="utf-8"))
    assert meta["name"] == "Oil & Gas Development Company Limited"
    assert meta["sector"] == "Oil & Gas Exploration Companies"


# ------------------------------------------------------------------ numbers
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


@pytest.mark.parametrize(
    "raw,expected",
    [("399.5M", 399_500_000), ("7.0K", 7_000), ("2.1B", 2_100_000_000), ("96,067", 96_067)],
)
def test_magnitude_to_float_expands_suffixes(raw, expected):
    assert magnitude_to_float(raw) == pytest.approx(expected)


# ------------------------------------------------------------------ dates
def test_derive_trade_date_maps_karachi_wall_clock_to_the_trading_day():
    assert derive_trade_date(_epoch("2026-10-29")) == date(2026, 10, 29)
    assert derive_trade_date(_epoch("2026-10-29", 0, 0)) == date(2026, 10, 29)
    assert derive_trade_date(_epoch("2026-10-30", 16, 0)) == date(2026, 10, 30)
    assert derive_trade_date(_epoch("2026-10-29") * 1000) == date(2026, 10, 29)  # milliseconds
    assert derive_trade_date(0) is None
    assert derive_trade_date(None) is None


def test_parse_latest_trade_date_prefers_the_portal_stamp():
    parsed, source = parse_latest_trade_date(
        (FIXTURES / "historical.html").read_text(encoding="utf-8")
    )
    assert parsed == date(2026, 10, 29)
    assert source == "historical-data-latest"

    # an index table that stamps its own timestamp is the fallback
    parsed, source = parse_latest_trade_date("<td>HBLTTI (28-10-2026 18:30:00)</td>")
    assert parsed == date(2026, 10, 28)
    assert source == "indices-timestamp"

    assert parse_latest_trade_date("<html>nothing</html>") == (None, "unavailable")


# -------------------------------------------------------------------- store
def test_schema_creates_every_table(db: PsxDatabase):
    assert set(db.table_counts()) == set(TABLES)
    assert db.schema_version == 2


def test_symbol_and_bar_upserts_are_idempotent(db: PsxDatabase):
    rows = [{"symbol": "OGDC", "name": "Oil & Gas Development Company", "sector_code": "0813"}]
    db.upsert_symbols(rows, "dps.psx.com.pk")
    db.upsert_symbols(rows, "dps.psx.com.pk")
    assert db.table_counts()["symbols"] == 1

    bars = [{"trade_date": date(2026, 10, 29), "close": 218.75, "volume": 4512300}]
    db.upsert_bars("OGDC", bars, "dps.psx.com.pk/indices/KSE100")
    db.upsert_bars("OGDC", bars, "dps.psx.com.pk/indices/KSE100")
    assert db.table_counts()["eod_bars"] == 1


def test_a_richer_row_is_never_overwritten_by_a_poorer_one(db: PsxDatabase):
    db.upsert_bars(
        "OGDC",
        [{"trade_date": date(2026, 10, 29), "open": 216.0, "high": 219.9, "low": 214.1,
          "close": 218.75, "prev_close": 215.4, "volume": 4512300}],
        "dps.psx.com.pk/company/OGDC",
    )
    db.upsert_bars(
        "OGDC",
        [{"trade_date": date(2026, 10, 29), "close": 218.75, "prev_close": 215.4, "volume": 4512300}],
        "dps.psx.com.pk/indices/KSE100",
    )
    bar = price_history(db, symbol="OGDC")[0]
    assert bar["high"] == pytest.approx(219.9)
    assert bar["low"] == pytest.approx(214.1)
    assert bar["open"] == pytest.approx(216.0)


def test_memberships_are_snapshotted_as_of(db: PsxDatabase):
    db.upsert_memberships("KSE100", [{"symbol": "OGDC", "weight_pct": 0.4}], date(2026, 6, 30), "s")
    db.upsert_memberships(
        "KSE100", [{"symbol": "OGDC", "weight_pct": 0.45}, {"symbol": "MEBL", "weight_pct": 4.4}],
        date(2026, 9, 30), "s",
    )
    latest = constituents(db, index_code="KSE100")
    assert [row["symbol"] for row in latest] == ["MEBL", "OGDC"]   # by weight
    older = constituents(db, index_code="KSE100", as_of="2026-06-30")
    assert [row["symbol"] for row in older] == ["OGDC"]


def test_log_raw_records_provenance(db: PsxDatabase):
    run_id = db.start_run("live", ["KSE100"])
    db.log_raw(run_id, "screener", "https://dps.psx.com.pk/screener", 200, "<html/>", "abc123")
    row = db.conn.execute("SELECT * FROM raw_payloads").fetchone()
    assert row["sha256"] == "abc123"
    assert row["bytes"] == len("<html/>")


# ------------------------------------------------------------------ capture
def test_capture_roundtrip_writes_manifest(tmp_path: Path):
    client = CaptureClient(build_capture(tmp_path / "in"))
    responses = [client.screener(), client.company("OGDC"), client.index_constituents("KSE100")]
    manifest = save_capture(responses, tmp_path / "out")

    assert manifest["source"] == "https://dps.psx.com.pk"
    assert (tmp_path / "out" / "screener.html").is_file()
    assert (tmp_path / "out" / "company" / "OGDC.html").is_file()
    assert (tmp_path / "out" / "indices" / "KSE100.html").is_file()
    assert len(json.loads((tmp_path / "out" / "manifest.json").read_text())["files"]) == 3


def test_ingest_from_capture_builds_a_queryable_database(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest_from_capture(capture, database, indices=["KSE100", "KMI30"], log=lambda _m: None)

    assert report.mode == "capture"
    assert report.errors == []
    assert report.trade_date == "2026-10-29"
    assert report.notes["trade_date_source"] == "historical-data-latest"
    assert report.constituents["KSE100"] == ["FFC", "OGDC", "PPL"]
    assert report.constituents["KMI30"] == ["FFC", "MEBL", "PPL"]

    # ---- constituents (authoritative, from /indices/{CODE})
    kse100 = {row["symbol"]: row for row in constituents(database, index_code="KSE100")}
    assert set(kse100) == {"FFC", "OGDC", "PPL"}
    assert kse100["OGDC"]["weight_pct"] == pytest.approx(0.42)
    assert kse100["OGDC"]["name"] == "Oil & Gas Development Company Limited"

    # ---- the whole market's symbols and sector codes come from /screener
    ogdc_symbol = next(row for row in symbols(database) if row["symbol"] == "OGDC")
    assert ogdc_symbol["sector_code"] == "0813"
    assert ogdc_symbol["listed_in"] == "KSE100"
    assert len(symbols(database)) == 5          # including the ETF outside both indices

    # ---- index levels + bars
    levels = {row["code"]: row for row in index_levels(database)}
    assert levels["KSE100"]["level"] == pytest.approx(167193.43)
    assert levels["KMI30"]["level"] == pytest.approx(265804.12)
    kse_bar = price_history(database, symbol="KSE100", table="index_bars")[0]
    assert kse_bar["close"] == pytest.approx(167193.43)
    assert kse_bar["prev_close"] == pytest.approx(167193.43 - 1456.68)
    assert kse_bar["high"] == pytest.approx(167483.48)

    # ---- today's per-symbol bar: close + previous close + volume
    ogdc_bar = price_history(database, symbol="OGDC")[0]
    assert ogdc_bar["trade_date"] == "2026-10-29"
    assert ogdc_bar["close"] == pytest.approx(218.75)
    assert ogdc_bar["prev_close"] == pytest.approx(215.40)
    assert ogdc_bar["volume"] == pytest.approx(4_512_300)

    # ---- company pages add the intraday range the constituent table lacks
    quotes = {row["symbol"]: row for row in latest_quotes(database, index_code="KMI30")}
    assert set(quotes) == {"FFC", "MEBL", "PPL"}
    assert quotes["MEBL"]["close"] == pytest.approx(92.31)
    assert quotes["MEBL"]["change_pct"] == pytest.approx((92.31 - 92.55) / 92.55 * 100, rel=1e-6)

    # KSE100 ∪ KMI30 = OGDC, PPL, FFC, MEBL
    summary = market_summary(database)
    assert summary["trade_date"] == "2026-10-29"
    assert summary["symbols"] == 4
    assert (summary["advances"], summary["declines"]) == (3, 1)   # all up except MEBL

    stats = database_stats(database)
    assert stats["last_run"]["mode"] == "capture"
    assert stats["memberships"] == {"KMI30": 3, "KSE100": 3}
    assert stats["coverage"]["eod_bars"]["entities"] == 4

    # ---- one symbol, every source joined up
    fundamentals = run_fundamentals(database, symbol="OGDC")
    assert fundamentals["profile"]["name"] == "Oil & Gas Development Company Limited"
    assert fundamentals["snapshot"]["pe"] == pytest.approx(6.85)
    assert fundamentals["snapshot"]["low_52w"] == pytest.approx(148.20)
    assert fundamentals["snapshot"]["dividend_yield"] == pytest.approx(5.26)
    annual = next(p for p in fundamentals["periods"] if p["period"] == "2026")
    assert annual["metrics"]["revenue"] == pytest.approx(1_412_000_000)
    assert annual["metrics"]["net_income"] == pytest.approx(338_900_000)
    quarterly = next(p for p in fundamentals["periods"] if p["period"] == "Q3 2026")
    assert quarterly["metrics"]["eps"] == pytest.approx(21.28)
    assert fundamentals["last_close"]["close"] == pytest.approx(218.75)
    assert fundamentals["indices"] == ["KSE100"]
    database.close()


def test_ingest_is_idempotent_across_runs(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    first = ingest_from_capture(capture, database, log=lambda _m: None)
    counts_first = database.table_counts()
    second = ingest_from_capture(capture, database, log=lambda _m: None)
    counts_second = database.table_counts()

    for table in ("symbols", "eod_bars", "index_bars", "index_memberships", "company_financials"):
        assert counts_first[table] == counts_second[table], table
    assert counts_second["ingest_runs"] == 2      # provenance accumulates
    assert first.run_id != second.run_id
    assert counts_second["company_snapshots"] == counts_first["company_snapshots"]
    database.close()


def test_concurrent_workers_share_one_connection_safely(capture: Path, tmp_path: Path):
    """The ingester writes from worker threads onto a single SQLite connection."""
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest(CaptureClient(capture), database, indices=["KSE100", "KMI30"],
                    workers=4, log=lambda _m: None)
    assert report.errors == []
    assert database.table_counts()["eod_bars"] >= 3
    assert database.table_counts()["company_financials"] > 0
    database.close()


def test_one_broken_symbol_does_not_abort_the_run(capture: Path, tmp_path: Path):
    (capture / "company" / "PPL.html").unlink()
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest_from_capture(capture, database, log=lambda _m: None)

    assert any("PPL" in error for error in report.errors)
    assert price_history(database, symbol="OGDC")
    # membership survives even though the company page is missing
    assert [row["symbol"] for row in constituents(database, index_code="KSE100")] == [
        "OGDC", "PPL", "FFC",   # ordered by index weight
    ]
    database.close()


def test_a_missing_constituent_page_is_reported_not_fatal(capture: Path, tmp_path: Path):
    (capture / "indices" / "KMI30.html").unlink()
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    report = ingest_from_capture(capture, database, log=lambda _m: None)

    assert any("KMI30" in error for error in report.errors)
    assert report.constituents["KSE100"] == ["FFC", "OGDC", "PPL"]
    assert report.constituents["KMI30"] == []
    assert price_history(database, symbol="OGDC")     # the rest of the run completed
    database.close()


def test_capture_client_reports_missing_files(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Exception):
        CaptureClient(empty).screener()


# ------------------------------------------------------------------------ CLI
def test_cli_init_stats_and_constituents(capture: Path, tmp_path: Path, capsys):
    db_path = tmp_path / "cli.db"
    assert cli_main(["init", "--db", str(db_path)]) == 0
    assert cli_main(["stats", "--db", str(db_path)]) == 0
    assert "schema v2" in capsys.readouterr().out

    assert cli_main(["from-capture", str(capture), "--db", str(db_path),
                     "--indices", "KSE100,KMI30"]) == 0
    capsys.readouterr()

    assert cli_main(["constituents", "KMI30", "--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "KMI30: 3 constituents" in out and "MEBL" in out

    assert cli_main(["quotes", "--db", str(db_path), "--index", "KSE100", "--limit", "2"]) == 0
    assert "OGDC" in capsys.readouterr().out

    assert cli_main(["history", "OGDC", "--db", str(db_path), "--limit", "1"]) == 0
    assert "2026-10-29" in capsys.readouterr().out

    assert cli_main(["stats", "--db", str(db_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tables"]["symbols"] == 5
    assert payload["memberships"] == {"KMI30": 3, "KSE100": 3}


def test_cli_export_writes_csv(capture: Path, tmp_path: Path, capsys):
    db_path = tmp_path / "cli.db"
    cli_main(["init", "--db", str(db_path)])
    cli_main(["from-capture", str(capture), "--db", str(db_path)])
    capsys.readouterr()

    out = tmp_path / "eod.csv"
    assert cli_main(["export", "--db", str(db_path), "--table", "eod_bars", "--out", str(out)]) == 0
    lines = out.read_text().splitlines()
    assert lines[0].startswith("symbol,trade_date")
    assert len(lines) >= 4


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


def test_client_recovers_when_the_portal_drops_a_keep_alive_socket(monkeypatch):
    """The portal closes idle connections; the retry must dial a fresh one."""
    import httpx as httpx_module

    attempts = {"count": 0}

    def flaky_get(self, url, *args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx_module.RemoteProtocolError(
                "Server disconnected without sending a response."
            )
        return httpx_module.Response(
            200, text="<html><table></table></html>", request=httpx_module.Request("GET", url)
        )

    monkeypatch.setattr(httpx_module.Client, "get", flaky_get)
    client = PsxPortalClient(min_interval=0, retries=3)
    try:
        response = client.screener()
    finally:
        client.close()
    assert response.status == 200
    assert attempts["count"] == 2          # one failure, one retry
    assert response.body.startswith("<html>")


def test_client_exposes_only_routes_the_portal_still_serves():
    """The withdrawn JSON routes must not be presented as an API."""
    for name in ("symbols", "market_watch", "eod", "intraday", "historical_month"):
        assert not hasattr(PsxPortalClient, name), name
    for name in ("screener", "indices_page", "index_constituents", "company", "historical_page"):
        assert hasattr(PsxPortalClient, name), name


def test_symbols_query_filters_by_sector_code(capture: Path, tmp_path: Path):
    database = PsxDatabase(tmp_path / "psx.db").initialise()
    ingest_from_capture(capture, database, log=lambda _m: None)
    banks = symbols(database, sector="0812")
    assert [row["symbol"] for row in banks] == ["MEBL"]
    assert len(symbols(database)) == 5
    database.close()


def test_trade_date_falls_back_to_the_last_weekday(tmp_path: Path):
    """If the portal is mute about its trading date, weekend days are skipped."""
    from strata_research.psxdb.ingest import _fallback_trade_date

    assert _fallback_trade_date(date(2026, 10, 31)) == date(2026, 10, 30)  # Sat -> Fri
    assert _fallback_trade_date(date(2026, 11, 1)) == date(2026, 10, 30)   # Sun -> Fri
    assert _fallback_trade_date(date(2026, 10, 29)) == date(2026, 10, 29)
    assert date.today() - timedelta(days=1) >= date(2000, 1, 1)
