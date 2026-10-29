"""Deterministic, offline demo universe.

These companies are **fictional**. The numbers are chosen so that the three
archetypes behave differently under the scoring engine:

* ``NOVA`` — high-quality compounder trading at a rich multiple.
* ``HELX`` — defensive cash generator at a fair multiple.
* ``ARCL`` — leveraged retailer with deteriorating fundamentals (red flags).

Every report built from this provider is labelled ``data_quality="synthetic"``.
"""

from __future__ import annotations

from ..schemas import CompanyFundamentals, CompanyProfile, FinancialYear
from .base import DataProviderError

_COMPANIES: dict[str, dict] = {
    "NOVA": {
        "profile": {
            "ticker": "NOVA",
            "name": "NovaGrid Robotics Inc.",
            "sector": "Industrials",
            "industry": "Industrial Automation",
            "country": "United States",
            "currency": "USD",
            "price": 84.20,
            "shares_outstanding": 120.0,
            "dividend_per_share": 0.0,
            "beta": 1.25,
            "description": (
                "Designs and manufactures warehouse automation cells, machine-vision "
                "inspection systems and the NovaOS orchestration software layer. "
                "Roughly 38% of revenue is recurring software and service."
            ),
        },
        "peers": ["ROK", "EMR", "ZBRA"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 2450.0, "gross_profit": 1225.0,
                "operating_income": 392.0, "pretax_income": 380.0,
                "income_tax_expense": 76.0, "net_income": 304.0, "eps": 2.53,
                "interest_expense": 12.0, "depreciation_amortization": 110.0,
                "total_assets": 3200.0, "total_equity": 1750.0, "total_debt": 420.0,
                "cash_and_equivalents": 610.0, "current_assets": 1520.0,
                "current_liabilities": 720.0, "inventory": 380.0,
                "operating_cash_flow": 430.0, "capex": 130.0,
            },
            {
                "fiscal_year": 2024, "revenue": 2080.0, "gross_profit": 1010.0,
                "operating_income": 318.0, "pretax_income": 306.0,
                "income_tax_expense": 61.0, "net_income": 245.0, "eps": 2.04,
                "interest_expense": 11.0, "depreciation_amortization": 96.0,
                "total_assets": 2920.0, "total_equity": 1540.0, "total_debt": 400.0,
                "cash_and_equivalents": 520.0, "current_assets": 1350.0,
                "current_liabilities": 660.0, "inventory": 340.0,
                "operating_cash_flow": 360.0, "capex": 112.0,
            },
            {
                "fiscal_year": 2023, "revenue": 1750.0, "gross_profit": 823.0,
                "operating_income": 252.0, "pretax_income": 240.0,
                "income_tax_expense": 48.0, "net_income": 192.0, "eps": 1.60,
                "interest_expense": 10.0, "depreciation_amortization": 82.0,
                "total_assets": 2600.0, "total_equity": 1340.0, "total_debt": 380.0,
                "cash_and_equivalents": 430.0, "current_assets": 1180.0,
                "current_liabilities": 610.0, "inventory": 300.0,
                "operating_cash_flow": 292.0, "capex": 96.0,
            },
        ],
    },
    "HELX": {
        "profile": {
            "ticker": "HELX",
            "name": "Helix Therapeutics PLC",
            "sector": "Health Care",
            "industry": "Pharmaceuticals",
            "country": "United Kingdom",
            "currency": "USD",
            "price": 46.50,
            "shares_outstanding": 210.0,
            "dividend_per_share": 0.46,
            "beta": 0.85,
            "description": (
                "Specialty pharmaceutical group with a portfolio concentrated in "
                "immunology and metabolic disease. Two anchor products represent "
                "about half of group sales; a mid-stage pipeline offsets patent "
                "cliffs later this decade."
            ),
        },
        "peers": ["PFE", "MRK", "NVS"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 3900.0, "gross_profit": 2860.0,
                "operating_income": 900.0, "pretax_income": 830.0,
                "income_tax_expense": 166.0, "net_income": 664.0, "eps": 3.16,
                "interest_expense": 45.0, "depreciation_amortization": 210.0,
                "total_assets": 6100.0, "total_equity": 3900.0, "total_debt": 1400.0,
                "cash_and_equivalents": 900.0, "current_assets": 2500.0,
                "current_liabilities": 1350.0, "inventory": 620.0,
                "operating_cash_flow": 1050.0, "capex": 240.0,
            },
            {
                "fiscal_year": 2024, "revenue": 3600.0, "gross_profit": 2620.0,
                "operating_income": 810.0, "pretax_income": 745.0,
                "income_tax_expense": 149.0, "net_income": 596.0, "eps": 2.84,
                "interest_expense": 48.0, "depreciation_amortization": 200.0,
                "total_assets": 5800.0, "total_equity": 3600.0, "total_debt": 1450.0,
                "cash_and_equivalents": 800.0, "current_assets": 2350.0,
                "current_liabilities": 1300.0, "inventory": 600.0,
                "operating_cash_flow": 980.0, "capex": 230.0,
            },
            {
                "fiscal_year": 2023, "revenue": 3300.0, "gross_profit": 2380.0,
                "operating_income": 730.0, "pretax_income": 668.0,
                "income_tax_expense": 134.0, "net_income": 534.0, "eps": 2.54,
                "interest_expense": 50.0, "depreciation_amortization": 190.0,
                "total_assets": 5500.0, "total_equity": 3300.0, "total_debt": 1500.0,
                "cash_and_equivalents": 700.0, "current_assets": 2200.0,
                "current_liabilities": 1250.0, "inventory": 580.0,
                "operating_cash_flow": 900.0, "capex": 220.0,
            },
        ],
    },
    "ARCL": {
        "profile": {
            "ticker": "ARCL",
            "name": "Arcadia Retail Group",
            "sector": "Consumer Discretionary",
            "industry": "Apparel Retail",
            "country": "United States",
            "currency": "USD",
            "price": 12.40,
            "shares_outstanding": 85.0,
            "dividend_per_share": 0.60,
            "beta": 1.60,
            "description": (
                "Mid-market mall-based apparel retailer operating about 620 stores. "
                "Inventory has been building while traffic declines; the balance "
                "sheet carries a large term loan refinanced at higher rates."
            ),
        },
        "peers": ["GAP", "ANF", "URBN"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 5200.0, "gross_profit": 1560.0,
                "operating_income": 208.0, "pretax_income": 96.0,
                "income_tax_expense": 24.0, "net_income": 72.0, "eps": 0.85,
                "interest_expense": 105.0, "depreciation_amortization": 180.0,
                "total_assets": 4200.0, "total_equity": 900.0, "total_debt": 2300.0,
                "cash_and_equivalents": 140.0, "current_assets": 1500.0,
                "current_liabilities": 1250.0, "inventory": 980.0,
                "operating_cash_flow": 210.0, "capex": 190.0,
            },
            {
                "fiscal_year": 2024, "revenue": 5400.0, "gross_profit": 1701.0,
                "operating_income": 270.0, "pretax_income": 170.0,
                "income_tax_expense": 44.0, "net_income": 126.0, "eps": 1.48,
                "interest_expense": 98.0, "depreciation_amortization": 175.0,
                "total_assets": 4300.0, "total_equity": 1000.0, "total_debt": 2200.0,
                "cash_and_equivalents": 160.0, "current_assets": 1560.0,
                "current_liabilities": 1240.0, "inventory": 900.0,
                "operating_cash_flow": 240.0, "capex": 180.0,
            },
            {
                "fiscal_year": 2023, "revenue": 5600.0, "gross_profit": 1848.0,
                "operating_income": 336.0, "pretax_income": 246.0,
                "income_tax_expense": 62.0, "net_income": 184.0, "eps": 2.16,
                "interest_expense": 90.0, "depreciation_amortization": 170.0,
                "total_assets": 4400.0, "total_equity": 1100.0, "total_debt": 2100.0,
                "cash_and_equivalents": 180.0, "current_assets": 1600.0,
                "current_liabilities": 1200.0, "inventory": 860.0,
                "operating_cash_flow": 300.0, "capex": 170.0,
            },
        ],
    },
}

ALIASES = {"DEMO": "NOVA", "EXAMPLE": "NOVA"}


class DemoProvider:
    """Serves the fictional demo universe; no network access required."""

    name = "demo"
    requires_network = False

    def __init__(self) -> None:
        self.universe = ("NOVA", "HELX", "ARCL")

    def available(self) -> bool:
        return True

    def fetch(self, ticker: str) -> CompanyFundamentals:
        key = ticker.strip().upper()
        key = ALIASES.get(key, key)
        payload = _COMPANIES.get(key)
        if payload is None:
            raise DataProviderError(
                f"{ticker!r} is not in the offline demo universe "
                f"({', '.join(self.universe)}). Demo companies are fictional. "
                "For real tickers set STRATA_API_KEY / OPENAI_API_KEY and use the "
                "yfinance or JSON provider."
            )
        profile = CompanyProfile(
            **payload["profile"], data_source="demo-universe", data_quality="synthetic"
        )
        profile.notes.append(
            "Synthetic statements for a fictional company; every figure is illustrative."
        )
        years = [FinancialYear(**year) for year in payload["years"]]
        return CompanyFundamentals(
            profile=profile, fiscal_years=years, peers=list(payload["peers"])
        )
