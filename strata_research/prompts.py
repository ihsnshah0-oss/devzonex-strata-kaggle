"""Prompt construction for the Fundamental Analyst.

The prompt is built from three blocks:

1. a short company header (identity, data provenance, quality),
2. an evidence pack rendered straight from the deterministic models,
3. an instruction block with the exact JSON contract.

Keeping the evidence pack generated (not free-text) is what allows the
grounding validator to verify the model's numbers later.
"""

from __future__ import annotations

import json
from typing import Any

from .compute import compute_ratios, margin_trend, ratio_lines
from .formatting import fmt_money, fmt_num, fmt_pct, fmt_per_share
from .schemas import CompanyFundamentals, QualityScore, RatioSet

DRAFT_MARKER_START = "<<<DETERMINISTIC_DRAFT"
DRAFT_MARKER_END = "DETERMINISTIC_DRAFT>>>"

ANALYST_SYSTEM_PROMPT = """You are the Fundamental Analyst on a disciplined equity research desk.

Operating rules:
- You are evidence-driven. Every quantitative claim must come from the supplied
  evidence pack or from a tool you actually called. Never invent, extrapolate or
  recall outside numbers. If a metric is marked n/a, treat it as unknown.
- Separate fact from interpretation. State what the numbers show, then why it matters.
- Be specific: reference margins, returns, leverage, cash conversion and valuation
  multiples instead of generic praise or criticism.
- You write for a professional but time-poor reader. Dense, plain language. No hype,
  no emoji, no bullet-point padding, no disclaimers beyond the required fields.
- Never present the output as investment advice and never predict a price target as
  fact; scenario maths belongs in the valuation view and must be labelled an
  assumption.
- If the evidence is too thin to reach a defensible conclusion (coverage < 40% or
  no valuation inputs), return verdict "INSUFFICIENT_DATA" and explain what is
  missing in watch_items.
- Output valid JSON only, matching the requested schema exactly. No markdown fences.
"""

OUTPUT_SCHEMA = {
    "verdict": "BUY | HOLD | SELL | INSUFFICIENT_DATA",
    "conviction": "float 0..1 - how strongly the evidence supports the verdict",
    "confidence": "float 0..1 - how complete/reliable the underlying evidence is",
    "summary": "string, 2-3 sentences, the single most important takeaway",
    "investment_thesis": "string, 120-220 words, causal argument not a list",
    "strengths": ["3-5 short strings, each anchored to a number"],
    "risks": ["2-5 short strings, each anchored to a number or an explicit unknown"],
    "valuation_view": "string, 60-140 words, what the multiples imply and one explicit scenario",
    "growth_view": "string, 40-100 words on revenue/EPS trajectory and its quality",
    "moat": "string, 30-80 words on durability of returns; say if evidence is insufficient",
    "red_flags": ["short strings - only flags supported by the evidence pack"],
    "watch_items": ["2-5 falsifiable things to monitor next"],
}


def _statement_rows() -> list[tuple[str, str]]:
    return [
        ("Revenue", "revenue"),
        ("Gross profit", "gross_profit"),
        ("Operating income", "operating_income"),
        ("Pretax income", "pretax_income"),
        ("Net income", "net_income"),
        ("Diluted EPS", "eps"),
        ("Operating cash flow", "operating_cash_flow"),
        ("Capex", "capex"),
        ("Total assets", "total_assets"),
        ("Total equity", "total_equity"),
        ("Total debt", "total_debt"),
        ("Cash & equivalents", "cash_and_equivalents"),
        ("Current assets", "current_assets"),
        ("Current liabilities", "current_liabilities"),
        ("Inventory", "inventory"),
        ("D&A", "depreciation_amortization"),
        ("Interest expense", "interest_expense"),
    ]


