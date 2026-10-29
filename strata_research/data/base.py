"""Provider contract for company fundamentals.

Providers are deliberately small: they return a :class:`CompanyFundamentals`
and nothing else. All ratio math, scoring and LLM prompting happens downstream
so providers stay swappable and testable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas import CompanyFundamentals


class DataProviderError(RuntimeError):
    """Raised when data cannot be sourced for a ticker."""


class ProviderUnavailable(DataProviderError):
    """Raised when an optional dependency or data directory is missing."""


@runtime_checkable
class FundamentalsProvider(Protocol):
    name: str
    requires_network: bool

    def fetch(self, ticker: str) -> CompanyFundamentals:  # pragma: no cover - protocol
        ...


def to_number(value: object) -> float | None:
    """Best-effort float conversion that treats NaN/None/'' as missing."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "null", "-", "n/a", "na"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
