"""The desk's default PSX watchlist.

These are the KSE100 names the desk is expected to answer for out of the box. The
list is only a *shortlist*: it never invents data. Each symbol resolves through the
PSX Data Portal mirror (``data/psx.db``), and a symbol the portal does not publish
financials for fails loudly in ``analyze`` instead of being silently filled in.

Override it with ``STRATA_RESEARCH_WATCHLIST="OGDC,MEBL,LUCK"`` or a file of
comma/newline separated tickers.
"""

from __future__ import annotations

import os
from pathlib import Path

WATCHLIST: tuple[str, ...] = (
    "ENGROH",
    "FFC",
    "EFERT",
    "HUBC",
    "AIRLINK",
    "ATRL",
    "CPHL",
    "DGKC",
    "FCCL",
    "FFL",
    "GAL",
    "GHNI",
    "HCAR",
    "MARI",
    "MLCF",
    "NML",
    "NRL",
    "PAEL",
    "PRL",
    "PSO",
    "SAZEW",
    "SEARL",
    "SNGP",
    "SSGC",
    "SYS",
)


def _clean(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        ticker = value.strip().upper()
        if ticker and ticker not in seen:
            seen.append(ticker)
    return seen


def load_watchlist(path: str | Path | None = None) -> list[str]:
    """Return the watchlist: a file, ``STRATA_RESEARCH_WATCHLIST``, or the default."""
    if path:
        text = Path(path).expanduser().read_text(encoding="utf-8")
        return _clean(text.replace(",", "\n").splitlines())
    override = os.environ.get("STRATA_RESEARCH_WATCHLIST", "").strip()
    if override:
        return _clean(override.replace(",", "\n").splitlines())
    return list(WATCHLIST)


__all__ = ["WATCHLIST", "load_watchlist"]
