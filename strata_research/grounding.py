"""Numeric grounding check.

LLMs hallucinate digits. This module extracts the numbers from the analyst's
narrative and verifies each one against the deterministic evidence set. It is a
heuristic, not a proof: years, small counts and ordinal words are skipped, and
percentages are accepted in both fraction and scaled form.
"""

from __future__ import annotations

import re
from typing import Iterable

from .schemas import (
    CompanyFundamentals,
    FundamentalReport,
    GroundingReport,
    QualityScore,
    RatioSet,
)

NUMBER_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
REL_TOLERANCE = 0.005
ABS_TOLERANCE = 0.051
MAX_REPORTED = 12


def collect_values(
    company: CompanyFundamentals, ratios: RatioSet, scores: QualityScore
) -> set[float]:
    values: set[float] = set()

    def add(value: object) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            values.add(float(value))

    for year in company.fiscal_years:
        for name, value in year.model_dump().items():
            if name != "fiscal_year":
                add(value)
    for name, value in ratios.model_dump().items():
        if name not in {"notes", "basis_year", "prior_year", "cagr_years"}:
            add(value)
    add(ratios.basis_year)
    for component in scores.components:
        add(component.value)
        add(component.points)
    add(scores.overall)
    add(scores.coverage)
    for pillar in scores.pillars:
        add(pillar.score)
    profile = company.profile
    add(profile.price)
    add(profile.shares_outstanding)
    add(profile.dividend_per_share)
    add(profile.beta)
    return values


def _forms(value: float) -> set[float]:
    """Plausible display forms of a stored value.

    Models write 79 for a score of 78.59, 12.4% for a margin of 0.124, and 19.7x
    for a multiple of 19.749. All three should count as grounded.
    """
    base = {value, value * 100.0, abs(value), abs(value) * 100.0}
    forms = set(base)
    for item in base:
        for decimals in (0, 1, 2):
            forms.add(round(item, decimals))
    return forms


def _acceptable(candidate: float, value: float) -> bool:
    for form in _forms(value):
        tolerance = max(ABS_TOLERANCE, abs(form) * REL_TOLERANCE)
        if abs(candidate - form) <= tolerance:
            return True
    return False


def is_checkable(candidate: float) -> bool:
    if candidate != candidate:  # NaN
        return False
    if abs(candidate) < 0.001:
        return False
    if candidate.is_integer() and 1900 <= abs(candidate) <= 2100:
        return False  # a year
    if candidate.is_integer() and abs(candidate) < 21:
        return False  # short counts, ratios like 3x, list numbers
    if candidate.is_integer() and abs(candidate) in {100}:
        return False  # score denominators ("79/100")
    return True


def extract_numbers(text: str) -> list[float]:
    found: list[float] = []
    for match in NUMBER_RE.finditer(text or ""):
        raw = match.group(0)
        cleaned = raw.replace(",", "")
        if cleaned in {"-", "+", ".", "-.", "+."}:
            continue
        try:
            found.append(float(cleaned))
        except ValueError:
            continue
    return found


def check_text(
    text: str, values: Iterable[float], tolerance: float = REL_TOLERANCE
) -> GroundingReport:
    pool = list(values)
    unverified: list[str] = []
    checked = 0
    for candidate in extract_numbers(text):
        if not is_checkable(candidate):
            continue
        checked += 1
        if any(_acceptable(candidate, value) for value in pool):
            continue
        rendered = f"{candidate:g}"
        if rendered not in unverified:
            unverified.append(rendered)
    return GroundingReport(
        checked=checked,
        unverified=unverified[:MAX_REPORTED],
        grounded=not unverified,
        tolerance=tolerance,
    )


def narrative_text(report_fields: dict[str, object]) -> str:
    """Flatten the analyst's narrative fields into one string for checking."""
    chunks: list[str] = []
    for value in report_fields.values():
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, list):
            chunks.extend(str(item) for item in value)
    return "\n".join(chunks)


def check_report(report: FundamentalReport, values: Iterable[float]) -> GroundingReport:
    analysis = report.analysis
    text = narrative_text(
        {
            "summary": analysis.summary,
            "investment_thesis": analysis.investment_thesis,
            "valuation_view": analysis.valuation_view,
            "growth_view": analysis.growth_view,
            "moat": analysis.moat,
            "strengths": analysis.strengths,
            "risks": analysis.risks,
            "red_flags": analysis.red_flags,
            "watch_items": analysis.watch_items,
        }
    )
    return check_text(text, values)
