"""Agent registry.

Agent 1 ships today. The rest are declared here with their contract so the API
and UI can show the roadmap honestly instead of pretending they exist.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from .base import AgentCard, BaseAgent, ResponseParseError, extract_json_object
from .fundamental import FUNDAMENTAL_CARD, FundamentalAnalyst

PLANNED_AGENTS: tuple[AgentCard, ...] = (
    AgentCard(
        key="news_sentiment_analyst",
        name="News & Sentiment Analyst",
        title="Agent 2 · News & Sentiment Analyst",
        status="planned",
        description=(
            "Retrieves filings, transcripts and news, then extracts catalysts, "
            "guidance changes and management tone with citations. Requires a "
            "document store and an embedding model."
        ),
        tools=("search_documents", "summarize_filing", "score_sentiment"),
        techniques=("RAG", "citation tracking", "tone/sentiment scoring"),
        inputs="ticker + document corpus",
        outputs="Catalyst and sentiment memo with citations",
        order=2,
    ),
    AgentCard(
        key="technical_analyst",
        name="Technical & Market Structure Analyst",
        title="Agent 3 · Technical & Market Structure Analyst",
        status="planned",
        description=(
            "Reads price and volume history for trend, volatility and liquidity "
            "context. Needs an OHLCV provider; outputs levels, not opinions."
        ),
        tools=("get_price_history", "compute_indicators", "detect_regimes"),
        techniques=("moving averages", "ATR/volatility", "relative strength"),
        inputs="ticker + OHLCV history",
        outputs="Trend and liquidity note with key levels",
        order=3,
    ),
    AgentCard(
        key="risk_analyst",
        name="Risk & Compliance Analyst",
        title="Agent 4 · Risk & Compliance Analyst",
        status="planned",
        description=(
            "Stress-tests the thesis: leverage, concentration, drawdown scenarios "
            "and position sizing. Consumes the other agents' structured outputs."
        ),
        tools=("stress_test", "position_sizer", "check_constraints"),
        techniques=("scenario analysis", "factor exposure", "position sizing"),
        inputs="structured reports from agents 1-3",
        outputs="Risk register and sizing constraints",
        order=4,
    ),
    AgentCard(
        key="quant_analyst",
        name="Quant & Backtest Analyst",
        title="Agent 5 · Quant & Backtest Analyst",
        status="planned",
        description=(
            "Turns the desk's signals into rules, then measures them out-of-sample. "
            "Needs a point-in-time data layer to avoid look-ahead bias."
        ),
        tools=("build_factor", "run_backtest", "report_metrics"),
        techniques=("factor construction", "walk-forward validation", "IC analysis"),
        inputs="historical point-in-time data",
        outputs="Backtest report with hit rate and drawdown",
        order=5,
    ),
    AgentCard(
        key="portfolio_manager",
        name="Portfolio Manager",
        title="Agent 6 · Portfolio Manager (synthesis)",
        status="planned",
        description=(
            "Reconciles conflicting specialist views into one recommendation with "
            "explicit dissent. Only runs when at least two analysts have reported."
        ),
        tools=("compare_reports", "weight_evidence", "write_decision"),
        techniques=("evidence weighting", "devil's advocate pass"),
        inputs="reports from agents 1-5",
        outputs="Final memo with dissent and audit trail",
        order=6,
    ),
)

AVAILABLE_AGENTS: tuple[AgentCard, ...] = (FUNDAMENTAL_CARD,)
ALL_AGENTS: tuple[AgentCard, ...] = tuple(
    sorted(AVAILABLE_AGENTS + PLANNED_AGENTS, key=lambda card: card.order)
)

FACTORIES = {"fundamental_analyst": FundamentalAnalyst}


def agent_cards() -> list[dict[str, Any]]:
    return [card.to_dict() for card in ALL_AGENTS]


def create_agent(key: str, settings: Settings, **kwargs: Any) -> BaseAgent:
    factory = FACTORIES.get(key)
    if factory is None:
        raise KeyError(f"agent {key!r} is not implemented (available: {', '.join(FACTORIES)})")
    return factory(settings, **kwargs)  # type: ignore[call-arg]


__all__ = [
    "ALL_AGENTS",
    "AVAILABLE_AGENTS",
    "FUNDAMENTAL_CARD",
    "PLANNED_AGENTS",
    "AgentCard",
    "BaseAgent",
    "ResponseParseError",
    "FundamentalAnalyst",
    "agent_cards",
    "create_agent",
    "extract_json_object",
]
