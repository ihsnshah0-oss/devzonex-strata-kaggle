"""Deterministic fundamental quality score, calibrated for PSX.

The score is a *prior*: it is computed before the LLM runs and handed to the model
so its narrative starts from consistent, auditable numbers. It is also what the
desk falls back to when no LLM is reachable.

Anchors are **market-aware**. PSX companies trade on much lower multiples and
carry much higher nominal growth than developed markets, so a global multiple
scale would call almost every Pakistani company "cheap". The ``PSX`` profile
uses local anchors (P/E 18x -> 4x, EV/EBITDA 12x -> 3.5x, FCF yield 2% -> 15%,
dividend yield 0% -> 10%) and adds a yield component, because income matters to
PSX investors. Unknown inputs are dropped and weights renormalised, so missing
data lowers *coverage* instead of silently scoring zero.
"""

from __future__ import annotations

from .compute import compute_ratios
from .formatting import grade_for
from .psx import sector_group
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
    "valuation": ("Valuation & yield", 0.10),
}

#: key -> (pillar, weight, unit)
COMPONENTS: dict[str, tuple[str, float, str]] = {
    "gross_margin": ("profitability", 0.18, "pct"),
    "operating_margin": ("profitability", 0.22, "pct"),
    "net_margin": ("profitability", 0.15, "pct"),
    "roe": ("profitability", 0.20, "pct"),
    "roic": ("profitability", 0.25, "pct"),
    "revenue_growth_yoy": ("growth", 0.20, "pct"),
    "eps_growth_yoy": ("growth", 0.20, "pct"),
    "revenue_cagr": ("growth", 0.30, "pct"),
    "eps_cagr": ("growth", 0.30, "pct"),
    "net_debt_to_ebitda": ("balance_sheet", 0.35, "x"),
    "interest_coverage": ("balance_sheet", 0.30, "x"),
    "current_ratio": ("balance_sheet", 0.15, "x"),
    "debt_to_equity": ("balance_sheet", 0.20, "x"),
    "fcf_margin": ("cash_quality", 0.35, "pct"),
    "fcf_conversion": ("cash_quality", 0.35, "pct"),
    "fcf_yield": ("cash_quality", 0.30, "pct"),
    "pe": ("valuation", 0.30, "x"),
    "ev_ebitda": ("valuation", 0.25, "x"),
    "ps": ("valuation", 0.15, "x"),
    "dividend_yield": ("valuation", 0.20, "pct"),
}

#: key -> (unattractive anchor, attractive anchor)
PSX_ANCHORS: dict[str, tuple[float, float]] = {
    "gross_margin": (0.05, 0.45),
    "operating_margin": (0.02, 0.30),
    "net_margin": (0.01, 0.18),
    "roe": (0.02, 0.30),
    "roic": (0.02, 0.25),
    "revenue_growth_yoy": (-0.05, 0.30),
    "eps_growth_yoy": (-0.15, 0.35),
    "revenue_cagr": (0.00, 0.25),
    "eps_cagr": (-0.05, 0.30),
    "net_debt_to_ebitda": (3.0, 0.0),
    "interest_coverage": (1.0, 8.0),
    "current_ratio": (0.8, 1.8),
    "debt_to_equity": (2.0, 0.30),
    "fcf_margin": (0.00, 0.15),
    "fcf_conversion": (0.30, 1.00),
    "fcf_yield": (0.02, 0.15),
    "pe": (18.0, 4.0),
    "ev_ebitda": (12.0, 3.5),
    "ps": (4.0, 0.50),
    "dividend_yield": (0.00, 0.10),
}

#: Development-market anchors, used only for non-PSX statements.
GLOBAL_ANCHORS: dict[str, tuple[float, float]] = {
    "gross_margin": (0.15, 0.60),
    "operating_margin": (0.00, 0.25),
    "net_margin": (0.00, 0.20),
    "roe": (0.00, 0.25),
    "roic": (0.00, 0.20),
    "revenue_growth_yoy": (-0.10, 0.20),
    "eps_growth_yoy": (-0.20, 0.25),
    "revenue_cagr": (-0.05, 0.18),
    "eps_cagr": (-0.10, 0.22),
    "net_debt_to_ebitda": (4.0, 0.0),
    "interest_coverage": (1.5, 10.0),
    "current_ratio": (0.8, 2.0),
    "debt_to_equity": (2.0, 0.30),
    "fcf_margin": (0.00, 0.20),
    "fcf_conversion": (0.30, 1.20),
    "fcf_yield": (0.00, 0.08),
    "pe": (45.0, 12.0),
    "ev_ebitda": (25.0, 8.0),
    "ps": (12.0, 1.5),
    "dividend_yield": (0.00, 0.04),
}

ANCHOR_PROFILES = {"PSX": PSX_ANCHORS, "GLOBAL": GLOBAL_ANCHORS}

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
    "dividend_yield": "Dividend yield",
}

