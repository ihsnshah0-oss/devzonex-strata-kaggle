"""DevZoneX PSX Research Desk — a team of LLM research agents for Pakistan Stock Exchange listings.

The package has two independent halves:

* ``strata_research.psxdb`` — PSX Data Portal ingestion into SQLite. It only
  needs ``httpx``, so it can run in a bare worker.
* the analysis stack (:class:`ResearchTeam`, :class:`Settings`, the agents and
  the API) — requires ``pydantic``, ``fastapi`` and friends.

The heavy imports are therefore lazy: importing ``strata_research`` is cheap, and
``import strata_research.psxdb`` never drags in the web/LLM stack.

Quick start::

    from strata_research import ResearchTeam, Settings

    team = ResearchTeam(Settings.from_env())
    brief = team.brief("DMEPL", focus="dividend sustainability")
    print(brief.reports[0].analysis.summary)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["Settings", "ResearchTeam", "FundamentalReport", "TeamBrief", "PSX_MARKET", "__version__"]

__version__ = "0.4.0"

#: Every report produced by this package is scoped to this market.
PSX_MARKET = "PSX"

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from .config import Settings
    from .orchestrator import ResearchTeam
    from .schemas import FundamentalReport, TeamBrief

_LAZY = {
    "Settings": ("config", "Settings"),
    "ResearchTeam": ("orchestrator", "ResearchTeam"),
    "FundamentalReport": ("schemas", "FundamentalReport"),
    "TeamBrief": ("schemas", "TeamBrief"),
}


def __getattr__(name: str) -> Any:
    """Import analysis objects on first use (PEP 562)."""
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute)
    globals()[name] = value  # cache for subsequent lookups
    return value


def __dir__() -> list[str]:  # pragma: no cover - introspection helper
    return sorted(list(globals()) + list(_LAZY))
