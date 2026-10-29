"""PSX Data Portal ingestion: client, parsers, SQLite store and CLI.

Everything in this package reads **only** ``https://dps.psx.com.pk``. No other
data source is contacted, and every row records which portal endpoint it came
from so the database is auditable end to end.

Quick start::

    python -m strata_research.psxdb init
    python -m strata_research.psxdb ingest --indices KSE100,KMI30
    python -m strata_research.psxdb stats
    python -m strata_research.psxdb constituents KSE100
"""

from __future__ import annotations

from .client import PsxPortalClient, PortalError, PortalSchemaError
from .ingest import IngestReport, ingest, ingest_from_capture
from .query import (
    constituents,
    database_stats,
    index_levels,
    latest_quotes,
    market_summary,
    price_history,
    run_fundamentals,
    symbols,
)
from .store import PsxDatabase

__all__ = [
    "PsxPortalClient",
    "PortalError",
    "PortalSchemaError",
    "PsxDatabase",
    "IngestReport",
    "ingest",
    "ingest_from_capture",
    "constituents",
    "database_stats",
    "index_levels",
    "latest_quotes",
    "market_summary",
    "price_history",
    "run_fundamentals",
    "symbols",
]
