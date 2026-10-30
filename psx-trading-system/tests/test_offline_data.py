"""Offline data tests — the app must be useful with the network switched off.

Every test here runs against the PSX Data Portal mirror shipped with the
repository (`data/psx.db.gz`), never against the internet. PSX_OFFLINE=1 is set
before the app modules are imported, so even a machine with a working connection
exercises the offline ladder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# Force the offline ladder for the whole session, before importing the app.
os.environ["PSX_OFFLINE"] = "1"

from src.data import mirror, psx_client                      # noqa: E402
from src.data import fundamentals, news                      # noqa: E402
from src.screener import engine as screener                  # noqa: E402
from src.agents import analysis                              # noqa: E402

WATCHLIST = ["MEBL", "MCB", "UBL", "HBL", "BOP", "NBP", "MARI", "OGDC", "PPL",
             "POL", "PSO", "APL", "FFC", "EFERT", "ENGROH", "LOTCHEM", "AHCL",
             "SYS", "TRG", "AIRLINK", "LUCK", "MLCF", "DGKC", "HUBC", "NESTLE"]

pytestmark = pytest.mark.skipif(not mirror.available(),
                                reason="portal mirror not present")


# ── mirror presence and metadata ────────────────────────────────────
def test_mirror_is_available():
    assert mirror.available() is True


def test_mirror_path_is_portal_not_ledger():
    """The mirror must never be mistaken for the paper-trading ledger."""
    assert mirror.path().name in ("portal.db", "portal.db.gz", "psx.db.gz",
                                  "psx.db", "psx-mirror.db", "psx-mirror.db.gz")
    assert mirror.path().parent.name == "data"


def test_mirror_meta_has_capture_time():
    m = mirror.meta()
    assert m["available"] is True
    assert m["as_of"], "mirror must record when the portal was captured"


def test_mirror_age_is_finite():
    age = mirror.age_days()
    assert age is not None and age >= 0


def test_mirror_source_string_mentions_portal():
    assert "PSX Data Portal" in mirror.SOURCE


def test_coverage_reports_history_symbols():
    cov = mirror.coverage()
    assert cov.get("history_symbols", 0) > 50


# ── snapshot ────────────────────────────────────────────────────────
def test_snapshot_has_expected_columns():
    snap = mirror.snapshot()
    for col in ("symbol", "name", "price", "prev_close", "change_pct",
                "market_cap", "sector", "sector_label", "pe_ratio"):
        assert col in snap.columns, f"missing {col}"


def test_snapshot_is_not_empty():
    assert len(mirror.snapshot()) > 300


def test_snapshot_symbols_are_unique():
    snap = mirror.snapshot()
    assert snap["symbol"].is_unique


def test_snapshot_change_pct_is_derived():
    snap = mirror.snapshot().dropna(subset=["price", "prev_close"])
    row = snap[snap["prev_close"] > 0].iloc[0]
    expected = round((row["price"] / row["prev_close"] - 1) * 100, 2)
    assert abs(row["change_pct"] - expected) < 0.05


def test_snapshot_market_caps_are_not_thousandfold():
    """A 1000× unit mix-up once pushed the total market cap past 40 trillion."""
    total = float(mirror.snapshot()["market_cap"].sum(skipna=True))
    assert 1e12 < total < 6e13, total


def test_snapshot_sector_code_and_label_differ_in_kind():
    snap = mirror.snapshot().dropna(subset=["sector_label"])
    row = snap[snap["sector_label"] != ""].iloc[0]
    assert str(row["sector"]).isdigit() or row["sector"] == ""
    assert not str(row["sector_label"]).isdigit()


# ── quotes and history ──────────────────────────────────────────────
def test_quote_returns_watchlist_price():
    q = mirror.quote("OGDC")
    assert q["symbol"] == "OGDC"
    assert q["close"] and q["close"] > 0


def test_quote_change_matches_price_and_prev_close():
    q = mirror.quote("OGDC")
    if q.get("ldcp"):
        assert abs(q["change"] - round(q["close"] - q["ldcp"], 2)) < 0.02


def test_quote_unknown_symbol_is_empty():
    assert mirror.quote("NOSUCHSYMBOL") == {}


def test_every_watchlist_symbol_has_a_quote():
    missing = [s for s in WATCHLIST if not mirror.quote(s)]
    assert not missing, f"no portal data for {missing}"


def test_history_returns_ohlcv_frame():
    df = mirror.history("OGDC")
    assert len(df) > 500
    for col in ("date", "open", "high", "low", "close", "volume"):
        assert col in df.columns


def test_history_is_chronological():
    df = mirror.history("OGDC")
    dates = pd.to_datetime(df["date"])
    assert dates.is_monotonic_increasing


def test_history_high_bounds_close():
    df = mirror.history("OGDC").tail(50)
    assert (df["high"] + 1e-6 >= df["close"]).all()
    assert (df["low"] - 1e-6 <= df["close"]).all()


def test_last_bar_is_newest_history_row():
    bar = mirror.last_bar("OGDC")
    df = mirror.history("OGDC")
    assert str(bar["date"])[:10] == str(pd.to_datetime(df["date"].iloc[-1]).date())


def test_has_history_flags_thin_symbols():
    assert mirror.has_history("OGDC") is True
    assert mirror.has_history("NOSUCHSYMBOL") is False


def test_symbols_with_history_is_a_list():
    syms = mirror.symbols_with_history()
    assert isinstance(syms, list) and "OGDC" in syms


# ── indexes ─────────────────────────────────────────────────────────
def test_indices_include_kse100_and_kmi30():
    codes = {i["code"] for i in mirror.indices()}
    assert {"KSE100", "KMI30"} <= codes


def test_kse100_level_is_plausible():
    kse = next(i for i in mirror.indices() if i["code"] == "KSE100")
    assert 10_000 < kse["value"] < 500_000


def test_index_history_has_rows():
    df = mirror.index_history("KSE100", limit=120)
    assert len(df) > 20


def test_membership_counts():
    assert len(mirror.members("KSE100")) == 100
    assert len(mirror.members("KMI30")) == 30


def test_members_are_listed_symbols():
    listed = set(mirror.all_symbols())
    assert set(mirror.members("KMI30")) <= listed


# ── sectors and performance ─────────────────────────────────────────
def test_sectors_have_codes_and_names():
    df = mirror.sectors()
    assert not df.empty
    assert {"sector_code", "sector_name"} <= set(df.columns)


def test_sector_symbols_group_members():
    groups = mirror.sector_symbols()
    assert groups and all(isinstance(v, list) for v in groups.values())


def test_performance_has_window_returns():
    perf = mirror.performance("OGDC")
    assert perf.get("high_52w") and perf.get("low_52w")
    assert perf["high_52w"] >= perf["low_52w"]


def test_week_changes_cover_many_symbols():
    assert len(mirror.week_changes()) > 100


# ── financial statements ────────────────────────────────────────────
def test_financials_frame_for_ogdc():
    df = mirror.financials("OGDC")
    assert not df.empty
    assert {"metric", "value", "fiscal_year"} <= set(df.columns)


def test_statements_revenue_in_rupees_not_thousands():
    st = mirror.statements("OGDC")
    latest = next(v for v in st["revenue"] if v)
    assert latest > 1e11, "revenue should be absolute PKR (portal sends thousands)"


def test_statements_eps_is_rupees():
    st = mirror.statements("OGDC")
    eps = next(v for v in st["eps"] if v)
    assert 0 < eps < 1000


def test_statements_are_newest_first():
    st = mirror.statements("OGDC")
    assert st["years"] == sorted(st["years"], reverse=True)
    assert len(st["revenue"]) == len(st["years"])


def test_unknown_symbol_statements_are_empty():
    assert mirror.statements("NOSUCHSYMBOL") == {}


# ── offline client ladder ───────────────────────────────────────────
def test_client_reports_offline():
    assert psx_client.network_up() is False
    assert psx_client.network_state()["up"] is False


def test_client_quote_served_from_mirror():
    q = psx_client.get_quote("OGDC")
    assert (q.get("close") or q.get("price")) > 0
    assert "Portal" in str(q.get("source", ""))


def test_client_history_served_offline():
    df = psx_client.get_history("OGDC")
    assert len(df) > 500


def test_client_snapshot_served_offline():
    snap = psx_client.get_market_snapshot()
    assert len(snap) > 300
    assert "symbol" in snap.columns


def test_client_kse100_membership_read_from_mirror():
    members = psx_client.get_kse100()
    assert len(members) == 100


def test_client_sectors_served_offline():
    df = psx_client.get_sectors()
    assert not df.empty


def test_datasources_marks_mirror_as_offline():
    info = psx_client.data_sources()
    assert info["network"]["up"] is False
    assert info["mirror"]["available"] is True


# ── fundamentals ────────────────────────────────────────────────────
def test_sector_name_accepts_name_as_is():
    assert fundamentals._sector_name("Oil & Gas Exploration Companies") == \
        "Oil & Gas Exploration Companies"


def test_sector_name_resolves_numeric_code():
    code = mirror.snapshot().dropna(subset=["sector_label"]).query("sector != ''")
    row = code[code["sector_label"] != ""].iloc[0]
    name = fundamentals._sector_name(row["sector"])
    assert name.lower() == str(row["sector_label"]).lower()


def test_sector_name_unknown_code_is_labelled_not_dashed():
    assert fundamentals._sector_name("9999")


def test_worth_caching_rejects_empty_payload():
    assert fundamentals._worth_caching({}) is False
    assert fundamentals._worth_caching({"price": None}) is False


def test_worth_caching_accepts_priced_payload():
    assert fundamentals._worth_caching({"price": 306.47}) is True


def test_fundamentals_offline_returns_price_and_pe():
    f = fundamentals.get_fundamentals("OGDC")
    assert f.get("price")
    assert f.get("pe") or f.get("pe_ratio")


# ── agents ──────────────────────────────────────────────────────────
def test_analysis_statements_prefer_mirror():
    st = analysis.statements_pack("OGDC")
    assert st.get("revenue")


def test_analysis_statements_do_not_crash_without_data():
    st = analysis.statements_pack("NOSUCHSYMBOL")
    assert st["revenue"] == [] and st["net_income"] == []


def test_analysis_cagr_handles_single_year():
    assert analysis._cagr(100, 110, 1) == pytest.approx(10.0, abs=0.2)


# ── screener ────────────────────────────────────────────────────────
def test_screener_universe_uses_mirror():
    df = screener.universe()
    assert len(df) > 300
    assert "symbol" in df.columns


def test_screener_sector_filter_accepts_name():
    snap = mirror.snapshot()
    label = snap.dropna(subset=["sector_label"]).query("sector_label != ''")["sector_label"].iloc[0]
    out = screener.run({"sectors": [label], "include_technicals": False})
    assert out["count"] >= 1
    assert all(str(r["sector_label"]).lower() == label.lower() for r in out["rows"])


def test_screener_sector_filter_accepts_code():
    snap = mirror.snapshot()
    row = snap.query("sector != '' and sector_label != ''").iloc[0]
    out = screener.run({"sectors": [row["sector"]], "include_technicals": False})
    assert out["count"] >= 1


# ── news guard ──────────────────────────────────────────────────────
def test_news_without_feedparser_returns_empty(monkeypatch):
    monkeypatch.setattr(news, "feedparser", None)
    assert news._fetch_feed("any", "http://example.invalid/feed") == []


def test_offline_news_returns_list():
    assert isinstance(news.get_market_news(limit=5), list)
