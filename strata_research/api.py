"""FastAPI backend for the research desk.

Run it with::

    uvicorn strata_research.api:app --host 0.0.0.0 --port 8000

Endpoints are versioned under ``/api/v1`` so the UI and future agents can evolve
independently. The LLM is only ever reached from the server, never the browser,
so API keys stay server-side.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .compute import compute_ratios, margin_trend
from .config import Settings
from .data import DataProviderError, fetch_fundamentals, provider_status
from .data.demo import DemoProvider
from .llm import LLMError
from .orchestrator import DESK_NAME, ResearchTeam
from .schemas import ResearchRequest, TeamBrief
from .scoring import score_company
from .tools import describe_tools

logger = logging.getLogger("strata_research.api")

UI_DIR = Path(__file__).parent / "ui"
DISCLAIMER = (
    "Automated research output. Educational use only; not investment advice. "
    "Verify every figure against primary filings."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        _app.state.team.close()

    app = FastAPI(
        title="DevZoneX Strata Research Desk",
        version=__version__,
        lifespan=lifespan,
        description=(
            "A team of LLM research agents on a Python backend. Agent 1 is the "
            "Fundamental Analyst: deterministic ratio/scoring engine plus an "
            "OpenAI-compatible LLM (including a Strata endpoint) for the narrative."
        ),
    )
    app.state.team = ResearchTeam(resolved)

    # ------------------------------------------------------------------
    @app.exception_handler(DataProviderError)
    async def _data_error(_request: Request, exc: DataProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "kind": "data_provider_error"},
        )

    @app.exception_handler(LLMError)
    async def _llm_error(_request: Request, exc: LLMError) -> JSONResponse:
        status = 504 if exc.status is None else 502
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "kind": "llm_error", "retryable": exc.retryable},
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    @app.get("/health")
    def health() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        return {
            "status": "ok",
            "version": __version__,
            "desk": DESK_NAME,
            "llm": team.settings.resolved_llm_kind,
            "model": team.settings.model,
        }

    @app.get("/api/v1/status")
    def status() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        payload = team.status()
        payload["version"] = __version__
        payload["disclaimer"] = DISCLAIMER
        return payload

    @app.get("/api/v1/agents")
    def agents() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        cards = team.cards()
        return {
            "agents": cards,
            "available": [card["key"] for card in cards if card["status"] == "available"],
            "planned": [card["key"] for card in cards if card["status"] == "planned"],
            "tools": describe_tools(),
        }

    @app.get("/api/v1/providers")
    def providers() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        return {
            "configured": team.settings.data_provider,
            "providers": provider_status(team.settings),
        }

    @app.post("/api/v1/agents/fundamental/analyze")
    def analyze_fundamental(request: ResearchRequest) -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        report = team.analyse(request)
        return report.model_dump(mode="json")

    @app.post("/api/v1/team/brief")
    def team_brief(request: ResearchRequest) -> TeamBrief:
        team: ResearchTeam = app.state.team
        return team.brief(request.ticker, request.focus, request.horizon)

    @app.get("/api/v1/reports")
    def reports() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        return {"reports": team.history()}

    @app.get("/api/v1/reports/{report_id}")
    def report(report_id: str) -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        found = team.get_report(report_id)
        if found is None:
            raise HTTPException(status_code=404, detail="report not found in this session")
        return found.model_dump(mode="json")

    @app.get("/api/v1/companies/{ticker}/preview")
    def preview(ticker: str) -> dict[str, Any]:
        """Deterministic snapshot with no LLM call - fast and free."""
        team: ResearchTeam = app.state.team
        company = fetch_fundamentals(team.settings, ticker)
        ratios = compute_ratios(company)
        scores = score_company(company, ratios)
        return {
            "profile": company.profile.model_dump(mode="json"),
            "ratios": ratios.model_dump(mode="json"),
            "scores": scores.model_dump(mode="json"),
            "years": [year.model_dump(mode="json") for year in company.fiscal_years],
            "margin_trend": {
                "gross": margin_trend(company, "gross"),
                "operating": margin_trend(company, "operating"),
                "net": margin_trend(company, "net"),
            },
            "peers": company.peers,
        }

    @app.get("/api/v1/demo/companies")
    def demo_companies() -> dict[str, Any]:
        team: ResearchTeam = app.state.team
        return {
            "note": "Fictional companies used by the offline demo provider.",
            "tickers": list(DemoProvider().universe),
            "active_provider": team.settings.data_provider,
        }

    @app.get("/ui", include_in_schema=False)
    def ui_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

    return app


app = create_app()
