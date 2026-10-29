"""Text and Markdown rendering for reports (CLI output and exports)."""

from __future__ import annotations

from .compute import ratio_lines
from .formatting import fmt_money, fmt_pct, fmt_score, fmt_x
from .schemas import FundamentalReport, TeamBrief


def _wrap(text: str, width: int = 96, indent: str = "") -> str:
    import textwrap

    return textwrap.fill(
        text, width=width, initial_indent=indent, subsequent_indent=indent
    )


def ratio_table_markdown(report: FundamentalReport) -> str:
    currency = report.profile.currency
    rows = ratio_lines(report.ratios, currency=currency)
    lines = ["| Metric | Value |", "|---|---:|"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    return "\n".join(lines)


def score_table_markdown(report: FundamentalReport) -> str:
    lines = ["| Pillar | Score | Inputs |", "|---|---:|---|"]
    for pillar in report.scores.pillars:
        lines.append(
            f"| {pillar.label} | {pillar.score:.0f}/100 | "
            f"{pillar.covered}/{pillar.total} |"
        )
    return "\n".join(lines)


def report_to_markdown(report: FundamentalReport) -> str:
    analysis = report.analysis
    profile = report.profile
    lines: list[str] = []
    lines.append(f"# {profile.name} ({profile.ticker}) — Fundamental Research Note")
    lines.append("")
    lines.append(
        f"**Verdict:** {analysis.verdict} · **Conviction:** {analysis.conviction:.2f} · "
        f"**Data confidence:** {analysis.confidence:.2f} · "
        f"**Quality score:** {fmt_score(report.scores.overall)} ({report.scores.grade})"
    )
    lines.append("")
    lines.append(
        f"*Sector:* {profile.sector or 'n/a'} · *Industry:* {profile.industry or 'n/a'} · "
        f"*Currency:* {profile.currency} · *As of:* {profile.as_of}"
    )
    lines.append("")
    lines.append(
        f"*Generated:* {report.generated_at.isoformat(timespec='seconds')} · "
        f"*Mode:* {report.mode} · *Model:* {report.model} · "
        f"*Runtime:* {report.duration_ms / 1000:.1f}s"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(analysis.summary or "n/a")
    lines.append("")
    lines.append("## Investment thesis")
    lines.append("")
    lines.append(analysis.investment_thesis or "n/a")
    lines.append("")
    if analysis.strengths:
        lines.append("## Strengths")
        lines.append("")
        lines.extend(f"- {item}" for item in analysis.strengths)
        lines.append("")
    if analysis.risks:
        lines.append("## Risks")
        lines.append("")
        lines.extend(f"- {item}" for item in analysis.risks)
        lines.append("")
    lines.append("## Valuation view")
    lines.append("")
    lines.append(analysis.valuation_view or "n/a")
    lines.append("")
    lines.append("## Growth view")
    lines.append("")
    lines.append(analysis.growth_view or "n/a")
    lines.append("")
    lines.append("## Moat / durability")
    lines.append("")
    lines.append(analysis.moat or "n/a")
    lines.append("")
    if analysis.red_flags:
        lines.append("## Red flags")
        lines.append("")
        lines.extend(f"- {item}" for item in analysis.red_flags)
        lines.append("")
    if analysis.watch_items:
        lines.append("## Watch list")
        lines.append("")
        lines.extend(f"- {item}" for item in analysis.watch_items)
        lines.append("")
    lines.append("## Deterministic ratios")
    lines.append("")
    lines.append(ratio_table_markdown(report))
    lines.append("")
    lines.append("## Quality score breakdown")
    lines.append("")
    lines.append(score_table_markdown(report))
    lines.append("")
    lines.append("## Provenance and audit")
    lines.append("")
    lines.append(f"- Data source: {profile.data_source} ({profile.data_quality})")
    lines.append(
        f"- Provider notes: {' '.join(profile.notes) if profile.notes else 'none'}"
    )
    lines.append(
        f"- LLM calls: {report.request.get('llm_calls', 0)} · "
        f"Tools offered: {', '.join(report.request.get('tools_available', [])) or 'none'}"
    )
    if report.tool_calls:
        for call in report.tool_calls:
            state = "ok" if call.ok else "failed"
            lines.append(f"- Tool `{call.tool}` ({state}, {call.duration_ms}ms): {call.summary}")
    else:
        lines.append("- Tool calls: none (evidence pack was sufficient)")
    lines.append(
        "- Grounding: "
        + (
            "all narrative figures matched the deterministic evidence set"
            if report.grounding.grounded
            else "unverified figures: " + ", ".join(report.grounding.unverified)
        )
        + f" ({report.grounding.checked} numbers checked)"
    )
    if report.usage:
        lines.append(f"- Token usage: {report.usage}")
    if report.warnings:
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    lines.append("")
    lines.append(f"> {report.disclaimer}")
    return "\n".join(lines).rstrip() + "\n"


def brief_to_markdown(brief: TeamBrief) -> str:
    lines = [f"# Desk brief — {brief.ticker}", ""]
    lines.append(f"**Headline:** {brief.headline}")
    lines.append("")
    lines.append(f"*Focus:* {brief.focus} · *Horizon:* {brief.horizon} · "
                 f"*Runtime:* {brief.duration_ms / 1000:.1f}s")
    lines.append("")
    lines.append("## Agent coverage")
    lines.append("")
    lines.append("| Agent | Status | Verdict | Conviction | Quality | Mode |")
    lines.append("|---|---|---|---:|---:|---|")
    for entry in brief.coverage:
        lines.append(
            f"| {entry.get('title') or entry.get('agent')} | {entry.get('status')} | "
            f"{entry.get('verdict', 'n/a')} | {entry.get('conviction', 0):.2f} | "
            f"{entry.get('quality_score', 0):.0f} | {entry.get('mode', 'n/a')} |"
        )
    lines.append("")
    if brief.roadmap:
        lines.append("## Not yet available")
        lines.append("")
        for item in brief.roadmap:
            lines.append(f"- {item.get('title')}: {item.get('reason')}")
        lines.append("")
    for report in brief.reports:
        lines.append("---")
        lines.append("")
        lines.append(report_to_markdown(report))
    lines.append(f"> {brief.disclaimer}")
    return "\n".join(lines).rstrip() + "\n"


def report_to_console(report: FundamentalReport) -> str:
    analysis = report.analysis
    profile = report.profile
    currency = profile.currency
    line = "─" * 78
    blocks: list[str] = [
        line,
        f"{profile.name} ({profile.ticker})  ·  {profile.sector or 'n/a'}",
        f"Verdict: {analysis.verdict}   Conviction: {analysis.conviction:.2f}   "
        f"Confidence: {analysis.confidence:.2f}",
        f"Quality: {fmt_score(report.scores.overall)} ({report.scores.grade} · "
        f"{report.scores.label})   Red flags: {len(report.scores.red_flags)}",
        f"Mode: {report.mode}   Model: {report.model}   "
        f"Runtime: {report.duration_ms / 1000:.1f}s",
        line,
        _wrap(analysis.summary),
        "",
        _wrap(analysis.investment_thesis),
        "",
        "Key metrics",
        f"  P/E {fmt_x(report.ratios.pe)}   EV/EBITDA {fmt_x(report.ratios.ev_ebitda)}   "
        f"FCF yield {fmt_pct(report.ratios.fcf_yield)}",
        f"  ROIC {fmt_pct(report.ratios.roic)}   Net margin "
        f"{fmt_pct(report.ratios.net_margin)}   "
        f"Net debt/EBITDA {fmt_x(report.ratios.net_debt_to_ebitda)}",
        f"  Revenue CAGR {fmt_pct(report.ratios.revenue_cagr)}   "
        f"FCF {fmt_money(report.ratios.fcf, currency=currency)}",
    ]
    if report.scores.red_flags:
        blocks.append("")
        blocks.append("Red flags")
        blocks.extend(f"  ! {flag}" for flag in report.scores.red_flags)
    if analysis.risks:
        blocks.append("")
        blocks.append("Risks")
        blocks.extend(f"  - {_wrap(risk, indent='    ').strip()}" for risk in analysis.risks)
    blocks.append("")
    blocks.append(
        f"Grounding: {report.grounding.checked} figures checked · "
        + ("all verified" if report.grounding.grounded else
           "unverified: " + ", ".join(report.grounding.unverified))
    )
    if report.warnings:
        blocks.append("Warnings:")
        blocks.extend(f"  ! {warning}" for warning in report.warnings)
    blocks.append(line)
    blocks.append(report.disclaimer)
    return "\n".join(blocks)
