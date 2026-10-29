"""Read-only tools the analyst agent can call.

Every tool is a pure function of the already-fetched, already-computed data, so
calling one can never introduce a number that the grounding validator has not
already seen. Tool calls and their durations are recorded on the report, which
makes the agent's reasoning path inspectable.

Adding a tool is a three-line change: write the handler, add a
:class:`ToolSpec`, and pass its name in ``FundamentalAnalyst.default_tools``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .compute import compute_ratios
from .formatting import fmt_pct, fmt_x
from .psx import MACRO_LENS, sector_group, sector_note
from .schemas import CompanyFundamentals, QualityScore, RatioSet, ToolCallRecord
from .scoring import score_company

Handler = Callable[["ToolContext", dict[str, Any]], dict[str, Any]]


@dataclass
class ToolContext:
    company: CompanyFundamentals
    ratios: RatioSet
    scores: QualityScore


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler


def _json(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


# --------------------------------------------------------------------- tools
def _tool_financials(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    try:
        limit = int(args.get("years", 3))
    except (TypeError, ValueError):
        limit = 3
    limit = max(1, min(limit, len(ctx.company.fiscal_years)))
    years = sorted(ctx.company.fiscal_years, key=lambda year: year.fiscal_year)[-limit:]
    fields = [
        "revenue", "gross_profit", "operating_income", "net_income", "eps",
        "operating_cash_flow", "capex", "total_assets", "total_equity",
        "total_debt", "cash_and_equivalents", "current_assets",
        "current_liabilities", "inventory",
    ]
    return _json(
        {
            "currency": ctx.company.profile.currency,
            "units": "millions except eps (per share)",
            "years": [
                {
                    "fiscal_year": year.fiscal_year,
                    **{name: getattr(year, name, None) for name in fields},
                }
                for year in years
            ],
        }
    )


def _tool_ratios(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    requested = args.get("keys")
    available = ctx.ratios.model_dump(exclude={"notes"})
    if isinstance(requested, list) and requested:
        unknown = [key for key in requested if key not in available]
        payload = {key: available[key] for key in requested if key in available}
        if unknown:
            payload["_unknown_keys"] = unknown
        return _json(payload)
    return _json(available)


def _tool_score(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    pillar = args.get("pillar")
    components = [
        component.model_dump()
        for component in ctx.scores.components
        if not pillar or component.pillar == str(pillar)
    ]
    return _json(
        {
            "overall": ctx.scores.overall,
            "grade": ctx.scores.grade,
            "label": ctx.scores.label,
            "coverage": ctx.scores.coverage,
            "pillars": [pillar_score.model_dump() for pillar_score in ctx.scores.pillars],
            "components": components,
            "red_flags": ctx.scores.red_flags,
        }
    )


def _tool_profile(ctx: ToolContext, _args: dict[str, Any]) -> dict[str, Any]:
    return _json(
        {
            "profile": ctx.company.profile.model_dump(),
            "peers": list(ctx.company.peers),
            "fiscal_years_available": [year.fiscal_year for year in ctx.company.fiscal_years],
        }
    )


def tool_scenario(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    latest = ctx.company.latest
    shares = ctx.company.profile.shares_outstanding
    price = ctx.company.profile.price
    if latest.revenue is None or not shares or not price:
        return _json(
            {
                "ok": False,
                "error": "Scenario maths needs revenue, diluted shares and a share price.",
            }
        )
    try:
        growth = float(args.get("revenue_growth", 0.0))
        margin = float(args.get("net_margin", 0.0))
        multiple = float(args.get("pe_multiple", 0.0))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "revenue_growth, net_margin and pe_multiple must be numbers."})
    if not -0.90 <= growth <= 1.50:
        return _json({"ok": False, "error": "revenue_growth must be between -0.90 and 1.50."})
    if not -0.50 <= margin <= 0.80:
        return _json({"ok": False, "error": "net_margin must be between -0.50 and 0.80."})
    if not 1.0 <= multiple <= 120.0:
        return _json({"ok": False, "error": "pe_multiple must be between 1 and 120."})

    revenue_next = latest.revenue * (1.0 + growth)
    net_income = revenue_next * margin
    eps = net_income / shares
    implied_price = eps * multiple
    return _json(
        {
            "ok": True,
            "assumptions": {
                "base_revenue": latest.revenue,
                "revenue_growth": growth,
                "net_margin": margin,
                "pe_multiple": multiple,
            },
            "implied": {
                "revenue_next": round(revenue_next, 2),
                "net_income_next": round(net_income, 2),
                "eps_next": round(eps, 4),
                "share_price": round(implied_price, 2),
                "upside_vs_current": round(implied_price / price - 1.0, 4),
            },
            "display": (
                f"At {fmt_pct(growth)} revenue growth and a {fmt_pct(margin)} net margin, "
                f"EPS would be {eps:.2f}; at {fmt_x(multiple)} the implied price is "
                f"{implied_price:.2f} vs {price:.2f} today."
            ),
        }
    )


def _tool_psx_context(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    profile = ctx.company.profile
    group = sector_group(profile.sector) or sector_group(profile.industry)
    return _json(
        {
            "market": profile.market,
            "exchange": profile.exchange,
            "currency": profile.currency,
            "sector_group": group,
            "sector_lens": sector_note(profile.sector) or sector_note(profile.industry),
            "market_lens": [{"topic": title, "detail": detail} for title, detail in MACRO_LENS],
            "peers": list(ctx.company.peers),
            "yahoo_symbol": f"{profile.ticker}.KA",
        }
    )


TOOLS: dict[str, ToolSpec] = {
    "get_financials": ToolSpec(
        name="get_financials",
        description="Return annual income statement, balance sheet and cash flow fields.",
        parameters={
            "type": "object",
            "properties": {
                "years": {
                    "type": "integer",
                    "description": "How many of the most recent fiscal years to return (1-4).",
                }
            },
            "additionalProperties": False,
        },
        handler=_tool_financials,
    ),
    "get_ratios": ToolSpec(
        name="get_ratios",
        description=(
            "Return deterministic ratios and multiples. Margins, growth and returns "
            "are fractions (0.16 = 16%)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subset of ratio keys; omit for all.",
                }
            },
            "additionalProperties": False,
        },
        handler=_tool_ratios,
    ),
    "get_score_breakdown": ToolSpec(
        name="get_score_breakdown",
        description="Return the rule-based quality score, its pillars, components and red flags.",
        parameters={
            "type": "object",
            "properties": {
                "pillar": {
                    "type": "string",
                    "description": "Optional pillar: profitability, growth, balance_sheet, cash_quality, valuation.",
                }
            },
            "additionalProperties": False,
        },
        handler=_tool_score,
    ),
    "compute_scenario": ToolSpec(
        name="compute_scenario",
        description=(
            "Deterministic scenario maths: implied share price from a revenue growth, "
            "net margin and P/E assumption. Use it instead of inventing price targets."
        ),
        parameters={
            "type": "object",
            "properties": {
                "revenue_growth": {"type": "number", "description": "Fraction, e.g. 0.08"},
                "net_margin": {"type": "number", "description": "Fraction, e.g. 0.12"},
                "pe_multiple": {"type": "number", "description": "Multiple, e.g. 18"},
            },
            "required": ["revenue_growth", "net_margin", "pe_multiple"],
            "additionalProperties": False,
        },
        handler=tool_scenario,
    ),
    "get_psx_context": ToolSpec(
        name="get_psx_context",
        description=(
            "Return PSX market context: sector group and sector-specific lens, the "
            "Pakistan macro checklist, peers and the Yahoo listing code."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_psx_context,
    ),
    "get_company_profile": ToolSpec(
        name="get_company_profile",
        description="Return company identity, provenance, peer names and available fiscal years.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_profile,
    ),
}


def openai_tool_schemas(names: list[str]) -> list[dict[str, Any]]:
    schemas = []
    for name in names:
        spec = TOOLS.get(name)
        if spec is None:
            continue
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return schemas


@dataclass
class ToolRunner:
    """Executes tool calls and records an audit trail."""

    context: ToolContext
    allowed: list[str] = field(default_factory=lambda: list(TOOLS))
    records: list[ToolCallRecord] = field(default_factory=list)

    def run(self, name: str, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        started = time.perf_counter()
        if name not in self.allowed:
            error = f"tool {name!r} is not enabled"
            self.records.append(
                ToolCallRecord(
                    tool=name, ok=False, error=error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            return {"ok": False, "error": error}
        spec = TOOLS.get(name)
        if spec is None:
            error = f"unknown tool {name!r}"
            self.records.append(
                ToolCallRecord(
                    tool=name, ok=False, error=error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            return {"ok": False, "error": error}

        parsed = _parse_arguments(arguments)
        if isinstance(parsed, dict) and "__error__" in parsed:
            error = str(parsed["__error__"])
            self.records.append(
                ToolCallRecord(
                    tool=name, ok=False, error=error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            return {"ok": False, "error": error}

        try:
            payload = spec.handler(self.context, parsed)
            ok = True
            error = None
        except Exception as exc:  # tools must never break the run
            payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            ok = False
            error = payload["error"]

        self.records.append(
            ToolCallRecord(
                tool=name,
                ok=ok,
                duration_ms=int((time.perf_counter() - started) * 1000),
                summary=_summarize(name, payload, ok),
                error=error,
            )
        )
        return payload


def _parse_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
    if arguments is None or arguments == "":
        return {}
    if isinstance(arguments, dict):
        return arguments
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        return {"__error__": f"arguments were not valid JSON: {exc}"}
    if not isinstance(parsed, dict):
        return {"__error__": "arguments must be a JSON object"}
    return parsed


def _summarize(name: str, payload: dict[str, Any], ok: bool) -> str:
    if not ok:
        return str(payload.get("error", "failed"))[:180]
    if name == "get_financials":
        years = payload.get("years") or []
        return f"{len(years)} fiscal years returned"
    if name == "get_ratios":
        return f"{len([key for key in payload if not key.startswith('_')])} ratio fields"
    if name == "get_score_breakdown":
        return f"overall {payload.get('overall')} ({payload.get('grade')})"
    if name == "compute_scenario":
        implied = payload.get("implied") or {}
        return f"implied price {implied.get('share_price')}"
    if name == "get_company_profile":
        return "profile returned"
    if name == "get_psx_context":
        return f"PSX context for {payload.get('sector_group') or 'sector n/a'}"
    return "ok"


def build_context(company: CompanyFundamentals) -> ToolContext:
    ratios = compute_ratios(company)
    return ToolContext(company=company, ratios=ratios, scores=score_company(company, ratios))


def describe_tools() -> list[dict[str, Any]]:
    """Human-readable tool catalogue for the API and UI."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        }
        for spec in TOOLS.values()
    ]


__all__ = [
    "TOOLS",
    "ToolContext",
    "ToolRunner",
    "ToolSpec",
    "build_context",
    "describe_tools",
    "openai_tool_schemas",
    "tool_scenario",
]
