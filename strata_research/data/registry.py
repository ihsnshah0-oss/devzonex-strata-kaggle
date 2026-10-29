"""Provider selection and a small time-to-live cache."""

from __future__ import annotations

import time
from typing import Iterable

from ..config import Settings
from ..schemas import CompanyFundamentals
from .base import DataProviderError, FundamentalsProvider
from .demo import DemoProvider
from .json_provider import JsonProvider
from .yfinance_provider import YFinanceProvider

__all__ = [
    "DataProviderError",
    "FundamentalsProvider",
    "build_providers",
    "provider_status",
    "fetch_fundamentals",
    "clear_cache",
]

_CACHE: dict[tuple[str, str], tuple[float, CompanyFundamentals]] = {}
_CACHE_TTL_SECONDS = 900.0


def build_providers(settings: Settings) -> list[FundamentalsProvider]:
    """Return provider candidates in priority order for ``settings``."""
    json_provider = JsonProvider(settings.data_dir)
    live = YFinanceProvider()
    demo = DemoProvider()

    explicit = settings.data_provider
    if explicit == "demo":
        return [demo]
    if explicit == "json":
        return [json_provider]
    if explicit == "yfinance":
        return [live]

    chain: list[FundamentalsProvider] = []
    if json_provider.available():
        chain.append(json_provider)
    if live.available():
        chain.append(live)
    chain.append(demo)
    return chain


def provider_status(settings: Settings) -> list[dict[str, object]]:
    providers = [JsonProvider(settings.data_dir), YFinanceProvider(), DemoProvider()]
    return [
        {
            "name": provider.name,
            "available": bool(getattr(provider, "available", lambda: True)()),
            "requires_network": provider.requires_network,
        }
        for provider in providers
    ]


def clear_cache() -> None:
    _CACHE.clear()


def fetch_fundamentals(settings: Settings, ticker: str) -> CompanyFundamentals:
    """Fetch fundamentals, walking the provider chain until one succeeds."""
    symbol = ticker.strip().upper()
    errors: list[str] = []
    for provider in build_providers(settings):
        key = (provider.name, symbol)
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1].model_copy(deep=True)
        try:
            company = provider.fetch(symbol)
        except DataProviderError as exc:
            errors.append(f"{provider.name}: {exc}")
            continue
        except Exception as exc:  # defensive: never let a provider crash the desk
            errors.append(f"{provider.name}: unexpected error: {exc}")
            continue
        company.profile.data_source = company.profile.data_source or provider.name
        _CACHE[key] = (time.monotonic(), company)
        return company.model_copy(deep=True)

    detail = " | ".join(errors) if errors else "no providers configured"
    raise DataProviderError(f"Could not load fundamentals for {symbol}: {detail}")


def provider_names(providers: Iterable[FundamentalsProvider]) -> list[str]:
    return [provider.name for provider in providers]
