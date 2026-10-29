"""DevZoneX Strata Research — a small team of LLM research agents.

The package is intentionally independent of the Kaggle launcher in
``scripts/``. It is a Python backend that talks to any OpenAI-compatible
chat-completions endpoint (including the Strata server the notebook starts)
and produces grounded, auditable research notes.

Quick start::

    from strata_research import ResearchTeam, Settings

    team = ResearchTeam(Settings.from_env())
    brief = team.brief("AAPL", focus="margin durability")
    print(brief.reports[0].analysis.summary)
"""

from __future__ import annotations

from .config import Settings
from .orchestrator import ResearchTeam
from .schemas import FundamentalReport, TeamBrief

__all__ = ["Settings", "ResearchTeam", "FundamentalReport", "TeamBrief", "__version__"]

__version__ = "0.2.0"