def financial_table(company: CompanyFundamentals) -> str:
    currency = company.profile.currency
    years = sorted(company.fiscal_years, key=lambda year: year.fiscal_year)
    header = "| Metric (millions " + currency + ") | " + " | ".join(
        f"FY{year.fiscal_year}" for year in years
    ) + " |"
    divider = "|" + "---|" * (len(years) + 1)
    lines = [header, divider]
    for label, attribute in _statement_rows():
        cells = []
        for year in years:
            value = getattr(year, attribute, None)
            if attribute == "eps":
                cells.append(fmt_per_share(value, currency))
            else:
                cells.append(fmt_money(value, digits=2))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def evidence_pack(
    company: CompanyFundamentals,
    ratios: RatioSet | None = None,
    scores: QualityScore | None = None,
) -> str:
    from .scoring import score_company

    ratios = ratios or compute_ratios(company)
    scores = scores or score_company(company, ratios)
    profile = company.profile

    lines: list[str] = []
    lines.append("## Company")
    lines.append(f"Name: {profile.name}")
    lines.append(f"Ticker: {profile.ticker}  Currency: {profile.currency}")
    lines.append(
        f"Sector: {profile.sector or 'n/a'}  Industry: {profile.industry or 'n/a'}  "
        f"Country: {profile.country or 'n/a'}"
    )
    lines.append(
        f"Share price: {fmt_per_share(profile.price, profile.currency)}  "
        f"Diluted shares: {fmt_num(profile.shares_outstanding, 1)}M  "
        f"Dividend/share: {fmt_per_share(profile.dividend_per_share, profile.currency)}  "
        f"Beta: {fmt_num(profile.beta, 2)}"
    )
    lines.append(
        f"Data source: {profile.data_source}  Data quality: {profile.data_quality}  "
        f"As of: {profile.as_of}"
    )
    if profile.description:
        lines.append(f"Business description: {profile.description}")
    if company.peers:
        lines.append("Peer references (names only, no peer financials were fetched): "
                     + ", ".join(company.peers))

    lines.append("")
    lines.append(
        f"## Annual statements (millions {profile.currency} unless per-share)"
    )
    lines.append(financial_table(company))

    lines.append("")
    lines.append("## Computed ratios (deterministic)")
    for label, value in ratio_lines(ratios, currency=profile.currency):
        lines.append(f"- {label}: {value}")
    if ratios.notes:
        lines.append("Ratio notes: " + " ".join(ratios.notes))

    lines.append("")
    lines.append("## Deterministic quality score (rule-based, not the LLM)")
    lines.append(
        f"Overall: {scores.overall:.1f}/100 (grade {scores.grade} - {scores.label}); "
        f"component coverage {scores.coverage * 100:.0f}%."
    )
    for pillar in scores.pillars:
        lines.append(
            f"- {pillar.label}: {pillar.score:.1f}/100 "
            f"({pillar.covered}/{pillar.total} inputs)"
        )
    if scores.red_flags:
        lines.append("Detected red flags:")
        for flag in scores.red_flags:
            lines.append(f"- {flag}")
    else:
        lines.append("Detected red flags: none triggered by the rule set.")

    gross = margin_trend(company, "gross")
    operating = margin_trend(company, "operating")
    net = margin_trend(company, "net")
    ordered = sorted(company.fiscal_years, key=lambda year: year.fiscal_year)
    labels = [f"FY{year.fiscal_year}" for year in ordered]
    lines.append("")
    lines.append("## Margin trend (oldest to newest)")
    lines.append(f"Years: {', '.join(labels)}")
    lines.append("Gross: " + ", ".join(fmt_pct(value) for value in gross))
    lines.append("Operating: " + ", ".join(fmt_pct(value) for value in operating))
    lines.append("Net: " + ", ".join(fmt_pct(value) for value in net))
    return "\n".join(lines)


def build_analyst_prompt(
    company: CompanyFundamentals,
    ratios: RatioSet,
    scores: QualityScore,
    *,
    focus: str,
    horizon: str,
    tool_names: list[str],
    deterministic_draft: dict[str, Any] | None = None,
) -> str:
    tools_line = (
        "You may call these tools before answering: " + ", ".join(tool_names) + "."
        if tool_names
        else "No tools are enabled; rely on the evidence pack."
    )
    payload = {
        "focus": focus,
        "horizon": horizon,
        "task": (
            "Write the fundamental research note for this company. Use the evidence "
            "pack as the sole source of quantitative facts."
        ),
        "output_schema": OUTPUT_SCHEMA,
    }
    sections = [
        "## Request",
        json.dumps(payload, indent=2),
        "",
        tools_line,
        "",
        evidence_pack(company, ratios, scores),
        "",
        "## Output",
        "Return ONE JSON object matching output_schema. "
        "conviction must reflect evidence strength, confidence must reflect data "
        "completeness. Do not add extra top-level keys.",
    ]
    if deterministic_draft is not None:
        sections.extend(
            [
                "",
                DRAFT_MARKER_START,
                json.dumps(deterministic_draft, indent=2),
                DRAFT_MARKER_END,
                "(A rule-based draft is included above for reference only.)",
            ]
        )
    return "\n".join(sections)


def build_repair_prompt(error: str, previous: str) -> str:
    trimmed = previous.strip()
    if len(trimmed) > 3500:
        trimmed = trimmed[:3500] + "…"
    return (
        "Your previous response could not be accepted.\n"
        f"Reason: {error}\n\n"
        "Previous response (truncated):\n"
        f"{trimmed}\n\n"
        "Return ONLY a corrected JSON object that satisfies output_schema. "
        "Same evidence, no new numbers, no commentary."
    )


def build_team_brief_prompt(
    ticker: str,
    focus: str,
    horizon: str,
    reports: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "## Desk briefing request",
            json.dumps(
                {
                    "ticker": ticker,
                    "focus": focus,
                    "horizon": horizon,
                    "available_analyst_reports": reports,
                    "planned_specialists": roadmap,
                },
                indent=2,
            ),
            "",
            "Summarize what the desk can honestly say today, what the fundamental "
            "report establishes, and which specialist is needed next. 150 words max.",
        ]
    )
