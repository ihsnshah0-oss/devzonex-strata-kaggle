"""The research desk: today one analyst, tomorrow a team.

``ResearchTeam`` is the single object the API, CLI and UI talk to. It owns the
LLM client, the report history and the agent registry. Adding agent #2 means
implementing it, registering it in ``agents/__init__.py`` and calling it from
:meth:`ResearchTeam.brief`.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from typing import Any

from .agents import ALL_AGENTS, FundamentalAnalyst, agent_cards
from .config import Settings
from .data import provider_status
from .formatting import fmt_pct
from .prompts import build_team_brief_prompt
from .schemas import FundamentalReport, ResearchRequest, TeamBrief
from .tools import describe_tools

DESK_NAME = "DevZoneX Strata Research Desk"


class ResearchTeam:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._analyst: FundamentalAnalyst | None = None
        self._history: deque[FundamentalReport] = deque(
            maxlen=max(1, self.settings.report_history)
        )

    # ------------------------------------------------------------------
    @property
    def fundamental_analyst(self) -> FundamentalAnalyst:
        if self._analyst is None:
            self._analyst = FundamentalAnalyst(self.settings)
        return self._analyst

    def close(self) -> None:
        if self._analyst is not None:
            self._analyst.close()
            self._analyst = None

    def __enter__(self) -> "ResearchTeam":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    def cards(self) -> list[dict[str, Any]]:
        return agent_cards()

    def status(self) -> dict[str, Any]:
        return {
            "desk": DESK_NAME,
            "settings": self.settings.public_dict(),
            "agents": agent_cards(),
            "providers": provider_status(self.settings),
            "tools": describe_tools(),
            "demo_tickers": ["NOVA", "HELX", "ARCL"],
            "history_size": len(self._history),
        }

    # ------------------------------------------------------------------
    def analyse(self, request: ResearchRequest) -> FundamentalReport:
        report = self.fundamental_analyst.run(request)
        self._history.append(report)
        return report

    def analyse_ticker(
        self,
        ticker: str,
        focus: str = "balanced fundamental view",
        horizon: str = "12-24 months",
    ) -> FundamentalReport:
        return self.analyse(ResearchRequest(ticker=ticker, focus=focus, horizon=horizon))

    def brief(
        self,
        ticker: str,
        focus: str = "balanced fundamental view",
        horizon: str = "12-24 months",
    ) -> TeamBrief:
        """Run every available agent and package the desk output."""
        started = time.perf_counter()
        request = ResearchRequest(ticker=ticker, focus=focus, horizon=horizon)
        reports: list[FundamentalReport] = [self.analyse(request)]

        coverage: list[dict[str, Any]] = []
        for report in reports:
            coverage.append(
                {
                    "agent": report.agent,
                    "title": report.agent_title,
                    "status": "delivered",
                    "report_id": report.report_id,
                    "verdict": report.analysis.verdict,
                    "conviction": report.analysis.conviction,
                    "confidence": report.analysis.confidence,
                    "quality_score": report.scores.overall,
                    "mode": report.mode,
                    "duration_ms": report.duration_ms,
                    "warnings": len(report.warnings),
                }
            )

        roadmap = [
            {
                "agent": card.key,
                "title": card.title,
                "status": card.status,
                "reason": "Not implemented yet; contract published for the next build.",
                "needs": card.inputs,
            }
            for card in ALL_AGENTS
            if card.status == "planned"
        ]

        headline = self._headline(reports[0])
        return TeamBrief(
            brief_id=uuid.uuid4().hex[:12],
            ticker=reports[0].ticker,
            focus=focus,
            horizon=horizon,
            headline=headline,
            reports=reports,
            coverage=coverage,
            roadmap=roadmap,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # ------------------------------------------------------------------
    def _headline(self, report: FundamentalReport) -> str:
        analysis = report.analysis
        pieces = [
            f"{report.company} ({report.ticker}): {analysis.verdict}",
            f"conviction {analysis.conviction:.2f}",
            f"quality {report.scores.overall:.0f}/100 ({report.scores.grade})",
        ]
        if report.ratios.ev_ebitda is not None:
            pieces.append(f"EV/EBITDA {report.ratios.ev_ebitda:.1f}x")
        if report.ratios.net_margin is not None:
            pieces.append(f"net margin {fmt_pct(report.ratios.net_margin)}")
        if report.scores.red_flags:
            pieces.append(f"{len(report.scores.red_flags)} red flag(s)")
        return "; ".join(pieces) + "."

    # ------------------------------------------------------------------
    def history(self) -> list[dict[str, Any]]:
        return [
            {
                "report_id": report.report_id,
                "ticker": report.ticker,
                "company": report.company,
                "generated_at": report.generated_at.isoformat(),
                "verdict": report.analysis.verdict,
                "mode": report.mode,
                "quality_score": report.scores.overall,
                "duration_ms": report.duration_ms,
            }
            for report in reversed(self._history)
        ]

    def get_report(self, report_id: str) -> FundamentalReport | None:
        for report in self._history:
            if report.report_id == report_id:
                return report
        return None

    # ------------------------------------------------------------------
    def brief_prompt(self, brief: TeamBrief) -> str:
        """Prompt used by the (future) portfolio manager to synthesize the desk."""
        return build_team_brief_prompt(
            brief.ticker,
            brief.focus,
            brief.horizon,
            [
                {
                    "agent": report.agent,
                    "verdict": report.analysis.verdict,
                    "conviction": report.analysis.conviction,
                    "summary": report.analysis.summary,
                    "red_flags": report.analysis.red_flags,
                }
                for report in brief.reports
            ],
            brief.roadmap,
        )

def create_team(settings: Settings | None = None) -> ResearchTeam:
    return ResearchTeam(settings)


__all__ = ["DESK_NAME", "ResearchTeam", "create_team"]
