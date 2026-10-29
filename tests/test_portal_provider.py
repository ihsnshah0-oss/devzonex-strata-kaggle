"""The portal-backed fundamentals provider.

``analyze OGDC`` used to answer "not in the offline demo universe" because the desk
only knew how to read hand-keyed statement files. These tests pin the replacement
path: real PSX companies shaped from the portal mirror, with the portal's thousands
of rupees converted to millions and EPS left in rupees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strata_research.config import Settings
from strata_research.data import DataProviderError, fetch_fundamentals
from strata_research.data.portal_provider import PortalStatementsProvider
from strata_research.psxdb import PsxDatabase, ingest_from_capture
from strata_research.watchlist import WATCHLIST, load_watchlist

from test_psxdb import build_capture


@pytest.fixture(scope="module")
def mirror(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("portal-mirror")
    capture = build_capture(directory)
    database = PsxDatabase(directory / "psx.db").initialise()
    ingest_from_capture(capture, database, log=lambda _message: None)
    database.close()
    return directory / "psx.db"


def _settings(db: Path) -> Settings:
    return Settings(llm_kind="template", data_provider="auto", psx_db=db)


# ----------------------------------------------------------------------
# the provider itself
# ----------------------------------------------------------------------
def test_portal_provider_shapes_published_financials(mirror: Path):
    company = PortalStatementsProvider(mirror).fetch("PSX:OGDC")

    assert company.profile.ticker == "OGDC"
    assert company.profile.sector and "oil" in company.profile.sector.lower()
    assert company.profile.price == pytest.approx(218.75)
    assert company.profile.data_source == "psx-portal"
    assert company.profile.data_quality == "reported"
    assert company.profile.shares_outstanding == pytest.approx(4_300.0)  # millions

    latest = company.latest
    assert latest.fiscal_year == 2026
    # the portal publishes thousands of PKR -> millions in the desk
    assert latest.revenue == pytest.approx(1_412_000_000 / 1_000)
    assert latest.net_income == pytest.approx(338_900_000 / 1_000)
    # EPS is rupees and must never be scaled
    assert latest.eps == pytest.approx(78.81)
    assert len(company.fiscal_years) == 3


def test_portal_provider_says_what_is_missing(mirror: Path):
    company = PortalStatementsProvider(mirror).fetch("OGDC")
    notes = " ".join(company.profile.notes)
    assert "PSX Data Portal" in notes
    assert "thousands" in notes
    assert "n/a rather than estimated" in notes
    # quarterly rows on the portal are surfaced, but they never become fiscal years
    assert all(year.fiscal_year for year in company.fiscal_years)


def test_portal_provider_rejects_an_unlisted_symbol(mirror: Path):
    with pytest.raises(DataProviderError):
        PortalStatementsProvider(mirror).fetch("NOPE")


def test_portal_provider_without_a_mirror_is_unavailable_but_harmless(tmp_path: Path):
    provider = PortalStatementsProvider(tmp_path / "missing.db")
    assert provider.available() is False
    assert provider.universe() == []


def test_auto_chain_uses_the_portal_before_the_demo_universe(mirror: Path):
    company = fetch_fundamentals(_settings(mirror), "FFC")
    assert company.profile.data_source == "psx-portal"
    assert company.latest.eps is not None


def test_the_default_watchlist_is_the_one_the_user_asked_for():
    assert len(WATCHLIST) == 25
    assert WATCHLIST[0] == "ENGROH" and WATCHLIST[-1] == "SYS"
    assert {"FFC", "EFERT", "HUBC", "MARI", "PSO", "SYS"} <= set(WATCHLIST)


def test_a_watchlist_symbol_outside_the_mirror_fails_loudly(mirror: Path):
    settings = _settings(mirror)
    assert fetch_fundamentals(settings, "OGDC").profile.ticker == "OGDC"
    assert fetch_fundamentals(settings, "MEBL").latest.eps == pytest.approx(25.10)
    # ENGROH is on the watchlist but not in this small fixture capture
    with pytest.raises(DataProviderError) as error:
        fetch_fundamentals(settings, "ENGROH")
    assert "ENGROH" in str(error.value)


def test_watchlist_override_from_the_environment(monkeypatch):
    monkeypatch.setenv("STRATA_RESEARCH_WATCHLIST", "ogdc, mebl\nOGDC")
    assert load_watchlist() == ["OGDC", "MEBL"]
    monkeypatch.delenv("STRATA_RESEARCH_WATCHLIST")
    assert load_watchlist() == list(WATCHLIST)


def test_watchlist_file_accepts_commas_and_newlines(tmp_path: Path):
    path = tmp_path / "list.txt"
    path.write_text("PSO, HUBC\n\nLUCK\n", encoding="utf-8")
    assert load_watchlist(path) == ["PSO", "HUBC", "LUCK"]


# ----------------------------------------------------------------------
# the desk, end to end
# ----------------------------------------------------------------------
def test_analyze_runs_on_real_portal_data(mirror: Path, capsys):
    from strata_research.cli import main

    exit_code = main(["--offline", "analyze", "OGDC"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "OGDC" in output
    assert "Oil & Gas Development" in output
    assert "Research output generated by an automated agent" in output


def test_watchlist_command_reports_coverage(mirror: Path, capsys, monkeypatch):
    from strata_research.cli import main

    monkeypatch.setenv("STRATA_RESEARCH_PSX_DB", str(mirror))
    monkeypatch.setenv("STRATA_RESEARCH_WATCHLIST", "OGDC,FFC,MEBL")
    exit_code = main(["--offline", "watchlist", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ready"] == 3
    assert {row["ticker"] for row in payload["symbols"]} == {"OGDC", "FFC", "MEBL"}
    assert all(row["source"] == "psx-portal" for row in payload["symbols"])


def test_watchlist_command_fails_loudly_on_an_unknown_symbol(mirror: Path, capsys, monkeypatch):
    from strata_research.cli import main

    monkeypatch.setenv("STRATA_RESEARCH_PSX_DB", str(mirror))
    monkeypatch.setenv("STRATA_RESEARCH_WATCHLIST", "OGDC,ZZZZ")
    exit_code = main(["--offline", "watchlist"])
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "ZZZZ" in output
    assert "1 symbol(s) have no portal financials" in output
