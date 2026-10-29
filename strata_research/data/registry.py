"""Provider selection for a PSX-only research desk.

Priority in ``auto`` mode:

1. ``psx``     — statements you supply (``STRATA_RESEARCH_PSX_DIR``), priced from
                 the live PSX Data Portal when quotes are enabled.
2. ``yfinance``— live ``<SYMBOL>.KA`` listings on Yahoo Finance.
3. ``demo``    — the fictional offline PSX universe.

Nothing outside PSX is accepted: every ticker is normalised to a PSX symbol
(``PSX:OGDC``, ``ogdc.KA`` and ``OGDC`` are the same company) and reports are
labelled with ``market="PSX"``.
"""

from __future__ import annotations

import time
from typing import Iterable

from ..config import Settings
from ..psx import PsxQuoteClient, normalize_symbol
from ..schemas import CompanyFundamentals
from .base import DataProviderError, FundamentalsProvider
from .demo import DemoProvider
from .json_provider import JsonProvider
from .psx_provider import PsxStatementsProvider
from .yfinance_provider import YFinanceProvider

__all__ = [
    "DataProviderError",
    "FundamentalsProvider",
    "build_providers",
    "provider_status",
    "fetch_fundamentals",
    "clear_cache",
    "demo_universe",
]

_CACHE: dict[tuple[str, str], tuple[float, CompanyFundamentals]] = {}
_CACHE_TTL_SECONDS = 900.0

_QUOTE_CLIENTS: dict[str, PsxQuoteClient] = {}


def _quote_client(settings: Settings) -> PsxQuoteClient | None:
    if not settings.psx_quotes:
        return None
    key = f"{settings.psx_base_url}|{settings.psx_quote_timeout}"
    if key not in _QUOTE_CLIENTS:
        _QUOTE_CLIENTS[key] = PsxQuoteClient(
            base_url=settings.psx_base_url, timeout=settings.psx_quote_timeout
        )
    return _QUOTE_CLIENTS[key]


def build_providers(settings: Settings) -> list[FundamentalsProvider]:
    psx = PsxStatementsProvider(
        settings.psx_dir,
        quote_client=_quote_client(settings),
        use_quotes=settings.psx_quotes,
    )
    live = YFinanceProvider()
    demo = DemoProvider()
    generic_json = JsonProvider(settings.data_dir)

    explicit = settings.data_provider
    if explicit == "demo":
        return [demo]
    if explicit == "psx":
        return [psx]
    if explicit == "json":
        return [generic_json]
    if explicit == "yfinance":
        return [live]

    chain: list[FundamentalsProvider] = []
    if psx.available():
        chain.append(psx)
    if live.available():
        chain.append(live)
    chain.append(demo)
    return chain


def provider_status(settings: Settings) -> list[dict[str, object]]:
    psx = PsxStatementsProvider(settings.psx_dir, quote_client=None, use_quotes=False)
    live = YFinanceProvider()
    demo = DemoProvider()
    entries = [
        {
            "name": "psx",
            "available": psx.available(),
            "requires_network": False,
            "detail": "Local PSX statements"
            + (f" in {settings.psx_dir}" if settings.psx_dir else " (set STRATA_RESEARCH_PSX_DIR)")
            + (", priced from the PSX Data Portal" if settings.psx_quotes else ""),
        },
        {
            "name": "yfinance",
            "available": live.available(),
            "requires_network": True,
            "detail": "Live <SYMBOL>.KA listings on Yahoo Finance (optional dependency)",
        },
        {
            "name": "demo",
            "available": True,
            "requires_network": False,
            "detail": "Fictional offline PSX universe: " + ", ".join(demo.universe),
        },
    ]
    return [entry for entry in entries if entry["name"] != "json"] if settings.data_provider != "json" else entries + [
        {
            "name": "json",
            "available": JsonProvider(settings.data_dir).available(),
            "requires_network": False,
            "detail": "Generic JSON statements (fallback for custom feeds)",
        }
    ]


def clear_cache() -> None:
    _CACHE.clear()


def demo_universe() -> list[dict[str, str]]:
    return DemoProvider().universe_summary()


def fetch_fundamentals(settings: Settings, ticker: str) -> CompanyFundamentals:
    """Fetch PSX fundamentals, walking the provider chain until one succeeds."""
    symbol = normalize_symbol(ticker)
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
        company.profile.market = "PSX"
        company.profile.exchange = company.profile.exchange or "PSX"
        _CACHE[key] = (time.monotonic(), company)
        return company.model_copy(deep=True)

    detail = " | ".join(errors) if errors else "no providers configured"
    raise DataProviderError(f"Could not load PSX fundamentals for {symbol}: {detail}")


def provider_names(providers: Iterable[FundamentalsProvider]) -> list[str]:
    return [provider.name for provider in providers]
