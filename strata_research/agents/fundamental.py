"""Agent #1 — the Fundamental Analyst.

Pipeline
--------
1. **Fetch** standardized statements from the provider chain (demo / JSON / live).
2. **Compute** ratios and a rule-based quality score. No LLM touches these.
3. **Draft** a deterministic note (verdict, red flags, scenario maths).
4. **Ask the LLM** to write the research note, with the evidence pack, the draft
   and read-only tools available. Tool calls are executed and audited.
5. **Validate** the JSON against the schema, repairing once if needed.
6. **Ground** every number in the narrative against the deterministic evidence.
7. **Package** a :class:`FundamentalReport` with provenance, usage and warnings.

If the endpoint fails and fallbacks are allowed, the deterministic note is
returned with ``mode="deterministic_fallback"`` instead of a broken response.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from ..compute import compute_ratios
from ..data import DataProviderError, fetch_fundamentals
from ..grounding import check_text, collect_values, extract_numbers, narrative_text
from ..heuristics import rule_based_analysis
from ..llm import LLMError, draft_for
from ..prompts import (
    ANALYST_SYSTEM_PROMPT,
    build_analyst_prompt,
    build_repair_prompt,
)
from ..schemas import (
    AnalystOutput,
    CompanyFundamentals,
    FundamentalReport,
    GroundingReport,
    QualityScore,
    RatioSet,
    ResearchRequest,
    ToolCallRecord,
)
from ..scoring import score_company
from ..tools import ToolContext, ToolRunner, describe_tools, openai_tool_schemas
from .base import AgentCard, BaseAgent, ResponseParseError, extract_json_object

FUNDAMENTAL_CARD = AgentCard(
    key="fundamental_analyst",
    name="Fundamental Analyst",
    title="Agent 1 · Fundamental Analyst",
    status="available",
    description=(
        "Covers PSX-listed companies only. Reads standardized statements, computes "
        "PKR ratios and a PSX-calibrated quality score deterministically, then uses "
        "an LLM to write a grounded note with verdict, conviction and red flags."
    ),
    tools=("get_financials", "get_ratios", "get_score_breakdown",
           "compute_scenario", "get_company_profile", "get_psx_context"),
    techniques=(
        "ratio analysis", "DuPont-style returns decomposition", "cash conversion",
        "rule-based scoring", "grounding validation", "tool-augmented prompting",
    ),
    inputs="ticker, focus, horizon + fundamentals data",
    outputs="FundamentalReport (verdict, thesis, ratios, scores, grounding)",
    order=1,
)

MAX_TOOL_ROUNDS = 3
MAX_MESSAGE_JSON = 6000


class FundamentalAnalyst(BaseAgent):
    """The first analyst on the desk. LLM-assisted, deterministic where it matters."""

    default_tools: tuple[str, ...] = FUNDAMENTAL_CARD.tools

    def __init__(self, settings, **kwargs: Any) -> None:
        super().__init__(settings=settings, card=FUNDAMENTAL_CARD, **kwargs)

    # ------------------------------------------------------------------
    def run(self, request: ResearchRequest) -> FundamentalReport:
        started = time.perf_counter()
        warnings: list[str] = []
        usage: dict[str, Any] = {}

        try:
            company = fetch_fundamentals(self.settings, request.ticker)
        except DataProviderError:
            raise
        ratios = compute_ratios(company)
        scores = score_company(company, ratios)
        context = ToolContext(company=company, ratios=ratios, scores=scores)
        runner = ToolRunner(context=context, allowed=list(self.default_tools))
        draft = rule_based_analysis(company, ratios, scores, focus=request.focus)

        if company.profile.data_quality == "synthetic":
            warnings.append(
                "Fundamentals are synthetic demo data; conclusions are illustrative."
            )

        prompt = build_analyst_prompt(
            company,
            ratios,
            scores,
            focus=request.focus,
            horizon=request.horizon,
            tool_names=list(self.default_tools),
            deterministic_draft=draft.model_dump(),
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        tool_schemas = (
            openai_tool_schemas(list(self.default_tools))
            if self.llm is not None
            and self.llm.kind == "openai"
            and self.settings.enable_tools
            else None
        )

        analysis: AnalystOutput
        mode = "llm" if getattr(self.llm, "kind", "") == "openai" else "template_llm"
        raw_response = ""
        stats = {"llm_calls": 0}
        try:
            raw_response, usage = self._converse(messages, tool_schemas, runner, stats)
            analysis = self._parse(raw_response)
        except ResponseParseError as exc:
            repaired = self._repair(messages, raw_response, str(exc), usage, stats)
            if repaired is None:
                raise
            raw_response, analysis, usage = repaired
        except LLMError as exc:
            if not self.settings.allow_deterministic_fallback:
                raise
            warnings.append(f"LLM unavailable, served the deterministic note: {exc}")
            analysis = draft
            mode = "deterministic_fallback"

        grounding_result = self._ground(
            company, ratios, scores, analysis, messages, raw_response, usage, mode, stats
        )
        if isinstance(grounding_result, tuple):
            analysis, grounding, usage = grounding_result
        else:
            grounding = grounding_result
        if not grounding.grounded:
            warnings.append(
                "Grounding check could not verify every figure: "
                + ", ".join(grounding.unverified)
            )
            analysis = self._strip_unverified(analysis, grounding)

        if analysis.verdict == "INSUFFICIENT_DATA":
            warnings.append("Analyst returned INSUFFICIENT_DATA; evidence coverage was too low.")

        duration_ms = int((time.perf_counter() - started) * 1000)
        return FundamentalReport(
            report_id=uuid.uuid4().hex[:12],
            ticker=company.profile.ticker,
            company=company.profile.name,
            sector=company.profile.sector,
            mode=mode,  # type: ignore[arg-type]
            model=self.model_name,
            request={
                "ticker": request.ticker,
                "focus": request.focus,
                "horizon": request.horizon,
                "llm_calls": stats["llm_calls"],
                "tools_available": list(self.default_tools),
            },
            profile=company.profile,
            ratios=ratios,
            scores=scores,
            analysis=analysis,
            grounding=grounding,
            tool_calls=runner.records,
            usage=usage,
            duration_ms=duration_ms,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    def _converse(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]] | None,
        runner: ToolRunner,
        stats: dict[str, int],
    ) -> tuple[str, dict[str, Any]]:
        assert self.llm is not None
        usage: dict[str, Any] = {}
        content = ""
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            message = self.llm.chat(messages, tools=tool_schemas)
            stats["llm_calls"] += 1
            usage = _merge_usage(usage, message.usage)
            if message.tool_calls:
                if round_index >= MAX_TOOL_ROUNDS:
                    raise LLMError(
                        f"Model requested tools {MAX_TOOL_ROUNDS + 1} times without answering."
                    )
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": call.arguments},
                            }
                            for call in message.tool_calls
                        ],
                    }
                )
                for call in message.tool_calls:
                    payload = runner.run(call.name, call.arguments)
                    serialized = json.dumps(payload, ensure_ascii=False)
                    if len(serialized) > MAX_MESSAGE_JSON:
                        serialized = serialized[:MAX_MESSAGE_JSON] + "…(truncated)"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": serialized,
                        }
                    )
                continue
            content = message.content or ""
            if not content.strip():
                raise LLMError("Model returned an empty message")
            return content, usage
        raise LLMError("Tool loop exhausted without a final answer")

    def _parse(self, text: str) -> AnalystOutput:
        try:
            payload = extract_json_object(text)
        except ResponseParseError:
            raise
        try:
            return AnalystOutput.model_validate(payload)
        except Exception as exc:
            raise ResponseParseError(f"JSON did not match the schema: {exc}") from exc

    def _repair(
        self,
        messages: list[dict[str, Any]],
        previous: str,
        error: str,
        usage: dict[str, Any],
        stats: dict[str, int],
    ) -> tuple[str, AnalystOutput, dict[str, Any]] | None:
        """Re-ask the model for schema-valid JSON, at most N times."""
        assert self.llm is not None
        attempts = max(0, self.settings.max_repair_attempts)
        for _ in range(attempts):
            repair_messages = list(messages) + [
                {"role": "assistant", "content": previous[:MAX_MESSAGE_JSON]},
                {"role": "user", "content": build_repair_prompt(error, previous)},
            ]
            try:
                message = self.llm.chat(repair_messages)
            except LLMError:
                return None
            stats["llm_calls"] += 1
            usage = _merge_usage(usage, message.usage)
            try:
                return message.content, self._parse(message.content), usage
            except ResponseParseError as exc:
                error = str(exc)
                previous = message.content
        return None

    def _ground(
        self,
        company: CompanyFundamentals,
        ratios: RatioSet,
        scores: QualityScore,
        analysis: AnalystOutput,
        messages: list[dict[str, Any]],
        raw_response: str,
        usage: dict[str, Any],
        mode: str,
        stats: dict[str, int],
    ):
        values = collect_values(company, ratios, scores)
        text = narrative_text(analysis.model_dump())
        grounding = check_text(text, values)
        if grounding.grounded or mode != "llm":
            return grounding
        assert self.llm is not None
        attempts = max(0, self.settings.max_repair_attempts)
        for _ in range(attempts):
            instruction = (
                "Your note contains numbers that do not appear in the evidence pack: "
                + ", ".join(grounding.unverified)
                + ". Rewrite the SAME JSON object using only figures present in the "
                "evidence pack, or remove the unsupported claims. Return JSON only."
            )
            repair_messages = list(messages) + [
                {"role": "assistant", "content": raw_response[:MAX_MESSAGE_JSON]},
                {"role": "user", "content": instruction},
            ]
            try:
                message = self.llm.chat(repair_messages)
                stats["llm_calls"] += 1
            except LLMError:
                break
            usage = _merge_usage(usage, message.usage)
            try:
                adjusted = self._parse(message.content)
            except ResponseParseError:
                continue
            adjusted_grounding = check_text(narrative_text(adjusted.model_dump()), values)
            if adjusted_grounding.grounded or len(adjusted_grounding.unverified) < len(
                grounding.unverified
            ):
                return adjusted, adjusted_grounding, usage
        return grounding

    @staticmethod
    def _strip_unverified(analysis: AnalystOutput, grounding: GroundingReport) -> AnalystOutput:
        """Remove list items that still carry unverifiable numbers."""
        if not grounding.unverified:
            return analysis
        bad = set(grounding.unverified)

        def clean(items: list[str]) -> list[str]:
            kept = []
            for item in items:
                numbers = {f"{value:g}" for value in extract_numbers(item)}
                if numbers & bad:
                    continue
                kept.append(item)
            return kept

        return analysis.model_copy(
            update={
                "strengths": clean(analysis.strengths),
                "risks": clean(analysis.risks),
                "red_flags": clean(analysis.red_flags),
                "watch_items": clean(analysis.watch_items),
            }
        )

    # ------------------------------------------------------------------
    @staticmethod
    def tool_catalogue() -> list[dict[str, Any]]:
        return describe_tools()

    @staticmethod
    def tools_summary() -> list[ToolCallRecord]:
        return []


def _merge_usage(total: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(total)
    for key, value in (extra or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value
        else:
            merged[key] = value
    return merged


__all__ = ["FUNDAMENTAL_CARD", "FundamentalAnalyst", "draft_for"]
