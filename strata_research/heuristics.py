"""Rule-based analyst used as a prior, an offline LLM and a safety net.

The same function backs three paths:

* the deterministic draft injected into the LLM prompt,
* the ``DeterministicLLM`` response in offline mode,
* the fallback note when the real endpoint errors out.

It is deliberately boring: verdict from the quality score minus detected red
flags, narrative built from the components that scored best and worst.
"""

from __future__ import annotations

from .compute import compute_ratios
from .formatting import fmt_amount, fmt_pct, fmt_per_share, fmt_x
from .psx import sector_group
from .schemas import AnalystOutput, CompanyFundamentals, QualityScore, RatioSet
from .scoring import score_company
from .tools import ToolContext, build_context, tool_scenario

SEVERE_PILLAR_THRESHOLD = 40.0


def _pillar(scores: QualityScore, key: str) -> float:
    for pillar in scores.pillars:
        if pillar.key == key:
            return pillar.score
    return 0.0


def decide(ratios: RatioSet, scores: QualityScore) -> tuple[str, float, float]:
    """Return ``(verdict, conviction, confidence)`` from deterministic inputs."""
    confidence = max(0.05, min(1.0, 0.2 + 0.7 * scores.coverage))
    if scores.coverage < 0.35 or (ratios.pe is None and ratios.ev_ebitda is None):
        return "INSUFFICIENT_DATA", 0.3, confidence

    effective = scores.overall - 3.0 * len(scores.red_flags)
    severe = (
        (ratios.interest_coverage is not None and ratios.interest_coverage < 2.0)
        or (ratios.net_debt_to_ebitda is not None and ratios.net_debt_to_ebitda > 4.0)
        or (ratios.fcf is not None and ratios.fcf < 0)
    )
    balance = _pillar(scores, "balance_sheet")
    if effective >= 66 and not severe and balance >= 50:
        verdict = "BUY"
    elif effective <= 44 or severe:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    distance = min(1.0, abs(effective - 55.0) / 45.0)
    conviction = round(min(0.9, 0.4 + 0.5 * distance - 0.03 * len(scores.red_flags)), 3)
    return verdict, max(0.2, conviction), round(confidence, 3)


def _valuation_stance(valuation_pillar: float, overall: float) -> str:
    if valuation_pillar >= 60 and overall < 50:
        return (
            "the discount tracks the weak fundamentals, which is value-trap risk "
            "rather than a margin of safety."
        )
    if valuation_pillar >= 60:
        return "the multiple is undemanding relative to the quality of the business."
    if valuation_pillar <= 35:
        return "the multiple already discounts a lot of good news."
    return "the multiple sits mid-range relative to business quality."


def _top_components(scores: QualityScore, count: int = 3) -> list:
    scored = [item for item in scores.components if item.points is not None]
    return sorted(scored, key=lambda item: item.points, reverse=True)[:count]


def _weak_components(scores: QualityScore, count: int = 3) -> list:
    scored = [item for item in scores.components if item.points is not None]
    return sorted(scored, key=lambda item: item.points)[:count]


def _describe(component, lower: bool = False) -> str:
    value = component.value
    if component.unit == "pct":
        rendered = fmt_pct(value)
    elif component.unit == "x":
        rendered = fmt_x(value, 2) if abs(value or 0) < 10 else fmt_x(value)
    else:
        rendered = f"{value:,.2f}" if value is not None else "n/a"
    label = component.label
    if lower and len(label) > 1 and label[1].islower():
        label = label[0].lower() + label[1:]  # keep acronyms like P/E, ROIC intact
    return f"{label} of {rendered}"


