"""Deterministic fundamental quality score.

The score is a *prior*: it is computed before the LLM runs and handed to the
model so its narrative starts from consistent, auditable numbers. It is also
what the desk falls back to when no LLM is reachable.

Each component maps a ratio onto 0..1 with a piece-wise linear ramp between an
"unattractive" and an "attractive" anchor. Missing inputs are dropped and the
pillar weights are renormalized, so absent data lowers *coverage* instead of
silently scoring zero.
"""

from __future__ import annotations

from .compute import compute_ratios, margin_trend
from .formatting import grade_for
from .schemas import (
    CompanyFundamentals,
    PillarScore,
    QualityScore,
    RatioSet,
    ScoreComponent,
)

PILLARS: dict[str, tuple[str, float]] = {
    "profitability": ("Profitability & returns", 0.30),
    "growth": ("Growth", 0.20),
    "balance_sheet": ("Balance sheet", 0.20),
    "cash_quality": ("Cash generation", 0.20),
    "valuation": ("Valuation", 0.10),
}

# key -> (pillar, weight, unit, unattractive anchor, attractive anchor)
# Anchors are *semantic*: the first value earns 0 points, the second earns 1, and
# the ramp works in either direction (so 4.0x leverage -> 0 and 0.0x -> 1).
COMPONENTS: dict[str, tuple[str, float, str, float, float]] = {
    "gross_margin": ("profitability", 0.18, "pct", 0.15, 0.60),
    "operating_margin": ("profitability", 0.22, "pct", 0.00, 0.25),
    "net_margin": ("profitability", 0.15, "pct", 0.00, 0.20),
    "roe": ("profitability", 0.20, "pct", 0.00, 0.25),
    "roic": ("profitability", 0.25, "pct", 0.00, 0.20),
    "revenue_growth_yoy": ("growth", 0.20, "pct", -0.10, 0.20),
    "eps_growth_yoy": ("growth", 0.20, "pct", -0.20, 0.25),
    "revenue_cagr": ("growth", 0.30, "pct", -0.05, 0.18),
    "eps_cagr": ("growth", 0.30, "pct", -0.10, 0.22),
    "net_debt_to_ebitda": ("balance_sheet", 0.35, "x", 4.0, 0.0),
    "interest_coverage": ("balance_sheet", 0.30, "x", 1.5, 10.0),
    "current_ratio": ("balance_sheet", 0.15, "x", 0.8, 2.0),
    "debt_to_equity": ("balance_sheet", 0.20, "x", 2.0, 0.30),
    "fcf_margin": ("cash_quality", 0.35, "pct", 0.00, 0.20),
    "fcf_conversion": ("cash_quality", 0.35, "pct", 0.30, 1.20),
    "fcf_yield": ("cash_quality", 0.30, "pct", 0.00, 0.08),
    "pe": ("valuation", 0.30, "x", 45.0, 12.0),
    "ev_ebitda": ("valuation", 0.25, "x", 25.0, 8.0),
    "ps": ("valuation", 0.15, "x", 12.0, 1.5),
}

LABELS = {
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "net_margin": "Net margin",
    "roe": "Return on equity",
    "roic": "Return on invested capital",
    "revenue_growth_yoy": "Revenue growth (YoY)",
    "eps_growth_yoy": "EPS growth (YoY)",
    "revenue_cagr": "Revenue CAGR",
    "eps_cagr": "EPS CAGR",
    "net_debt_to_ebitda": "Net debt / EBITDA",
    "interest_coverage": "Interest coverage",
    "current_ratio": "Current ratio",
    "debt_to_equity": "Debt / equity",
    "fcf_margin": "FCF margin",
    "fcf_conversion": "FCF conversion",
    "fcf_yield": "FCF yield",
    "pe": "P/E",
    "ev_ebitda": "EV/EBITDA",
    "ps": "P/S",
}


def normalize(value: float, unattractive: float, attractive: float) -> float:
    """Linear map of ``value`` onto 0..1 between two semantic anchors."""
    if attractive == unattractive:
        return 0.5
    score = (value - unattractive) / (attractive - unattractive)
    return min(1.0, max(0.0, score))


def _answers(ratios: RatioSet, key: str) -> float | None:
    return getattr(ratios, key, None)


