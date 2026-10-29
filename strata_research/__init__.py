"""DevZoneX PSX Research Desk — a team of LLM research agents for Pakistan Stock Exchange listings.

The package is intentionally independent of the Kaggle launcher in
``scripts/``. It is a Python backend that talks to any OpenAI-compatible
chat-completions endpoint (including the Strata server the notebook starts)
and produces grounded, auditable research notes.

Quick start::

    from strata_research import ResearchTeam, Settings

    team = ResearchTeam(Settings.from_env())
    brief = team.brief("DMEPL", focus="dividend sustainability")
    print(brief.reports[0].analysis.summary)
"""

from __future__ import annotations

from .config import Settings
from .orchestrator import ResearchTeam
from .schemas import FundamentalReport, TeamBrief

__all__ = ["Settings", "ResearchTeam", "FundamentalReport", "TeamBrief", "__version__"]

__version__ = "0.3.0"