def rule_based_analysis(
    company: CompanyFundamentals,
    ratios: RatioSet | None = None,
    scores: QualityScore | None = None,
    focus: str = "balanced fundamental view",
) -> AnalystOutput:
    ratios = ratios or compute_ratios(company)
    scores = scores or score_company(company, ratios)
    profile = company.profile
    currency = profile.currency
    verdict, conviction, confidence = decide(ratios, scores)
    if profile.data_quality == "synthetic":
        confidence = round(max(0.1, confidence * 0.85), 3)

    latest = company.latest
    strongest = _top_components(scores)
    weakest = _weak_components(scores)

    summary = (
        f"{profile.name} ({profile.ticker}) scores {scores.overall:.0f}/100 on the "
        f"PSX fundamental model (grade {scores.grade}, {scores.label}). "
        f"Latest revenue is {fmt_amount(latest.revenue, currency=currency)} with a "
        f"{fmt_pct(ratios.net_margin)} net margin, {fmt_pct(ratios.roic)} ROIC and "
        f"{fmt_x(ratios.ev_ebitda)} EV/EBITDA. "
        + (
            "No red flag was triggered by the rule set."
            if not scores.red_flags
            else f"{len(scores.red_flags)} red flag(s) were detected."
        )
    )

    thesis_bits: list[str] = []
    if strongest:
        joined = " and ".join(_describe(item, lower=True) for item in strongest[:2])
        if verdict == "SELL":
            thesis_bits.append(
                f"The comparatively strong points are {joined}, but they do not offset "
                "the weaknesses below."
            )
        else:
            thesis_bits.append(f"The case rests on {joined}.")
    if ratios.revenue_cagr is not None:
        thesis_bits.append(
            f"Revenue compounded at {fmt_pct(ratios.revenue_cagr)} over "
            f"{ratios.cagr_years or 1} year(s), with EPS CAGR of {fmt_pct(ratios.eps_cagr)}."
        )
    if ratios.fcf is not None:
        thesis_bits.append(
            f"Free cash flow of {fmt_amount(ratios.fcf, currency=currency)} converts "
            f"{fmt_pct(ratios.fcf_conversion)} of net income into cash."
        )
    if ratios.dividend_yield is not None and ratios.dividend_yield > 0:
        thesis_bits.append(
            f"The dividend yield is {fmt_pct(ratios.dividend_yield)}, "
            + (
                "covered by free cash flow."
                if (ratios.fcf_conversion or 0) >= 0.6
                else "but cash conversion is thin."
            )
        )
    if ratios.ev_ebitda is not None or ratios.pe is not None:
        thesis_bits.append(
            f"At the current price the market pays {fmt_x(ratios.pe)} earnings and "
            f"{fmt_x(ratios.ev_ebitda)} EBITDA."
        )
    if weakest:
        thesis_bits.append(
            "The weakest links are "
            + " and ".join(_describe(item, lower=True) for item in weakest[:2])
            + "."
        )
    investment_thesis = " ".join(thesis_bits) or (
        "Evidence is too thin to build a defensible thesis."
    )

    strengths = [
        _describe(item) for item in strongest if (item.points or 0) >= 0.5
    ][:4] or ["No component clears the mid-point of the scoring model."]

    risks = list(scores.red_flags[:4])
    for item in weakest:
        if (item.points or 0) <= 0.45:
            risks.append(f"Soft spot: {_describe(item)}.")
    risks = risks[:5] or ["No material risk flagged by the rule set; still verify with filings."]

    scenario_text = ""
    context = build_context(company)
    scenario = tool_scenario(
        context,
        {
            "revenue_growth": 0.0,
            "net_margin": ratios.net_margin if ratios.net_margin is not None else 0.08,
            "pe_multiple": ratios.pe if ratios.pe and ratios.pe > 0 else 15.0,
        },
    )
    if scenario.get("ok"):
        implied = scenario["implied"]
        scenario_text = (
            f" Holding today's margin and multiple with flat revenue implies "
            f"{fmt_per_share(implied['share_price'], currency)} per share versus "
            f"{fmt_per_share(profile.price, currency)} now "
            f"({fmt_pct(implied['upside_vs_current'], signed=True)})."
        )
    valuation_view = (
        f"P/E {fmt_x(ratios.pe)}, EV/EBITDA {fmt_x(ratios.ev_ebitda)}, P/S {fmt_x(ratios.ps)}, "
        f"FCF yield {fmt_pct(ratios.fcf_yield)}. The valuation pillar scores "
        f"{_pillar(scores, 'valuation'):.0f}/100; "
        + _valuation_stance(_pillar(scores, "valuation"), scores.overall)
        + scenario_text
    )
    growth_view = (
        f"Revenue growth of {fmt_pct(ratios.revenue_growth_yoy, signed=True)} and EPS "
        f"growth of {fmt_pct(ratios.eps_growth_yoy, signed=True)} in the latest year; "
        f"the growth pillar scores {_pillar(scores, 'growth'):.0f}/100. "
        "Treat a single year as noise and check whether the direction holds across the "
        "reported history."
    )
    moat = (
        f"Returns on invested capital of {fmt_pct(ratios.roic)} against a balance-sheet "
        f"pillar score of {_pillar(scores, 'balance_sheet'):.0f}/100 are the best "
        "available proxy for durability in this dataset. The statements cannot prove "
        "pricing power; on PSX that usually needs evidence on market share, capacity "
        "additions and pricing power with regulators, not just margins."
    )

    group = sector_group(profile.sector) or sector_group(profile.industry)
    watch_items = [
        f"Next quarter's revenue growth against the {fmt_pct(ratios.revenue_growth_yoy, signed=True)} trend.",
        f"Gross margin versus the latest {fmt_pct(ratios.gross_margin)} as input costs and the PKR move.",
        f"Interest cover of {fmt_x(ratios.interest_coverage)} under the current SBP policy rate.",
    ]
    if group == "Power Generation":
        watch_items.append("Circular-debt receivable ageing and capacity-payment recovery.")
    elif group == "Cement":
        watch_items.append("Despatch volumes, coal cost per tonne and retention prices.")
    elif group == "Oil & Gas Exploration":
        watch_items.append("Gas price notification, receivables from the gas chain and PKR/USD.")
    elif group == "Fertilizer":
        watch_items.append("Gas allocation/tariff for the sector and urea price notifications.")
    else:
        watch_items.append(
            f"Free cash flow conversion versus {fmt_pct(ratios.fcf_conversion)}."
        )
    watch_items.append(
        f"Net debt / EBITDA of {fmt_x(ratios.net_debt_to_ebitda)} on the next balance sheet."
    )

    return AnalystOutput(
        verdict=verdict,  # type: ignore[arg-type]
        conviction=conviction,
        confidence=confidence,
        summary=summary,
        investment_thesis=investment_thesis,
        strengths=strengths,
        risks=risks,
        valuation_view=valuation_view,
        growth_view=growth_view,
        moat=moat,
        red_flags=list(scores.red_flags),
        watch_items=watch_items,
    )


def context_for(company: CompanyFundamentals) -> ToolContext:
    """Helper used by the API/UI to compute deterministic views once."""
    return build_context(company)