#: PSX sectors whose reported numbers need a different lens.
FINANCIAL_SECTORS = {"Commercial Banks"}


def anchor_profile_for(market: str | None) -> str:
    return "PSX" if (market or "PSX").upper() == "PSX" else "GLOBAL"


def normalize(value: float, unattractive: float, attractive: float) -> float:
    """Linear map of ``value`` onto 0..1 between two semantic anchors."""
    if attractive == unattractive:
        return 0.5
    score = (value - unattractive) / (attractive - unattractive)
    return min(1.0, max(0.0, score))


def _component_note(value: float | None, unattractive: float, attractive: float) -> str:
    if value is None:
        return "Not computable from available data."
    best = max(unattractive, attractive)
    worst = min(unattractive, attractive)
    if value >= best:
        return "At least as good as the attractive anchor."
    if value <= worst:
        return "At or beyond the unattractive anchor."
    return "Between the two anchors."


def score_company(
    company: CompanyFundamentals, ratios: RatioSet | None = None
) -> QualityScore:
    ratios = ratios or compute_ratios(company)
    profile_name = anchor_profile_for(company.profile.market)
    anchors = ANCHOR_PROFILES[profile_name]

    components: list[ScoreComponent] = []
    for key, (pillar, weight, unit) in COMPONENTS.items():
        value = getattr(ratios, key, None)
        unattractive, attractive = anchors[key]
        points = None if value is None else normalize(value, unattractive, attractive)
        components.append(
            ScoreComponent(
                key=key,
                label=LABELS[key],
                pillar=pillar,
                value=value,
                unit=unit,  # type: ignore[arg-type]
                weight=weight,
                points=None if points is None else round(points, 4),
                note=_component_note(value, unattractive, attractive),
            )
        )

    pillars: list[PillarScore] = []
    weighted_total = 0.0
    weight_denominator = 0.0
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
    covered_components = sum(1 for item in components if item.points is not None)
    return QualityScore(
        overall=round(overall, 2),
        grade=grade,
        label=label,
        anchor_profile=profile_name,
        pillars=pillars,
        components=components,
        red_flags=detect_red_flags(company, ratios),
        coverage=round(covered_components / len(components) if components else 0.0, 4),
    )


def detect_red_flags(company: CompanyFundamentals, ratios: RatioSet) -> list[str]:
    flags: list[str] = []
    years = company.fiscal_years
    latest = years[0]
    prior = years[1] if len(years) > 1 else None
    group = sector_group(company.profile.sector) or sector_group(company.profile.industry)

    if ratios.net_margin is not None and ratios.net_margin < 0.03:
        flags.append(f"Thin net margin ({ratios.net_margin * 100:.1f}%).")
    if ratios.interest_coverage is not None and ratios.interest_coverage < 2.5:
        flags.append(
            f"Interest coverage only {ratios.interest_coverage:.1f}x; earnings barely "
            "cover the cost of debt at current policy rates."
        )
    if (
        latest.interest_expense is not None
        and latest.revenue
        and latest.interest_expense / latest.revenue > 0.08
    ):
        flags.append(
            f"Interest cost is {latest.interest_expense / latest.revenue * 100:.1f}% of "
            "revenue; SBP policy-rate moves flow straight into earnings."
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
    if (
        ratios.payout_ratio is not None
        and ratios.fcf is not None
        and company.profile.dividend_per_share
        and company.profile.shares_outstanding
        and company.profile.dividend_per_share * company.profile.shares_outstanding > ratios.fcf > 0
    ):
        flags.append("Dividend is not covered by free cash flow.")
    if ratios.revenue_growth_yoy is not None and ratios.revenue_growth_yoy < 0:
        flags.append(
            f"Revenue declined {abs(ratios.revenue_growth_yoy) * 100:.1f}% year over year."
        )
    if ratios.pe is not None and ratios.pe > 25:
        growth = ratios.eps_growth_yoy or 0.0
        if growth < 0.15:
            flags.append(
                f"Multiple of {ratios.pe:.0f}x earnings with only {growth * 100:.0f}% EPS growth "
                "is expensive for a PSX listing."
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
    if ratios.gross_margin_change is not None and ratios.gross_margin_change < -0.03:
        flags.append(
            f"Gross margin compressed {abs(ratios.gross_margin_change) * 100:.1f} pts "
            "over the period."
        )

    # --- PSX market-structure flags -----------------------------------
    if group == "Power Generation":
        flags.append(
            "IPP earnings depend on capacity payments and circular-debt recoveries; "
            "receivable ageing is not visible in these statements."
        )
    if group in FINANCIAL_SECTORS:
        flags.append(
            "Financial-sector statements need a bank model (NIM, provisioning, ADR, CAR); "
            "industrial ratios understate the risks here."
        )
    return flags
