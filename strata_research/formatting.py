"""Small, dependency-free formatting helpers shared by prompts, tools and UI."""

from __future__ import annotations

NA = "n/a"


def fmt_pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    """Format a *fraction* (0.1612) as a percentage string ('16.1%')."""
    if value is None:
        return NA
    text = f"{value * 100:+.{digits}f}%" if signed else f"{value * 100:.{digits}f}%"
    return text


def fmt_x(value: float | None, digits: int = 1) -> str:
    if value is None:
        return NA
    return f"{value:.{digits}f}x"


def fmt_money(value: float | None, digits: int = 0, currency: str = "") -> str:
    """Format an amount expressed in millions."""
    if value is None:
        return NA
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{value:,.{digits}f}M"


def fmt_per_share(value: float | None, currency: str = "") -> str:
    if value is None:
        return NA
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{value:,.2f}"


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return NA
    return f"{value:,.{digits}f}"


def fmt_amount(value: float | None, currency: str = "PKR", digits: int = 1) -> str:
    """Compact PKR amount from a figure expressed in millions."""
    if value is None:
        return NA
    prefix = f"{currency} " if currency else ""
    if abs(value) >= 1_000_000:
        return f"{prefix}{value / 1_000_000:,.{digits}f}trn"
    if abs(value) >= 1_000:
        return f"{prefix}{value / 1_000:,.{digits}f}bn"
    return f"{prefix}{value:,.0f}M"


def fmt_crore(value: float | None, digits: int = 0) -> str:
    """PKR crores from a figure expressed in millions (1 crore = 10 million)."""
    if value is None:
        return NA
    return f"PKR {value / 10:,.{digits}f} crore"


def fmt_score(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value:.0f}/100"


def grade_for(score: float) -> tuple[str, str]:
    """Map a 0-100 quality score to a letter grade and a human label."""
    if score >= 85:
        return "A", "Exceptional"
    if score >= 72:
        return "B", "Strong"
    if score >= 58:
        return "C", "Solid"
    if score >= 44:
        return "D", "Mixed"
    if score >= 30:
        return "E", "Weak"
    return "F", "Distressed"