def score_company(
    company: CompanyFundamentals, ratios: RatioSet | None = None
) -> QualityScore:
    ratios = ratios or compute_ratios(company)
    components: list[ScoreComponent] = []
    for key, (pillar, weight, unit, unattractive, attractive) in COMPONENTS.items():
        value = _answers(ratios, key)
        points = (
            None
            if value is None
            else normalize(value, unattractive, attractive)
        )
        components.append(
            ScoreComponent(
                key=key,
                label=LABELS[key],
                pillar=pillar,
                value=value,
                unit=unit,  # type: ignore[arg-type]
                weight=weight,
                points=None if points is None else round(points, 4),
                note=_component_note(key, value, unattractive, attractive),
            )
        )

    pillars: list[PillarScore] = []
    weighted_total = 0.0
    weight_denominator = 0.0
    total_components = len(components)
    covered_components = sum(1 for item in components if item.points is not None)
    for pillar_key, (label, pillar_weight) in PILLARS.items():
        members = [item for item in components if item.pillar == pillar_key]
        covered = [item for item in members if item.points is not None]
        if covered:
            member_weight = sum(item.weight for item in covered) or 1.0
            pillar_score = sum(item.points * item.weight for item in covered) / member_weight
            coverage = len(covered) / len(members) if members else 0.0
        else:
            pillar_score = 0.0
            coverage = 0.0
        pillars.append(
            PillarScore(
                key=pillar_key,
                label=label,
                weight=pillar_weight,
                score=round(pillar_score * 100, 2),
                covered=len(covered),
                total=len(members),
            )
        )
        if coverage:
            effective = pillar_weight * coverage
            weighted_total += pillar_score * effective
            weight_denominator += effective

    overall = (weighted_total / weight_denominator * 100.0) if weight_denominator else 0.0
    grade, label = grade_for(overall)
    coverage_ratio = covered_components / total_components if total_components else 0.0
    return QualityScore(
        overall=round(overall, 2),
        grade=grade,
        label=label,
        pillars=pillars,
        components=components,
        red_flags=detect_red_flags(company, ratios),
        coverage=round(coverage_ratio, 4),
    )


def _component_note(
    key: str, value: float | None, unattractive: float, attractive: float
) -> str:
    if value is None:
        return "Not computable from available data."
    best = max(unattractive, attractive)
    worst = min(unattractive, attractive)
    if value >= best:
        return "At least as good as the attractive anchor."
    if value <= worst:
        return "At or beyond the unattractive anchor."
    return "Between the two anchors."


def detect_red_flags(company: CompanyFundamentals, ratios: RatioSet) -> list[str]:
    flags: list[str] = []
    years = company.fiscal_years
    latest = years[0]
    prior = years[1] if len(years) > 1 else None

    if ratios.net_margin is not None and ratios.net_margin < 0.03:
        flags.append(f"Thin net margin ({ratios.net_margin * 100:.1f}%).")
    if ratios.interest_coverage is not None and ratios.interest_coverage < 2.5:
        flags.append(
            f"Interest coverage only {ratios.interest_coverage:.1f}x; earnings barely "
            "cover the cost of debt."
        )
    if ratios.net_debt_to_ebitda is not None and ratios.net_debt_to_ebitda > 3.5:
        flags.append(f"Leverage elevated at {ratios.net_debt_to_ebitda:.1f}x net debt/EBITDA.")
    if ratios.current_ratio is not None and ratios.current_ratio < 1.0:
        flags.append(f"Current ratio below 1.0 ({ratios.current_ratio:.2f}x).")
    if ratios.fcf is not None and ratios.fcf < 0:
        flags.append("Free cash flow is negative in the latest fiscal year.")
    if (
        ratios.fcf_conversion is not None
        and ratios.fcf_conversion < 0.5
        and (ratios.net_margin or 0) > 0
    ):
        flags.append(
            f"Cash conversion weak ({ratios.fcf_conversion * 100:.0f}% of net income becomes FCF)."
        )
    if ratios.payout_ratio is not None and ratios.payout_ratio > 1.0:
        flags.append(f"Dividend payout exceeds earnings ({ratios.payout_ratio * 100:.0f}%).")
    if ratios.revenue_growth_yoy is not None and ratios.revenue_growth_yoy < 0:
        flags.append(
            f"Revenue declined {abs(ratios.revenue_growth_yoy) * 100:.1f}% year over year."
        )
    if ratios.pe is not None and ratios.pe > 40:
        growth = ratios.eps_growth_yoy or 0.0
        if growth < 0.15:
            flags.append(
                f"Multiple of {ratios.pe:.0f}x earnings with only {growth * 100:.0f}% EPS growth."
            )
    if prior is not None and latest.total_equity is not None and prior.total_equity is not None:
        if latest.total_equity < prior.total_equity:
            flags.append("Shareholders' equity fell versus the prior year.")
    if (
        latest.inventory is not None
        and prior is not None
        and prior.inventory
        and latest.revenue is not None
        and prior.revenue
    ):
        inventory_growth = latest.inventory / prior.inventory - 1
        revenue_growth = latest.revenue / prior.revenue - 1
        if inventory_growth > revenue_growth + 0.15:
            flags.append(
                f"Inventory grew {inventory_growth * 100:.0f}% against revenue growth of "
                f"{revenue_growth * 100:.0f}%."
            )
    gross = [value for value in margin_trend(company, "gross") if value is not None]
    if len(gross) >= 2 and gross[0] - gross[-1] > 0.03:
        flags.append(
            f"Gross margin compressed {abs(gross[0] - gross[-1]) * 100:.1f} pts over the period."
        )
    return flags
