"""Tests for the Strata research desk (strata_research package).

Everything runs offline: the demo data provider plus fake LLM clients. The real
HTTP transport is exercised with httpx.MockTransport instead of a live endpoint.
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
from strata_research.data.json_provider import JsonProvider
from strata_research.grounding import check_text, collect_values, extract_numbers
from strata_research.heuristics import decide, rule_based_analysis
from strata_research.llm import ChatMessage, LLMError, OpenAIChatClient, ToolCall
from strata_research.orchestrator import ResearchTeam
from strata_research.render import report_to_markdown
from strata_research.schemas import AnalystOutput, CompanyFundamentals, ResearchRequest
from strata_research.scoring import normalize, score_company


def offline_settings(**overrides: Any) -> Settings:
    base = dict(llm_kind="template", data_provider="demo", api_key=None)
    base.update(overrides)
    return Settings(**base)


NOVA = "NOVA"
ARCL = "ARCL"
HELX = "HELX"


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
    payload = {
        "verdict": "BUY",
        "conviction": 0.7,
        "confidence": 0.8,
        "summary": "Revenue grew 17.8% to 2,450 with ROIC at 20.1%.",
        "investment_thesis": "Returns are high and the balance sheet holds net cash.",
        "strengths": ["ROIC of 20.1%"],
        "risks": ["P/E of 33.3x leaves little room for error"],
        "valuation_view": "EV/EBITDA of 19.7x is full.",
        "growth_view": "Revenue CAGR of 18.3%.",
        "moat": "Software mix supports returns.",
        "red_flags": [],
        "watch_items": ["Gross margin versus 50.0%"],
    }
    payload.update(overrides)
    return payload


def json_message(payload: dict[str, Any]) -> ChatMessage:
    return ChatMessage(content=json.dumps(payload), model="fake-model")


class DataAndMathTests(unittest.TestCase):
    def test_demo_provider_is_labelled_synthetic(self):
        company = fetch_fundamentals(offline_settings(), NOVA)
        self.assertEqual(company.profile.data_quality, "synthetic")
        self.assertEqual(len(company.fiscal_years), 3)
        self.assertEqual(company.fiscal_years[0].fiscal_year, 2025)

    def test_deterministic_ticker_alias(self):
        self.assertEqual(
            fetch_fundamentals(offline_settings(), "demo").profile.ticker, "NOVA"
        )

    def test_unknown_ticker_raises_helpful_error(self):
        with self.assertRaises(DataProviderError) as ctx:
            fetch_fundamentals(offline_settings(), "ZZZZ")
        self.assertIn("demo universe", str(ctx.exception))

    def test_ratio_math_matches_hand_calculation(self):
        company = fetch_fundamentals(offline_settings(), NOVA)
        ratios = compute_ratios(company)
        self.assertAlmostEqual(ratios.market_cap, 84.20 * 120.0, places=2)
        self.assertAlmostEqual(ratios.net_debt, 420.0 - 610.0, places=2)
        self.assertAlmostEqual(ratios.enterprise_value, 84.20 * 120.0 - 190.0, places=2)
        self.assertAlmostEqual(ratios.ebitda, 392.0 + 110.0, places=2)
        self.assertAlmostEqual(ratios.net_margin, 304.0 / 2450.0, places=5)
        self.assertAlmostEqual(ratios.roic, (392.0 * 0.8) / (420.0 + 1750.0 - 610.0), places=5)
        self.assertAlmostEqual(ratios.fcf, 430.0 - 130.0, places=5)
        self.assertAlmostEqual(ratios.pe, 84.20 / 2.53, places=4)
        self.assertAlmostEqual(ratios.revenue_cagr, (2450.0 / 1750.0) ** 0.5 - 1, places=5)

    def test_safe_div_handles_zero_and_missing(self):
        self.assertIsNone(safe_div(1.0, 0.0))
        self.assertIsNone(safe_div(None, 2.0))
        self.assertEqual(safe_div(4.0, 2.0), 2.0)

    def test_missing_price_disables_multiples(self):
        company = fetch_fundamentals(offline_settings(), HELX)
        company.profile.price = None
        ratios = compute_ratios(company)
        self.assertIsNone(ratios.pe)
        self.assertIsNone(ratios.market_cap)
        self.assertTrue(any("Market price" in note for note in ratios.notes))

    def test_to_number_filters_junk(self):
        self.assertIsNone(to_number(float("nan")))
        self.assertIsNone(to_number("n/a"))
        self.assertEqual(to_number("1,234.5"), 1234.5)

    def test_json_provider_reads_local_file(self):
        company = fetch_fundamentals(offline_settings(data_provider="auto"), NOVA)
        payload = {
            "companies": [
                {
                    "profile": {"ticker": "TEST", "name": "Test Co", "price": 10, "shares_outstanding": 100},
                    "fiscal_years": [
                        {"fiscal_year": 2024, "revenue": 1000, "net_income": 100, "total_equity": 500}
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)
            (path / "companies.json").write_text(json.dumps(payload), encoding="utf-8")
            provider = JsonProvider(path)
            fetched = provider.fetch("TEST")
            self.assertEqual(fetched.profile.ticker, "TEST")
            self.assertEqual(fetched.fiscal_years[0].fiscal_year, 2024)
        self.assertEqual(company.profile.data_quality, "synthetic")


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.settings = offline_settings()
        self.nova = fetch_fundamentals(self.settings, NOVA)
        self.arcl = fetch_fundamentals(self.settings, ARCL)

    def test_quality_order_is_sensible(self):
        nova = score_company(self.nova)
        arcl = score_company(self.arcl)
        self.assertGreater(nova.overall, 60)
        self.assertLess(arcl.overall, 40)
        self.assertEqual(nova.grade, "B")
        self.assertEqual(arcl.grade, "F")

    def test_net_cash_scores_well_on_leverage(self):
        """Regression: descending anchors must not punish net cash."""
        nova = score_company(self.nova)
        leverage = next(
            item for item in nova.components if item.key == "net_debt_to_ebitda"
        )
        self.assertLess(leverage.value, 0)
        self.assertEqual(leverage.points, 1.0)

    def test_normalize_is_bidirectional(self):
        self.assertEqual(normalize(4.0, 4.0, 0.0), 0.0)
        self.assertEqual(normalize(0.0, 4.0, 0.0), 1.0)
        self.assertEqual(normalize(0.25, 0.0, 0.25), 1.0)
        self.assertEqual(normalize(-5.0, 0.0, 0.25), 0.0)

    def test_red_flags_detect_leverage_and_margin_pressure(self):
        flags = " ".join(score_company(self.arcl).red_flags).lower()
        self.assertIn("interest coverage", flags)
        self.assertIn("leverage", flags)
        self.assertIn("net margin", flags)

    def test_missing_inputs_lower_coverage_not_score(self):
        thin = CompanyFundamentals(
            profile=self.nova.profile.model_copy(
                update={"price": None, "shares_outstanding": None}
            ),
            fiscal_years=[self.nova.fiscal_years[0]],
        )
        scored = score_company(thin)
        self.assertLess(scored.coverage, 1.0)
        self.assertGreater(scored.overall, 0)

    def test_decisions(self):
        self.assertEqual(decide(compute_ratios(self.nova), score_company(self.nova))[0], "BUY")
        self.assertEqual(decide(compute_ratios(self.arcl), score_company(self.arcl))[0], "SELL")

    def test_insufficient_data_when_no_valuation(self):
        company = fetch_fundamentals(self.settings, NOVA)
        company.profile.price = None
        company.profile.shares_outstanding = None
        ratios = compute_ratios(company)
        verdict, _, _ = decide(ratios, score_company(company, ratios))
        self.assertEqual(verdict, "INSUFFICIENT_DATA")


class GroundingTests(unittest.TestCase):
    def test_rounded_and_percent_forms_are_grounded(self):
        report = check_text("Quality 79/100, margin 12.4%, EV/EBITDA 19.7x", [78.59, 0.124, 19.749])
        self.assertTrue(report.grounded, report.unverified)

    def test_invented_number_is_flagged(self):
        report = check_text("Revenue reached 9,999 while margins held", [2450.0, 0.124])
        self.assertFalse(report.grounded)
        self.assertIn("9999", report.unverified)

    def test_years_and_small_counts_are_ignored(self):
        report = check_text("In FY2025 the company had 3 segments", [2450.0])
        self.assertTrue(report.grounded)

    def test_sign_flip_in_prose_is_grounded(self):
        """'Revenue declined 3.7%' must match a stored -0.0372."""
        report = check_text("Revenue declined 3.7% year over year", [-0.0372])
        self.assertTrue(report.grounded, report.unverified)

    def test_extract_numbers_handles_separators(self):
        self.assertEqual(extract_numbers("2,450 and 12.4%"), [2450.0, 12.4])

    def test_collect_values_includes_statements_and_ratios(self):
        company = fetch_fundamentals(offline_settings(), NOVA)
        ratios = compute_ratios(company)
        values = collect_values(company, ratios, score_company(company, ratios))
        self.assertIn(2450.0, values)
        self.assertIn(84.2, values)


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


class AgentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.settings = offline_settings(llm_kind="openai", api_key="test-key")
        self.request = ResearchRequest(ticker=NOVA)

    def test_offline_agent_returns_grounded_report(self):
        analyst = FundamentalAnalyst(offline_settings())
        report = analyst.run(self.request)
        self.assertEqual(report.mode, "template_llm")
        self.assertEqual(report.analysis.verdict, "BUY")
        self.assertTrue(report.grounding.grounded, report.grounding.unverified)
        self.assertEqual(report.ticker, NOVA)
        self.assertTrue(report.warnings)

    def test_tool_call_round_trip(self):
        llm = FakeLLM(
            [
                ChatMessage(
                    content="",
                    tool_calls=[ToolCall(id="c1", name="get_ratios", arguments='{"keys": ["roic"]}')],
                ),
                json_message(valid_payload()),
            ]
        )
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertEqual(report.mode, "llm")
        self.assertEqual(len(report.tool_calls), 1)
        self.assertTrue(report.tool_calls[0].ok)
        self.assertEqual(report.tool_calls[0].tool, "get_ratios")
        self.assertEqual(report.request["llm_calls"], 2)
        second_call_messages = llm.messages[1]
        self.assertTrue(any(message.get("role") == "tool" for message in second_call_messages))
        self.assertIsNotNone(llm.tool_schemas[0])
        self.assertIsNotNone(llm.tool_schemas[1], "tools stay available across rounds")

    def test_tools_can_be_disabled_for_endpoints_without_support(self):
        llm = FakeLLM([json_message(valid_payload())])
        settings = offline_settings(
            llm_kind="openai", api_key="k", enable_tools=False
        )
        FundamentalAnalyst(settings, llm=llm).run(self.request)
        self.assertIsNone(llm.tool_schemas[0])

    def test_repair_after_invalid_json(self):
        llm = FakeLLM(
            [
                ChatMessage(content="I think it is a buy."),
                json_message(valid_payload(verdict="BUY")),
            ]
        )
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertEqual(report.mode, "llm")
        self.assertEqual(report.analysis.verdict, "BUY")
        self.assertEqual(report.request["llm_calls"], 2)

    def test_grounding_repair_rewrites_invented_numbers(self):
        bad = json_message(
            valid_payload(
                summary="Revenue hit 12,345 in FY2025.",
                investment_thesis="Margins of 55.5% are unprecedented.",
            )
        )
        cleaner = json_message(valid_payload())
        llm = FakeLLM([bad, cleaner])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertTrue(report.grounding.grounded, report.grounding.unverified)
        self.assertNotIn("12,345", report.analysis.summary)

    def test_unverified_numbers_are_stripped_when_repair_fails(self):
        bad = json_message(
            valid_payload(
                risks=["Hidden liability of 4,321", "Multiple of 33.3x is full"],
            )
        )
        llm = FakeLLM([bad, ChatMessage(content="cannot comply")])
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertFalse(report.grounding.grounded)
        self.assertEqual(report.analysis.risks, ["Multiple of 33.3x is full"])
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
        llm = FakeLLM(
            [
                ChatMessage(content="", tool_calls=[ToolCall(id="x", name="drop_tables")]),
                json_message(valid_payload()),
            ]
        )
        report = FundamentalAnalyst(self.settings, llm=llm).run(self.request)
        self.assertFalse(report.tool_calls[0].ok)
        self.assertIn("not enabled", report.tool_calls[0].error or "")

    def test_tool_loop_is_bounded(self):
        loops = [
            ChatMessage(content="", tool_calls=[ToolCall(id=f"c{i}", name="get_ratios")])
            for i in range(6)
        ]
        settings = offline_settings(
            llm_kind="openai", api_key="k", allow_deterministic_fallback=False
        )
        with self.assertRaises(LLMError):
            FundamentalAnalyst(settings, llm=FakeLLM(loops)).run(self.request)

    def test_rule_based_draft_is_internally_consistent(self):
        company = fetch_fundamentals(offline_settings(), ARCL)
        ratios = compute_ratios(company)
        draft = rule_based_analysis(company, ratios, score_company(company, ratios))
        self.assertEqual(draft.verdict, "SELL")
        self.assertTrue(draft.red_flags)
        self.assertGreater(len(draft.watch_items), 0)


class HttpTransportTests(unittest.TestCase):
    def settings(self, **overrides):
        base = dict(
            llm_kind="openai",
            api_key="sk-strata-super-secret",
            base_url="http://model.local/v1",
            model="test-model",
            max_retries=1,
            request_timeout=5,
        )
        base.update(overrides)
        return Settings(**base)

    def test_parses_tool_calls_and_usage(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer sk-strata-super-secret")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "test-model")
            self.assertIn("tools", body)
            return httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "get_ratios", "arguments": "{}"},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                },
            )

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
        message = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(message.content, "ok")
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
        settings = self.settings()
        self.assertNotIn("super-secret", json.dumps(settings.public_dict()))
        self.assertIn("set", mask_secret("abcd"))


class LiveServerIntegrationTests(unittest.TestCase):
    """Runs the real agent against a real HTTP server (still fully offline)."""

    def test_agent_round_trip_over_http(self):
        import json as jsonlib
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        calls = {"count": 0, "saw_tool_result": False, "path": ""}
        final = valid_payload()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return None

            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                body = jsonlib.loads(self.rfile.read(length) or b"{}")
                calls["count"] += 1
                calls["path"] = self.path
                if self.headers.get("authorization") != "Bearer test-key":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error": {"message": "bad key"}}')
                    return
                if calls["count"] == 1:
                    message = {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "get_ratios", "arguments": '{"keys": ["roic"]}'},
                            }
                        ],
                    }
                    finish = "tool_calls"
                else:
                    calls["saw_tool_result"] = any(
                        item.get("role") == "tool" for item in body["messages"]
                    )
                    message = {"role": "assistant", "content": jsonlib.dumps(final)}
                    finish = "stop"
                payload = {
                    "model": body.get("model"),
                    "choices": [{"message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                }
                blob = jsonlib.dumps(payload).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            settings = Settings(
                llm_kind="openai",
                base_url=f"http://127.0.0.1:{port}/v1",
                api_key="test-key",
                model="fake-strata",
                data_provider="demo",
            )
            with ResearchTeam(settings) as team:
                report = team.analyse_ticker(NOVA)
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
            brief = team.brief(NOVA, focus="margin durability")
            self.assertEqual(len(brief.reports), 1)
            self.assertEqual(brief.reports[0].ticker, NOVA)
            self.assertIn("BUY", brief.headline)
            self.assertEqual(len(brief.roadmap), len(PLANNED_AGENTS))
            self.assertEqual(len(team.history()), 1)
            report_id = brief.reports[0].report_id
            self.assertIsNotNone(team.get_report(report_id))
            team.close()
            self.assertFalse(any(card["status"] == "available" for card in team.cards()[1:]))

    def test_status_and_cards(self):
        with self.build_team() as team:
            status = team.status()
            self.assertEqual(status["settings"]["llm_kind"], "template")
            self.assertEqual(len(status["agents"]), len(agent_cards()))
            self.assertEqual(status["agents"][0]["status"], "available")

    def test_create_agent_registry(self):
        analyst = create_agent("fundamental_analyst", offline_settings())
        self.assertIsInstance(analyst, FundamentalAnalyst)
        with self.assertRaises(KeyError):
            create_agent("portfolio_manager", offline_settings())

    def test_markdown_rendering(self):
        with self.build_team() as team:
            report = team.analyse_ticker(ARCL)
        markdown = report_to_markdown(report)
        self.assertIn("# Arcadia Retail Group (ARCL)", markdown)
        self.assertIn("Verdict:", markdown)
        self.assertIn("Not investment advice", markdown)
        self.assertIn("## Deterministic ratios", markdown)

    def test_api_endpoints(self):
        from fastapi.testclient import TestClient

        from strata_research.api import create_app

        app = create_app(offline_settings())
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json()["status"], "ok")
            status = client.get("/api/v1/status").json()
            self.assertEqual(status["desk"], "DevZoneX Strata Research Desk")
            agents = client.get("/api/v1/agents").json()
            self.assertIn("fundamental_analyst", agents["available"])
            preview = client.get("/api/v1/companies/NOVA/preview").json()
            self.assertAlmostEqual(preview["ratios"]["pe"], 84.20 / 2.53, places=3)
            missing = client.get("/api/v1/companies/ZZZZ/preview")
            self.assertEqual(missing.status_code, 404)

            response = client.post(
                "/api/v1/agents/fundamental/analyze",
                json={"ticker": "arcl", "focus": "balance sheet risk"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["ticker"], ARCL)
            self.assertEqual(body["analysis"]["verdict"], "SELL")
            self.assertIn("report_id", body)

            invalid = client.post("/api/v1/agents/fundamental/analyze", json={"ticker": "BAD TICKER"})
            self.assertEqual(invalid.status_code, 422)

            brief = client.post("/api/v1/team/brief", json={"ticker": "HELX"}).json()
            self.assertEqual(brief["ticker"], HELX)
            listing = client.get("/api/v1/reports").json()["reports"]
            self.assertGreaterEqual(len(listing), 2)
            detail = client.get(f"/api/v1/reports/{body['report_id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(client.get("/api/v1/reports/nope").status_code, 404)
            self.assertEqual(client.get("/api/v1/demo/companies").json()["tickers"], ["NOVA", "HELX", "ARCL"])

    def test_ui_is_served(self):
        from fastapi.testclient import TestClient

        from strata_research.api import create_app

        app = create_app(offline_settings())
        with TestClient(app) as client:
            page = client.get("/ui/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("Strata Research Desk", page.text)


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

    def test_analyze_json(self):
        code, output = self.run_cli(["--offline", "analyze", NOVA, "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["agent"], "fundamental_analyst")
        self.assertIn(payload["analysis"]["verdict"], {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"})

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
            code, _ = self.run_cli(["--offline", "brief", HELX, "--save", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue(target.exists())
            content = target.read_text(encoding="utf-8")
            self.assertIn("# Desk brief — HELX", content)
            self.assertIn("Agent coverage", content)


if __name__ == "__main__":
    unittest.main()
