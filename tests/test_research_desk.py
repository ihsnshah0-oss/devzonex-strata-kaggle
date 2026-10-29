"""Tests for the PSX research desk (``strata_research``).

Everything runs offline: the fictional PSX demo universe, local JSON statements,
fake LLM clients and ``httpx.MockTransport`` for both the model endpoint and the
PSX Data Portal.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx

from strata_research.agents import PLANNED_AGENTS, agent_cards, create_agent
from strata_research.agents.base import ResponseParseError, extract_json_object
from strata_research.agents.fundamental import FundamentalAnalyst
from strata_research.cli import main as cli_main
from strata_research.compute import compute_ratios, safe_div
from strata_research.config import Settings, mask_secret
from strata_research.data import DataProviderError, fetch_fundamentals
from strata_research.data.base import to_number
from strata_research.data.demo import DemoProvider
from strata_research.data.json_provider import JsonProvider
from strata_research.data.psx_provider import PsxStatementsProvider
from strata_research.grounding import check_text, collect_values, extract_numbers
from strata_research.heuristics import decide, rule_based_analysis
from strata_research.llm import ChatMessage, LLMError, OpenAIChatClient, ToolCall
from strata_research.orchestrator import ResearchTeam
from strata_research.psx import (
    MACRO_LENS,
    PsxQuoteClient,
    normalize_symbol,
    parse_historical_table,
    scale_statements,
    sector_group,
    sector_note,
    unit_scale,
    yahoo_symbol,
)
from strata_research.render import report_to_markdown
from strata_research.schemas import (
    AnalystOutput,
    CompanyFundamentals,
    ResearchRequest,
)
from strata_research.scoring import ANCHOR_PROFILES, normalize, score_company
from strata_research.tools import ToolRunner, build_context

EPL = "DMEPL"      # Oil & Gas Exploration: net cash, cheap, high yield
FRT = "DMFRT"      # Fertilizer: high margin, high payout
CMT = "DMCMT"      # Cement: cyclical, leveraged
PWR = "DMPWR"      # Power: IPP, circular debt, distressed


def offline_settings(**overrides: Any) -> Settings:
    base = dict(llm_kind="template", data_provider="demo", api_key=None)
    base.update(overrides)
    return Settings(**base)


class FakeLLM:
    """Returns a queued sequence of responses and records the conversation."""

    kind = "openai"
    model_name = "fake-model"

    def __init__(self, responses: list[ChatMessage]) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, Any]]] = []
        self.tool_schemas: list[Any] = []

    def chat(self, messages, *, tools=None, temperature=None, max_tokens=None) -> ChatMessage:
        self.messages.append(list(messages))
        self.tool_schemas.append(tools)
        if not self.responses:
            raise LLMError("no more scripted responses")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def valid_payload(**overrides: Any) -> dict[str, Any]:
    """A note whose numbers all exist in the DMEPL evidence pack."""
    payload = {
        "verdict": "BUY",
        "conviction": 0.7,
        "confidence": 0.8,
        "summary": "Revenue grew 7.7% to 420,000 with ROIC at 38.9%.",
        "investment_thesis": "Net cash and a 24.7% net margin support the case.",
        "strengths": ["ROIC of 38.9%", "Net cash balance sheet"],
        "risks": ["Dividend yield of 7.3% depends on gas prices"],
        "valuation_view": "EV/EBITDA of 3.1x is cheap even for PSX.",
        "growth_view": "Revenue CAGR of 8.8% with EPS of 24.09.",
        "moat": "Low-cost reserves support returns.",
        "red_flags": [],
        "watch_items": ["Gross margin versus 50.0%"],
    }
    payload.update(overrides)
    return payload


def json_message(payload: dict[str, Any]) -> ChatMessage:
    return ChatMessage(content=json.dumps(payload), model="fake-model")


class PsxSymbolAndUnitTests(unittest.TestCase):
    def test_symbol_normalisation(self):
        for raw in ["ogdc", " OGDC ", "PSX:OGDC", "OGDC.KA", "OGDC-KA", "psx-ogdc"]:
            self.assertEqual(normalize_symbol(raw), "OGDC", raw)

    def test_invalid_symbols(self):
        with self.assertRaises(ValueError):
            normalize_symbol("")
        with self.assertRaises(ValueError):
            normalize_symbol("BAD SYMBOL!")
        with self.assertRaises(ValueError):
            normalize_symbol("WAY-TOO-LONG-SYMBOL")

    def test_yahoo_listing_code(self):
        self.assertEqual(yahoo_symbol("LUCK"), "LUCK.KA")
        self.assertEqual(yahoo_symbol("meBL.KA"), "MEBL.KA")

    def test_unit_scaling(self):
        self.assertEqual(unit_scale("thousands"), 0.001)
        self.assertEqual(unit_scale("millions"), 1.0)
        self.assertEqual(unit_scale("crore"), 10.0)
        self.assertEqual(unit_scale(None), 1.0)
        with self.assertRaises(ValueError):
            unit_scale("furlongs")

    def test_scale_statements_keeps_eps_and_year(self):
        scaled = scale_statements(
            [{"fiscal_year": 2025, "revenue": 95000000, "eps": 11.4}], "thousands"
        )
        self.assertEqual(scaled[0]["fiscal_year"], 2025)
        self.assertAlmostEqual(scaled[0]["revenue"], 95000.0)
        self.assertEqual(scaled[0]["eps"], 11.4)  # per-share values are not scaled here

    def test_sector_taxonomy(self):
        self.assertEqual(sector_group("Cement"), "Cement")
        self.assertEqual(sector_group("Power Generation & Distribution"), "Power Generation")
        self.assertEqual(sector_group("Oil & Gas Exploration Companies"), "Oil & Gas Exploration")
        self.assertIsNone(sector_group("Shipping"))
        self.assertIn("circular debt", (sector_note("Power Generation") or "").lower())

    def test_macro_lens_covers_pakistan_drivers(self):
        topics = " ".join(topic for topic, _ in MACRO_LENS).lower()
        for expected in ("policy rate", "pkr/usd", "circular debt", "inflation"):
            self.assertIn(expected, topics)


class PsxQuoteClientTests(unittest.TestCase):
    HTML = """
    <table>
      <tr><th>TIME</th><th>OPEN</th><th>HIGH</th><th>LOW</th><th>CLOSE</th><th>VOLUME</th></tr>
      <tr><td>Oct 28, 2026</td><td>160.10</td><td>166.00</td><td>159.50</td><td>164.25</td><td>1,234,500</td></tr>
      <tr><td>Oct 29, 2026</td><td>164.90</td><td>168.10</td><td>163.00</td><td>165.00</td><td>987,600</td></tr>
    </table>
    """

    def test_parse_historical_table(self):
        rows = parse_historical_table(self.HTML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["close"], 165.0)
        self.assertEqual(rows[-1]["volume"], 987600.0)
        self.assertEqual(rows[-1]["date"].isoformat(), "2026-10-29")

    def test_parse_survives_garbage(self):
        self.assertEqual(parse_historical_table("<html>maintenance</html>"), [])
        self.assertEqual(parse_historical_table(""), [])

    def test_quote_reads_the_chart_feed(self):
        """Without a mirror the live quote comes from /timeseries/eod/{SYM}."""
        payload = {
            "status": 1,
            "message": "",
            "data": [[1793271600, 306.21, 2584565, 306.0], [1793185200, 303.68, 2172474, 302.46]],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/timeseries/eod/OGDC")
            # the portal only answers data routes to XMLHttpRequests with a token
            self.assertEqual(request.headers.get("X-Requested-With"), "XMLHttpRequest")
            return httpx.Response(200, json=payload)

        client = PsxQuoteClient(
            base_url="https://dps.example.pk",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            use_mirror=False,
        )
        quote = client.quote("PSX:OGDC")
        self.assertEqual(quote.symbol, "OGDC")
        self.assertEqual(quote.price, 306.21)
        self.assertEqual(quote.volume, 2584565.0)
        self.assertAlmostEqual(quote.change_pct, 306.21 / 303.68 - 1, places=5)
        self.assertEqual(quote.as_of, "2026-10-29")

    def test_quote_falls_back_to_the_company_page(self):
        """If the feed is down, the company page still carries close and LDCP."""
        company_page = (
            '<div class="stats_item"><div class="stats_label">LDCP</div>'
            '<div class="stats_value">164.25</div></div>'
            '<div class="stats_item"><div class="stats_label">Close</div>'
            '<div class="stats_value">165.00</div></div>'
            '<div class="stats_item"><div class="stats_label">Volume</div>'
            '<div class="stats_value">987,600</div></div>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/timeseries/eod/OGDC":
                return httpx.Response(503, text="feed down")
            self.assertEqual(request.url.path, "/company/OGDC")
            return httpx.Response(200, text=company_page)

        client = PsxQuoteClient(
            base_url="https://dps.example.pk",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            use_mirror=False,
        )
        quote = client.quote("OGDC")
        self.assertEqual(quote.price, 165.0)
        self.assertAlmostEqual(quote.change_pct, 165.0 / 164.25 - 1, places=5)
        self.assertEqual(quote.volume, 987600.0)

    def test_quote_failure_is_not_fatal(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        client = PsxQuoteClient(
            base_url="https://dps.example.pk",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            use_mirror=False,
        )
        quote = client.quote("OGDC")
        self.assertEqual(quote.symbol, "OGDC")
        self.assertIsNone(quote.price)
        self.assertIsNotNone(client.last_error)

    def test_symbols_come_from_the_portal_directory(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/symbols")
            return httpx.Response(
                200,
                json=[
                    {"symbol": "OGDC", "name": "Oil & Gas Development Company Limited"},
                    {"symbol": "LUCK", "name": "Lucky Cement Limited"},
                ],
            )

        client = PsxQuoteClient(
            base_url="https://dps.example.pk",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            use_mirror=False,
        )
        self.assertEqual(client.symbols(), ["OGDC", "LUCK"])

class PsxStatementsProviderTests(unittest.TestCase):
    def write(self, folder: Path, payload: dict[str, Any], name: str = "DMQSR.json") -> Path:
        path = folder / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def payload(self, units: str | None = "millions", price: float | None = 150.0) -> dict:
        data = {
            "profile": {
                "ticker": "DMQSR",
                "name": "Demo Quarry Ltd. (fiction)",
                "sector": "Cement",
                "price": price,
                "shares_outstanding": 100.0,
                "dividend_per_share": 5.0,
            },
            "fiscal_years": [
                {"fiscal_year": 2025, "revenue": 10000, "net_income": 900, "eps": 9.0,
                 "total_equity": 4000, "total_assets": 9000, "operating_cash_flow": 1200,
                 "capex": 400},
                {"fiscal_year": 2024, "revenue": 9200, "net_income": 800, "eps": 8.0,
                 "total_equity": 3700, "total_assets": 8600, "operating_cash_flow": 1100,
                 "capex": 380},
            ],
            "peers": ["LUCK", "mlcf"],
        }
        if units:
            data["units"] = units
        return data

    def test_reads_company_and_normalises_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, self.payload())
            provider = PsxStatementsProvider(folder, use_quotes=False)
            self.assertTrue(provider.available())
            company = provider.fetch("psx:dmqsr")
            self.assertEqual(company.profile.ticker, "DMQSR")
            self.assertEqual(company.profile.currency, "PKR")
            self.assertEqual(company.profile.market, "PSX")
            self.assertEqual(company.profile.sector, "Cement")
            self.assertEqual(company.peers, ["LUCK", "MLCF"])
            self.assertEqual(company.universe if hasattr(company, "universe") else provider.universe()[0]["ticker"], "DMQSR")

    def test_thousands_are_converted_to_millions(self):
        payload = self.payload(units="thousands")
        payload["fiscal_years"][0].update(
            revenue=10_000_000,      # PKR '000 -> 10,000M
            net_income=900_000,      # -> 900M
            total_equity=4_000_000,  # -> 4,000M
            total_assets=9_000_000,
            operating_cash_flow=1_200_000,
            capex=400_000,
        )
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, payload)
            company = PsxStatementsProvider(folder, use_quotes=False).fetch("DMQSR")
        self.assertAlmostEqual(company.latest.revenue, 10000.0)
        self.assertEqual(company.latest.eps, 9.0)
        self.assertAlmostEqual(company.latest.net_income, 900.0)

    def test_live_quote_overrides_price(self):
        class FakeQuote:
            as_of = "2026-10-29"
            price = 188.5

        class FakeClient:
            last_error = None

            def quote(self, symbol):
                assert symbol == "DMQSR"
                return FakeQuote()

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, self.payload())
            provider = PsxStatementsProvider(folder, quote_client=FakeClient(), use_quotes=True)
            company = provider.fetch("DMQSR")
        self.assertEqual(company.profile.price, 188.5)
        self.assertIn("psx-quote", company.profile.data_source)

    def test_missing_quote_keeps_file_price(self):
        class BrokenClient:
            last_error = "timeout"

            def quote(self, symbol):
                raise RuntimeError("network down")

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, self.payload())
            provider = PsxStatementsProvider(folder, quote_client=BrokenClient())
            company = provider.fetch("DMQSR")
        self.assertEqual(company.profile.price, 150.0)
        self.assertTrue(any("quote failed" in note for note in company.profile.notes))

    def test_unknown_symbol_lists_available(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, self.payload())
            with self.assertRaises(DataProviderError) as ctx:
                PsxStatementsProvider(folder, use_quotes=False).fetch("OGDC")
        self.assertIn("DMQSR", str(ctx.exception))

    def test_aggregate_file_is_supported(self):
        aggregate = {"companies": [self.payload(), {
            "profile": {"ticker": "DMAGG", "name": "Demo Aggregate Ltd.", "price": 90.0,
                        "shares_outstanding": 50.0},
            "fiscal_years": [{"fiscal_year": 2025, "revenue": 5000, "net_income": 400,
                              "total_equity": 2000}],
        }]}
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.write(folder, aggregate, "companies.json")
            provider = PsxStatementsProvider(folder, use_quotes=False)
            self.assertEqual(sorted(item["ticker"] for item in provider.universe()),
                             ["DMAGG", "DMQSR"])

    def test_provider_unavailable_without_folder(self):
        self.assertFalse(PsxStatementsProvider(None).available())
        with self.assertRaises(DataProviderError):
            PsxStatementsProvider(None).fetch("OGDC")


class DemoTests(unittest.TestCase):
    def test_demo_universe_is_fictional_psx(self):
        settings = offline_settings()
        for ticker in [EPL, FRT, CMT, PWR]:
            company = fetch_fundamentals(settings, ticker)
            self.assertEqual(company.profile.currency, "PKR")
            self.assertEqual(company.profile.market, "PSX")
            self.assertEqual(company.profile.country, "Pakistan")
            self.assertEqual(company.profile.data_quality, "synthetic")
            self.assertIn("fiction", company.profile.name.lower())
            self.assertEqual(len(company.fiscal_years), 3)

    def test_universe_summary(self):
        summary = DemoProvider().universe_summary()
        self.assertEqual([item["ticker"] for item in summary], [EPL, FRT, CMT, PWR])
        self.assertTrue(all(item["sector"] for item in summary))

    def test_alias_and_symbol_spellings(self):
        self.assertEqual(fetch_fundamentals(offline_settings(), "demo").profile.ticker, EPL)
        self.assertEqual(fetch_fundamentals(offline_settings(), "psx:dmfrt").profile.ticker, FRT)

    def test_unknown_ticker_mentions_psx_options(self):
        with self.assertRaises(DataProviderError) as ctx:
            fetch_fundamentals(offline_settings(), "ZZZZ")
        message = str(ctx.exception)
        self.assertIn("PSX", message)
        self.assertIn("STRATA_RESEARCH_PSX_DIR", message)


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.company = fetch_fundamentals(offline_settings(), EPL)
        self.ratios = compute_ratios(self.company)

    def test_ratio_math_matches_hand_calculation(self):
        r = self.ratios
        self.assertAlmostEqual(r.market_cap, 165.0 * 4300.0, places=2)
        self.assertAlmostEqual(r.net_debt, 40000.0 - 190000.0, places=2)
        self.assertAlmostEqual(r.enterprise_value, 165.0 * 4300.0 - 150000.0, places=2)
        self.assertAlmostEqual(r.ebitda, 150000.0 + 28000.0, places=2)
        self.assertAlmostEqual(r.net_margin, 103600.0 / 420000.0, places=5)
        self.assertAlmostEqual(r.fcf, 150000.0 - 45000.0, places=5)
        self.assertAlmostEqual(r.pe, 165.0 / 24.09, places=4)
        self.assertAlmostEqual(r.dividend_yield, 12.0 / 165.0, places=5)
        self.assertAlmostEqual(r.revenue_cagr, (420000.0 / 355000.0) ** 0.5 - 1, places=5)
        self.assertAlmostEqual(r.ebitda, 178000.0, places=2)

    def test_gross_margin_change_is_explicit(self):
        company = fetch_fundamentals(offline_settings(), PWR)
        ratios = compute_ratios(company)
        self.assertAlmostEqual(ratios.gross_margin_change, 42000 / 210000 - 47000 / 198000, places=5)

    def test_safe_div_handles_zero_and_missing(self):
        self.assertIsNone(safe_div(1.0, 0.0))
        self.assertIsNone(safe_div(None, 2.0))
        self.assertEqual(safe_div(4.0, 2.0), 2.0)

    def test_missing_price_disables_multiples(self):
        company = fetch_fundamentals(offline_settings(), FRT)
        company.profile.price = None
        ratios = compute_ratios(company)
        self.assertIsNone(ratios.pe)
        self.assertIsNone(ratios.market_cap)
        self.assertTrue(any("Market price" in note for note in ratios.notes))

    def test_to_number_filters_junk(self):
        self.assertIsNone(to_number(float("nan")))
        self.assertIsNone(to_number("n/a"))
        self.assertEqual(to_number("1,234.5"), 1234.5)

    def test_generic_json_provider_still_works(self):
        payload = {"companies": [{
            "profile": {"ticker": "TEST", "name": "Test Co", "price": 10,
                        "shares_outstanding": 100},
            "fiscal_years": [{"fiscal_year": 2024, "revenue": 1000, "net_income": 100,
                              "total_equity": 500}],
        }]}
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)
            (path / "companies.json").write_text(json.dumps(payload), encoding="utf-8")
            fetched = JsonProvider(path).fetch("TEST")
        self.assertEqual(fetched.profile.ticker, "TEST")
        self.assertEqual(fetched.fiscal_years[0].fiscal_year, 2024)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.settings = offline_settings()

    def test_quality_order_is_sensible(self):
        scores = {
            ticker: score_company(fetch_fundamentals(self.settings, ticker)).overall
            for ticker in (EPL, FRT, CMT, PWR)
        }
        self.assertGreater(scores[EPL], 70)
        self.assertGreater(scores[FRT], 70)
        self.assertLess(scores[PWR], 40)
        self.assertGreater(scores[EPL], scores[CMT])
        self.assertGreater(scores[CMT], scores[PWR])

    def test_net_cash_scores_well_on_leverage(self):
        """Regression: descending anchors must not punish net cash."""
        scores = score_company(fetch_fundamentals(self.settings, EPL))
        leverage = next(item for item in scores.components
                        if item.key == "net_debt_to_ebitda")
        self.assertLess(leverage.value, 0)
        self.assertEqual(leverage.points, 1.0)

    def test_psx_anchors_are_stricter_on_multiples(self):
        """A 12.7x P/E is mid-range on PSX, but looks cheap on global anchors."""
        company = fetch_fundamentals(self.settings, CMT)
        ratios = compute_ratios(company)
        psx = score_company(company, ratios)
        global_company = company.model_copy(deep=True)
        global_company.profile.market = "GLOBAL"
        global_scores = score_company(global_company, ratios)
        self.assertEqual(psx.anchor_profile, "PSX")
        self.assertEqual(global_scores.anchor_profile, "GLOBAL")
        valuation_psx = next(p.score for p in psx.pillars if p.key == "valuation")
        valuation_global = next(p.score for p in global_scores.pillars if p.key == "valuation")
        self.assertLess(valuation_psx, valuation_global)

    def test_dividend_yield_is_scored(self):
        scores = score_company(fetch_fundamentals(self.settings, PWR))
        dividend = next(item for item in scores.components if item.key == "dividend_yield")
        self.assertEqual(dividend.value, 0.0)
        self.assertEqual(dividend.points, 0.0)
        frt = score_company(fetch_fundamentals(self.settings, FRT))
        frt_dividend = next(item for item in frt.components if item.key == "dividend_yield")
        self.assertGreater(frt_dividend.points, 0.5)

    def test_normalize_is_bidirectional(self):
        self.assertEqual(normalize(18.0, 18.0, 4.0), 0.0)
        self.assertEqual(normalize(4.0, 18.0, 4.0), 1.0)
        self.assertEqual(normalize(0.25, 0.0, 0.25), 1.0)
        self.assertEqual(normalize(-5.0, 0.0, 0.25), 0.0)

    def test_anchor_profiles_cover_every_component(self):
        self.assertEqual(set(ANCHOR_PROFILES["PSX"]), set(ANCHOR_PROFILES["GLOBAL"]))

    def test_red_flags_for_leveraged_ipp(self):
        flags = " ".join(score_company(fetch_fundamentals(self.settings, PWR)).red_flags).lower()
        self.assertIn("interest coverage", flags)
        self.assertIn("leverage", flags)
        self.assertIn("policy-rate", flags)
        self.assertIn("circular-debt", flags)

    def test_cement_interest_cover_flag(self):
        flags = " ".join(score_company(fetch_fundamentals(self.settings, CMT)).red_flags).lower()
        self.assertIn("interest coverage", flags)
        self.assertIn("gross margin compressed", flags)

    def test_missing_inputs_lower_coverage_not_score(self):
        company = fetch_fundamentals(self.settings, EPL)
        thin = CompanyFundamentals(
            profile=company.profile.model_copy(
                update={"price": None, "shares_outstanding": None}
            ),
            fiscal_years=[company.fiscal_years[0]],
        )
        scored = score_company(thin)
        self.assertLess(scored.coverage, 1.0)
        self.assertGreater(scored.overall, 0)

    def test_decisions(self):
        epl = fetch_fundamentals(self.settings, EPL)
        pwr = fetch_fundamentals(self.settings, PWR)
        self.assertEqual(decide(compute_ratios(epl), score_company(epl))[0], "BUY")
        self.assertEqual(decide(compute_ratios(pwr), score_company(pwr))[0], "SELL")

    def test_insufficient_data_when_no_valuation(self):
        company = fetch_fundamentals(self.settings, EPL)
        company.profile.price = None
        company.profile.shares_outstanding = None
        ratios = compute_ratios(company)
        verdict, _, _ = decide(ratios, score_company(company, ratios))
        self.assertEqual(verdict, "INSUFFICIENT_DATA")


class GroundingTests(unittest.TestCase):
    def test_rounded_and_percent_forms_are_grounded(self):
        report = check_text("Quality 85/100, margin 24.7%, EV/EBITDA 3.1x", [84.79, 0.247, 3.143])
        self.assertTrue(report.grounded, report.unverified)

    def test_billion_and_crore_renderings_are_grounded(self):
        report = check_text("Revenue of PKR 420.0bn and PKR 42,000 crore", [420000.0])
        self.assertTrue(report.grounded, report.unverified)

    def test_invented_number_is_flagged(self):
        report = check_text("Revenue reached 9,999 while margins held", [420000.0, 0.247])
        self.assertFalse(report.grounded)
        self.assertIn("9999", report.unverified)

    def test_sign_flip_in_prose_is_grounded(self):
        report = check_text("Revenue declined 3.7% year over year", [-0.0372])
        self.assertTrue(report.grounded, report.unverified)

    def test_years_and_small_counts_are_ignored(self):
        report = check_text("In FY2025 the company had 3 segments", [420000.0])
        self.assertTrue(report.grounded)

    def test_extract_numbers_handles_separators(self):
        self.assertEqual(extract_numbers("420,000 and 12.4%"), [420000.0, 12.4])

    def test_collect_values_includes_statements_and_ratios(self):
        company = fetch_fundamentals(offline_settings(), EPL)
        ratios = compute_ratios(company)
        values = collect_values(company, ratios, score_company(company, ratios))
        self.assertIn(420000.0, values)
        self.assertIn(165.0, values)


class JsonExtractionTests(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(extract_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_wrapped_json(self):
        text = 'Here you go:\n{"a": {"b": 2}}\nHope that helps.'
        self.assertEqual(extract_json_object(text), {"a": {"b": 2}})

    def test_trailing_commas(self):
        self.assertEqual(extract_json_object('{"a": 1, "b": [1, 2,],}'), {"a": 1, "b": [1, 2]})

    def test_garbage_raises(self):
        with self.assertRaises(ResponseParseError):
            extract_json_object("no json here")

    def test_verdict_aliases_and_clamping(self):
        output = AnalystOutput.model_validate(
            {"verdict": "overweight", "conviction": 80, "confidence": "0.4", "risks": "one risk"}
        )
        self.assertEqual(output.verdict, "BUY")
        self.assertEqual(output.conviction, 0.8)
        self.assertEqual(output.confidence, 0.4)
        self.assertEqual(output.risks, ["one risk"])


class PsxContextToolTests(unittest.TestCase):
    def test_context_tool_returns_sector_and_macro(self):
        company = fetch_fundamentals(offline_settings(), PWR)
        runner = ToolRunner(build_context(company))
        payload = runner.run("get_psx_context", {})
        self.assertEqual(payload["market"], "PSX")
        self.assertEqual(payload["sector_group"], "Power Generation")
        self.assertIn("circular debt", payload["sector_lens"].lower())
        self.assertEqual(len(payload["market_lens"]), len(MACRO_LENS))
        self.assertEqual(payload["yahoo_symbol"], "DMPWR.KA")
        self.assertTrue(runner.records[0].ok)

    def test_every_card_tool_is_registered(self):
        from strata_research.agents.fundamental import FUNDAMENTAL_CARD
        from strata_research.tools import TOOLS

        for name in FUNDAMENTAL_CARD.tools:
            self.assertIn(name, TOOLS)


class AgentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.settings = offline_settings(llm_kind="openai", api_key="test-key")
        self.request = ResearchRequest(ticker=EPL)

    def test_offline_agent_returns_grounded_psx_report(self):
        report = FundamentalAnalyst(offline_settings()).run(self.request)
        self.assertEqual(report.mode, "template_llm")
        self.assertEqual(report.analysis.verdict, "BUY")
        self.assertTrue(report.grounding.grounded, report.grounding.unverified)
        self.assertEqual(report.profile.currency, "PKR")
        self.assertEqual(report.profile.market, "PSX")
        self.assertEqual(report.scores.anchor_profile, "PSX")
        self.assertTrue(report.warnings)

    def test_all_demo_companies_are_grounded(self):
        analyst = FundamentalAnalyst(offline_settings())
        for ticker in (EPL, FRT, CMT, PWR):
            report = analyst.run(ResearchRequest(ticker=ticker))
            self.assertTrue(
                report.grounding.grounded,
                f"{ticker}: {report.grounding.unverified}",
            )

    def test_tool_call_round_trip(self):
        llm = FakeLLM([
            ChatMessage(content="", tool_calls=[
                ToolCall(id="c1", name="get_ratios", arguments='{"keys": ["roic"]}')
            ]),
            json_message(valid_payload()),
        ])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertEqual(report.mode, "llm")
        self.assertEqual(len(report.tool_calls), 1)
        self.assertTrue(report.tool_calls[0].ok)
        self.assertEqual(report.tool_calls[0].tool, "get_ratios")
        self.assertEqual(report.request["llm_calls"], 2)
        self.assertTrue(any(m.get("role") == "tool" for m in llm.messages[1]))

    def test_psx_context_tool_round_trip(self):
        llm = FakeLLM([
            ChatMessage(content="", tool_calls=[ToolCall(id="c2", name="get_psx_context")]),
            json_message(valid_payload()),
        ])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertEqual(report.tool_calls[0].tool, "get_psx_context")
        self.assertIn("PSX context", report.tool_calls[0].summary)

    def test_tools_can_be_disabled_for_endpoints_without_support(self):
        llm = FakeLLM([json_message(valid_payload())])
        settings = offline_settings(llm_kind="openai", api_key="k", enable_tools=False)
        FundamentalAnalyst(settings, llm=llm).run(self.request)
        self.assertIsNone(llm.tool_schemas[0])

    def test_repair_after_invalid_json(self):
        llm = FakeLLM([ChatMessage(content="I think it is a buy."), json_message(valid_payload())])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertEqual(report.analysis.verdict, "BUY")
        self.assertEqual(report.request["llm_calls"], 2)

    def test_grounding_repair_rewrites_invented_numbers(self):
        bad = json_message(valid_payload(
            summary="Revenue hit 12,345 in FY2025.",
            investment_thesis="Margins of 55.5% are unprecedented.",
        ))
        report = FundamentalAnalyst(self.settings, llm=FakeLLM([bad, json_message(valid_payload())])).run(self.request)
        self.assertTrue(report.grounding.grounded, report.grounding.unverified)
        self.assertNotIn("12,345", report.analysis.summary)

    def test_unverified_numbers_are_stripped_when_repair_fails(self):
        bad = json_message(valid_payload(
            risks=["Hidden liability of 4,321", "EV/EBITDA of 3.1x is cheap"]
        ))
        report = FundamentalAnalyst(
            self.settings, llm=FakeLLM([bad, ChatMessage(content="cannot comply")])
        ).run(self.request)
        self.assertFalse(report.grounding.grounded)
        self.assertEqual(report.analysis.risks, ["EV/EBITDA of 3.1x is cheap"])
        self.assertTrue(any("Grounding" in warning for warning in report.warnings))

    def test_llm_failure_falls_back_to_deterministic_note(self):
        class BrokenLLM(FakeLLM):
            def chat(self, *args, **kwargs):
                raise LLMError("connection refused")

        report = FundamentalAnalyst(self.settings, llm=BrokenLLM([])).run(self.request)
        self.assertEqual(report.mode, "deterministic_fallback")
        self.assertTrue(any("LLM unavailable" in warning for warning in report.warnings))
        self.assertEqual(report.analysis.verdict, "BUY")

    def test_llm_failure_raises_when_fallback_disabled(self):
        class BrokenLLM(FakeLLM):
            def chat(self, *args, **kwargs):
                raise LLMError("connection refused")

        settings = offline_settings(
            llm_kind="openai", api_key="k", allow_deterministic_fallback=False
        )
        with self.assertRaises(LLMError):
            FundamentalAnalyst(settings, llm=BrokenLLM([])).run(self.request)

    def test_unknown_tool_is_rejected_without_crashing(self):
        llm = FakeLLM([
            ChatMessage(content="", tool_calls=[ToolCall(id="x", name="drop_tables")]),
            json_message(valid_payload()),
        ])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertFalse(report.tool_calls[0].ok)
        self.assertIn("not enabled", report.tool_calls[0].error or "")

    def test_tool_loop_is_bounded(self):
        loops = [ChatMessage(content="", tool_calls=[ToolCall(id=f"c{i}", name="get_ratios")])
                 for i in range(6)]
        settings = offline_settings(
            llm_kind="openai", api_key="k", allow_deterministic_fallback=False
        )
        with self.assertRaises(LLMError):
            FundamentalAnalyst(settings, llm=FakeLLM(loops)).run(self.request)

    def test_rule_based_draft_for_ipp_is_defensive(self):
        company = fetch_fundamentals(offline_settings(), PWR)
        ratios = compute_ratios(company)
        draft = rule_based_analysis(company, ratios, score_company(company, ratios))
        self.assertEqual(draft.verdict, "SELL")
        self.assertTrue(draft.red_flags)
        self.assertTrue(any("circular" in item.lower() for item in draft.watch_items))


class HttpTransportTests(unittest.TestCase):
    def settings(self, **overrides):
        base = dict(llm_kind="openai", api_key="sk-strata-super-secret",
                    base_url="http://model.local/v1", model="test-model",
                    max_retries=1, request_timeout=5)
        base.update(overrides)
        return Settings(**base)

    def test_parses_tool_calls_and_usage(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer sk-strata-super-secret")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "test-model")
            self.assertIn("tools", body)
            return httpx.Response(200, json={
                "model": "test-model",
                "choices": [{"message": {"content": "", "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "get_ratios", "arguments": "{}"}}]},
                    "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            })

        client = OpenAIChatClient(self.settings(), httpx.Client(transport=httpx.MockTransport(handler)))
        message = client.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
        self.assertEqual(message.tool_calls[0].name, "get_ratios")
        self.assertEqual(message.usage["prompt_tokens"], 10)

    def test_retries_then_succeeds(self):
        state = {"calls": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["calls"] += 1
            if state["calls"] == 1:
                return httpx.Response(503, json={"error": {"message": "overloaded"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        client = OpenAIChatClient(self.settings(), httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(client.chat([{"role": "user", "content": "hi"}]).content, "ok")
        self.assertEqual(state["calls"], 2)

    def test_error_message_never_leaks_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key sk-strata-super-secret"}})

        client = OpenAIChatClient(self.settings(), httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(LLMError) as ctx:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertNotIn("sk-strata-super-secret", str(ctx.exception))
        self.assertEqual(ctx.exception.status, 401)

    def test_settings_mask_secrets(self):
        self.assertNotIn("super-secret", json.dumps(self.settings().public_dict()))
        self.assertIn("set", mask_secret("abcd"))


class LiveServerIntegrationTests(unittest.TestCase):
    """Runs the real agent against a real HTTP server (still fully offline)."""

    def test_agent_round_trip_over_http(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        calls = {"count": 0, "saw_tool_result": False, "path": ""}
        final = valid_payload()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return None

            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                calls["count"] += 1
                calls["path"] = self.path
                if self.headers.get("authorization") != "Bearer test-key":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error": {"message": "bad key"}}')
                    return
                if calls["count"] == 1:
                    message = {"role": "assistant", "content": "", "tool_calls": [
                        {"id": "call_1", "type": "function",
                         "function": {"name": "get_ratios", "arguments": '{"keys": ["roic"]}'}}]}
                    finish = "tool_calls"
                else:
                    calls["saw_tool_result"] = any(
                        item.get("role") == "tool" for item in body["messages"]
                    )
                    message = {"role": "assistant", "content": json.dumps(final)}
                    finish = "stop"
                payload = {"model": body.get("model"),
                           "choices": [{"message": message, "finish_reason": finish}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                     "total_tokens": 120}}
                blob = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            settings = Settings(llm_kind="openai", base_url=f"http://127.0.0.1:{port}/v1",
                                api_key="test-key", model="fake-strata", data_provider="demo")
            with ResearchTeam(settings) as team:
                report = team.analyse_ticker(EPL)
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(calls["path"], "/v1/chat/completions")
        self.assertEqual(report.mode, "llm")
        self.assertEqual(report.model, "fake-strata")
        self.assertEqual(report.request["llm_calls"], 2)
        self.assertTrue(calls["saw_tool_result"])
        self.assertTrue(report.tool_calls[0].ok)
        self.assertEqual(report.usage["total_tokens"], 240)
        self.assertTrue(report.grounding.grounded, report.grounding.unverified)


class TeamAndApiTests(unittest.TestCase):
    def build_team(self):
        return ResearchTeam(offline_settings())

    def test_team_brief_and_history(self):
        with self.build_team() as team:
            brief = team.brief(EPL, focus="dividend sustainability")
            self.assertEqual(len(brief.reports), 1)
            self.assertEqual(brief.reports[0].ticker, EPL)
            self.assertIn("BUY", brief.headline)
            self.assertIn("PKR", brief.headline)
            self.assertEqual(len(brief.roadmap), len(PLANNED_AGENTS))
            self.assertEqual(len(team.history()), 1)
            report = team.get_report(brief.reports[0].report_id)
            self.assertIsNotNone(report)

    def test_status_is_psx_scoped(self):
        with self.build_team() as team:
            status = team.status()
            self.assertEqual(status["market"], "PSX")
            self.assertEqual(status["currency"], "PKR")
            self.assertEqual(status["settings"]["llm_kind"], "template")
            self.assertEqual(len(status["agents"]), len(agent_cards()))
            self.assertEqual(status["agents"][0]["status"], "available")
            self.assertIn(EPL, status["demo_tickers"])
            self.assertTrue(any(p["name"] == "psx" for p in status["providers"]))

    def test_psx_context(self):
        with self.build_team() as team:
            context = team.psx_context(CMT)
            self.assertEqual(context["sector_group"], "Cement")
            self.assertEqual(context["yahoo_symbol"], "DMCMT.KA")
            self.assertIn("despatch", (context["sector_lens"] or "").lower())
            self.assertTrue(context["market_lens"])

    def test_create_agent_registry(self):
        analyst = create_agent("fundamental_analyst", offline_settings())
        self.assertIsInstance(analyst, FundamentalAnalyst)
        with self.assertRaises(KeyError):
            create_agent("portfolio_manager", offline_settings())

    def test_markdown_rendering_is_psx_labelled(self):
        with self.build_team() as team:
            report = team.analyse_ticker(PWR)
        markdown = report_to_markdown(report)
        self.assertIn("# Demo Power Generation Ltd. (fiction) (DMPWR)", markdown)
        self.assertIn("*Market:* PSX", markdown)
        self.assertIn("Verdict:", markdown)
        self.assertIn("PSX anchors", markdown)
        self.assertIn("Not investment advice", markdown)

    def test_api_endpoints(self):
        from fastapi.testclient import TestClient

        from strata_research.api import create_app

        app = create_app(offline_settings())
        with TestClient(app) as client:
            health = client.get("/health").json()
            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["market"], "PSX")
            status = client.get("/api/v1/status").json()
            self.assertEqual(status["desk"], "DevZoneX PSX Research Desk")
            agents = client.get("/api/v1/agents").json()
            self.assertIn("fundamental_analyst", agents["available"])
            self.assertIn("get_psx_context", [tool["name"] for tool in agents["tools"]])

            preview = client.get("/api/v1/companies/DMEPL/preview").json()
            self.assertAlmostEqual(preview["ratios"]["pe"], 165.0 / 24.09, places=3)
            self.assertEqual(preview["profile"]["currency"], "PKR")
            self.assertEqual(client.get("/api/v1/companies/ZZZZ/preview").status_code, 404)

            symbols = client.get("/api/v1/psx/symbols").json()
            self.assertEqual(symbols["market"], "PSX")
            self.assertEqual([item["ticker"] for item in symbols["demo"]], [EPL, FRT, CMT, PWR])
            self.assertEqual(symbols["yahoo_suffix"], ".KA")

            context = client.get("/api/v1/psx/context/PSX:DMPWR").json()
            self.assertEqual(context["sector_group"], "Power Generation")
            self.assertEqual(client.get("/api/v1/psx/yahoo/luck").json()["yahoo_symbol"], "LUCK.KA")

            response = client.post("/api/v1/agents/fundamental/analyze",
                                   json={"ticker": "dmcmt", "focus": "balance sheet risk"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["ticker"], CMT)
            self.assertEqual(body["analysis"]["verdict"], "SELL")
            self.assertEqual(body["scores"]["anchor_profile"], "PSX")

            invalid = client.post("/api/v1/agents/fundamental/analyze", json={"ticker": "BAD TICKER"})
            self.assertEqual(invalid.status_code, 422)

            brief = client.post("/api/v1/team/brief", json={"ticker": FRT}).json()
            self.assertEqual(brief["ticker"], FRT)
            listing = client.get("/api/v1/reports").json()["reports"]
            self.assertGreaterEqual(len(listing), 2)
            self.assertEqual(client.get(f"/api/v1/reports/{body['report_id']}").status_code, 200)
            self.assertEqual(client.get("/api/v1/reports/nope").status_code, 404)
            demo = client.get("/api/v1/demo/companies").json()
            self.assertEqual(demo["tickers"], [EPL, FRT, CMT, PWR])

    def test_ui_is_served(self):
        from fastapi.testclient import TestClient

        from strata_research.api import create_app

        with TestClient(create_app(offline_settings())) as client:
            page = client.get("/ui/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("PSX Research Desk", page.text)


class CliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = cli_main(argv)
        return code, buffer.getvalue()

    def test_status_json(self):
        code, output = self.run_cli(["--offline", "status", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["settings"]["llm_kind"], "template")
        self.assertEqual(payload["market"], "PSX")

    def test_psx_universe_command(self):
        code, output = self.run_cli(["--offline", "psx"])
        self.assertEqual(code, 0)
        self.assertIn("Pakistan Stock Exchange", output)
        for ticker in (EPL, FRT, CMT, PWR):
            self.assertIn(ticker, output)
        self.assertIn("Policy rate", output)

    def test_psx_json(self):
        code, output = self.run_cli(["--offline", "psx", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual([item["ticker"] for item in payload["demo_companies"]],
                         [EPL, FRT, CMT, PWR])
        self.assertIn("Cement", payload["sectors"])

    def test_analyze_json(self):
        code, output = self.run_cli(["--offline", "analyze", EPL, "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["agent"], "fundamental_analyst")
        self.assertEqual(payload["profile"]["market"], "PSX")
        self.assertIn(payload["analysis"]["verdict"],
                      {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"})

    def test_unknown_ticker_exits_nonzero(self):
        code, _ = self.run_cli(["--offline", "analyze", "NOPE"])
        self.assertEqual(code, 1)

    def test_agents_listing(self):
        code, output = self.run_cli(["--offline", "agents"])
        self.assertEqual(code, 0)
        self.assertIn("Fundamental Analyst", output)

    def test_brief_markdown_export(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "brief.md"
            code, _ = self.run_cli(["--offline", "brief", FRT, "--save", str(target)])
            self.assertEqual(code, 0)
            content = target.read_text(encoding="utf-8")
            self.assertIn("# Desk brief — DMFRT", content)
            self.assertIn("Agent coverage", content)


if __name__ == "__main__":
    unittest.main()
