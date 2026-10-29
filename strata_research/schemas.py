"""Typed contracts shared by the data layer, agents, API and UI.

All monetary values are expressed in **millions** of the reporting currency
unless the field name says otherwise (``eps``, ``price``, ``dividend_per_share``
are per-share amounts). Keeping one unit convention everywhere is what makes
the deterministic ratio math trustworthy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Verdict = Literal["BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"]
DataQuality = Literal["reported", "synthetic", "mixed"]
ReportMode = Literal["llm", "template_llm", "deterministic_fallback"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FinancialYear(BaseModel):
    """One fiscal year of standardized statements."""

    model_config = ConfigDict(extra="ignore")

    fiscal_year: int
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    pretax_income: float | None = None
    income_tax_expense: float | None = None
    net_income: float | None = None
    eps: float | None = None
    interest_expense: float | None = None
    depreciation_amortization: float | None = None
    total_assets: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticker: str
    name: str
    market: str = "PSX"
    exchange: str = "PSX"
    sector: str | None = None
    industry: str | None = None
    country: str | None = "Pakistan"
    currency: str = "PKR"
    description: str | None = None
    price: float | None = None
    shares_outstanding: float | None = Field(
        default=None, description="Diluted shares in millions."
    )
    dividend_per_share: float | None = None
    beta: float | None = None
    as_of: str = Field(default_factory=lambda: utc_now().date().isoformat())
    data_source: str = "unknown"
    data_quality: DataQuality = "synthetic"
    notes: list[str] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, value: str) -> str:
        from .psx import normalize_symbol

        return normalize_symbol(value)


class CompanyFundamentals(BaseModel):
    """Everything the research desk knows about a company before analysis."""

    model_config = ConfigDict(extra="ignore")

    profile: CompanyProfile
    fiscal_years: list[FinancialYear] = Field(min_length=1)
    peers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sort_years(self) -> "CompanyFundamentals":
        self.fiscal_years = sorted(
            self.fiscal_years, key=lambda year: year.fiscal_year, reverse=True
        )
        return self

    @property
    def latest(self) -> FinancialYear:
        return self.fiscal_years[0]

    @property
    def prior(self) -> FinancialYear | None:
        return self.fiscal_years[1] if len(self.fiscal_years) > 1 else None


class RatioSet(BaseModel):
    """Deterministic ratios. ``None`` means 'not computable from the data'."""

    model_config = ConfigDict(extra="ignore")

    # scale / valuation
    market_cap: float | None = None
    enterprise_value: float | None = None
    net_debt: float | None = None
    ebitda: float | None = None
    book_value_per_share: float | None = None
    # profitability
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    # balance sheet
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    # growth
    revenue_growth_yoy: float | None = None
    eps_growth_yoy: float | None = None
    gross_margin_change: float | None = Field(
        default=None, description="Latest minus oldest gross margin, in fraction points."
    )
    operating_margin_change: float | None = None
    revenue_cagr: float | None = None
    eps_cagr: float | None = None
    # cash flow
    fcf: float | None = None
    fcf_margin: float | None = None
    fcf_conversion: float | None = None
    # multiples
    pe: float | None = None
    ps: float | None = None
    pb: float | None = None
    ev_ebitda: float | None = None
    fcf_yield: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    # provenance
    basis_year: int | None = None
    prior_year: int | None = None
    cagr_years: int | None = None
    notes: list[str] = Field(default_factory=list)


class ScoreComponent(BaseModel):
    key: str
    label: str
    pillar: str
    value: float | None = None
    unit: Literal["pct", "x", "money", "ratio"] = "ratio"
    weight: float = 1.0
    points: float | None = Field(default=None, description="0..1 normalized quality")
    note: str = ""


class PillarScore(BaseModel):
    key: str
    label: str
    weight: float
    score: float = Field(ge=0, le=100)
    covered: int = 0
    total: int = 0


class QualityScore(BaseModel):
    overall: float = Field(ge=0, le=100)
    grade: str
    label: str
    anchor_profile: str = "PSX"
    pillars: list[PillarScore] = Field(default_factory=list)
    components: list[ScoreComponent] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    coverage: float = Field(ge=0, le=1, default=0.0)


class ToolCallRecord(BaseModel):
    tool: str
    ok: bool = True
    duration_ms: int = 0
    summary: str = ""
    error: str | None = None


class GroundingReport(BaseModel):
    checked: int = 0
    unverified: list[str] = Field(default_factory=list)
    grounded: bool = True
    tolerance: float = 0.02

    @property
    def ok(self) -> bool:
        return self.grounded


class AnalystOutput(BaseModel):
    """Structured JSON the LLM must return (also produced without an LLM)."""

    model_config = ConfigDict(extra="ignore")

    verdict: Verdict = "INSUFFICIENT_DATA"
    conviction: float = 0.5
    confidence: float = 0.5
    summary: str = ""
    investment_thesis: str = ""
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    valuation_view: str = ""
    growth_view: str = ""
    moat: str = ""
    red_flags: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip().upper().replace(" ", "_")
        aliases = {
            "OVERWEIGHT": "BUY",
            "OUTPERFORM": "BUY",
            "ACCUMULATE": "BUY",
            "LONG": "BUY",
            "NEUTRAL": "HOLD",
            "MARKET_PERFORM": "HOLD",
            "UNDERWEIGHT": "SELL",
            "UNDERPERFORM": "SELL",
            "AVOID": "SELL",
            "REDUCE": "SELL",
            "SHORT": "SELL",
            "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
            "UNKNOWN": "INSUFFICIENT_DATA",
            "N/A": "INSUFFICIENT_DATA",
        }
        text = aliases.get(text, text)
        if text not in {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"}:
            raise ValueError(
                "verdict must be one of BUY, HOLD, SELL, INSUFFICIENT_DATA"
            )
        return text

    @field_validator("conviction", "confidence", mode="before")
    @classmethod
    def _clamp_unit(cls, value: Any) -> Any:
        if value is None:
            return 0.5
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        if number > 1.0:  # model returned a percentage
            number = number / 100.0
        return min(1.0, max(0.0, number))

    @field_validator(
        "strengths", "risks", "red_flags", "watch_items", mode="before"
    )
    @classmethod
    def _coerce_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            cleaned = []
            for item in value:
                if isinstance(item, str):
                    if item.strip():
                        cleaned.append(item.strip())
                elif item is not None:
                    cleaned.append(str(item))
            return cleaned
        return value


class FundamentalReport(BaseModel):
    report_id: str
    agent: str = "fundamental_analyst"
    agent_title: str = "Fundamental Analyst"
    ticker: str
    company: str
    sector: str | None = None
    generated_at: datetime = Field(default_factory=utc_now)
    mode: ReportMode = "llm"
    model: str = "unknown"
    request: dict[str, Any] = Field(default_factory=dict)
    profile: CompanyProfile
    ratios: RatioSet
    scores: QualityScore
    analysis: AnalystOutput
    grounding: GroundingReport = Field(default_factory=GroundingReport)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Research output generated by an automated agent for educational and "
        "research purposes only. Not investment advice. Verify all figures "
        "against primary filings before acting."
    )


class TeamBrief(BaseModel):
    brief_id: str
    ticker: str
    generated_at: datetime = Field(default_factory=utc_now)
    focus: str = ""
    horizon: str = ""
    headline: str = ""
    reports: list[FundamentalReport] = Field(default_factory=list)
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    roadmap: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    disclaimer: str = (
        "Synthesized by a team of automated research agents. Not investment advice."
    )


class ResearchRequest(BaseModel):
    ticker: str
    focus: str = "balanced fundamental view"
    horizon: str = "12-24 months"

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        text = (value or "").strip().upper()
        if not text:
            raise ValueError("ticker is required")
        if not text.replace(".", "").replace("-", "").isalnum():
            raise ValueError("ticker must be alphanumeric (dots and dashes allowed)")
        if len(text) > 12:
            raise ValueError("ticker is too long")
        return text
