"""Deterministic offline demo universe of **fictional PSX-listed companies**.

Nothing here is real market data: every name, statement and price is invented so
the desk can be demonstrated and tested without network access. Statements are in
**millions of PKR** and the companies are chosen to span the PSX sectors a
fundamental analyst actually meets:

* ``DMEPL`` — Oil & Gas Exploration: net cash, high margins, low multiple.
* ``DMFRT`` — Fertilizer: high margin dividend payer.
* ``DMCMT`` — Cement: cyclical, leveraged, interest cover under pressure.
* ``DMPWR`` — Power Generation: IPP with circular-debt style leverage.

Real PSX symbols need the ``psx`` provider (local statements) or the ``yfinance``
provider (``<SYMBOL>.KA`` listings); nothing in this module should be quoted as
market fact.
"""

from __future__ import annotations

from ..schemas import CompanyFundamentals, CompanyProfile, FinancialYear
from .base import DataProviderError

_COMPANIES: dict[str, dict] = {
    "DMEPL": {
        "profile": {
            "ticker": "DMEPL",
            "name": "Demo Petroleum Exploration Ltd. (fiction)",
            "sector": "Oil & Gas Exploration",
            "industry": "Oil & Gas Exploration Companies",
            "country": "Pakistan",
            "currency": "PKR",
            "price": 165.0,
            "shares_outstanding": 4300.0,
            "dividend_per_share": 12.0,
            "beta": 1.05,
            "description": (
                "Fictional upstream oil and gas producer with three operated fields "
                "and a gas processing plant; revenue is USD-linked through a "
                "government-set gas price formula."
            ),
        },
        "peers": ["OGDC", "PPL", "POL"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 420000.0, "gross_profit": 210000.0,
                "operating_income": 150000.0, "pretax_income": 148000.0,
                "income_tax_expense": 44400.0, "net_income": 103600.0, "eps": 24.09,
                "interest_expense": 3000.0, "depreciation_amortization": 28000.0,
                "total_assets": 640000.0, "total_equity": 420000.0, "total_debt": 40000.0,
                "cash_and_equivalents": 190000.0, "current_assets": 260000.0,
                "current_liabilities": 150000.0, "inventory": 45000.0,
                "operating_cash_flow": 150000.0, "capex": 45000.0,
            },
            {
                "fiscal_year": 2024, "revenue": 390000.0, "gross_profit": 190000.0,
                "operating_income": 138000.0, "pretax_income": 136000.0,
                "income_tax_expense": 40800.0, "net_income": 95200.0, "eps": 22.14,
                "interest_expense": 3200.0, "depreciation_amortization": 26000.0,
                "total_assets": 610000.0, "total_equity": 390000.0, "total_debt": 45000.0,
                "cash_and_equivalents": 170000.0, "current_assets": 245000.0,
                "current_liabilities": 145000.0, "inventory": 42000.0,
                "operating_cash_flow": 140000.0, "capex": 42000.0,
            },
            {
                "fiscal_year": 2023, "revenue": 355000.0, "gross_profit": 170000.0,
                "operating_income": 124000.0, "pretax_income": 122000.0,
                "income_tax_expense": 36600.0, "net_income": 85400.0, "eps": 19.86,
                "interest_expense": 3400.0, "depreciation_amortization": 24000.0,
                "total_assets": 580000.0, "total_equity": 360000.0, "total_debt": 50000.0,
                "cash_and_equivalents": 150000.0, "current_assets": 230000.0,
                "current_liabilities": 140000.0, "inventory": 40000.0,
                "operating_cash_flow": 128000.0, "capex": 40000.0,
            },
        ],
    },
    "DMFRT": {
        "profile": {
            "ticker": "DMFRT",
            "name": "Demo Fertilizer Company Ltd. (fiction)",
            "sector": "Fertilizer",
            "industry": "Fertilizer",
            "country": "Pakistan",
            "currency": "PKR",
            "price": 320.0,
            "shares_outstanding": 1200.0,
            "dividend_per_share": 30.0,
            "beta": 0.90,
            "description": (
                "Fictional urea producer with 1.2 million tonnes of annual capacity, "
                "gas supplied under a fixed allocation and a long history of high "
                "dividend payouts."
            ),
        },
        "peers": ["FFC", "EFERT", "FATIMA"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 180000.0, "gross_profit": 78000.0,
                "operating_income": 62000.0, "pretax_income": 63000.0,
                "income_tax_expense": 18900.0, "net_income": 44100.0, "eps": 36.75,
                "interest_expense": 1500.0, "depreciation_amortization": 9000.0,
                "total_assets": 290000.0, "total_equity": 195000.0, "total_debt": 32000.0,
                "cash_and_equivalents": 70000.0, "current_assets": 120000.0,
                "current_liabilities": 62000.0, "inventory": 28000.0,
                "operating_cash_flow": 66000.0, "capex": 18000.0,
            },
            {
                "fiscal_year": 2024, "revenue": 165000.0, "gross_profit": 70000.0,
                "operating_income": 55000.0, "pretax_income": 56000.0,
                "income_tax_expense": 16800.0, "net_income": 39200.0, "eps": 32.67,
                "interest_expense": 1700.0, "depreciation_amortization": 8600.0,
                "total_assets": 275000.0, "total_equity": 180000.0, "total_debt": 35000.0,
                "cash_and_equivalents": 62000.0, "current_assets": 112000.0,
                "current_liabilities": 60000.0, "inventory": 26000.0,
                "operating_cash_flow": 60000.0, "capex": 17000.0,
            },
            {
                "fiscal_year": 2023, "revenue": 148000.0, "gross_profit": 61000.0,
                "operating_income": 47000.0, "pretax_income": 48000.0,
                "income_tax_expense": 14400.0, "net_income": 33600.0, "eps": 28.00,
                "interest_expense": 1900.0, "depreciation_amortization": 8200.0,
                "total_assets": 262000.0, "total_equity": 165000.0, "total_debt": 38000.0,
                "cash_and_equivalents": 55000.0, "current_assets": 105000.0,
                "current_liabilities": 58000.0, "inventory": 24000.0,
                "operating_cash_flow": 54000.0, "capex": 16000.0,
            },
        ],
    },
    "DMCMT": {
        "profile": {
            "ticker": "DMCMT",
            "name": "Demo Cement Works Ltd. (fiction)",
            "sector": "Cement",
            "industry": "Cement",
            "country": "Pakistan",
            "currency": "PKR",
            "price": 145.0,
            "shares_outstanding": 700.0,
            "dividend_per_share": 5.0,
            "beta": 1.20,
            "description": (
                "Fictional north-zone cement producer running two lines at about "
                "78% utilisation, exposed to coal prices, freight and the domestic "
                "construction cycle."
            ),
        },
        "peers": ["LUCK", "MLCF", "CHCC"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 95000.0, "gross_profit": 26600.0,
                "operating_income": 17100.0, "pretax_income": 11400.0,
                "income_tax_expense": 3420.0, "net_income": 7980.0, "eps": 11.40,
                "interest_expense": 7600.0, "depreciation_amortization": 8000.0,
                "total_assets": 190000.0, "total_equity": 78000.0, "total_debt": 62000.0,
                "cash_and_equivalents": 9000.0, "current_assets": 38000.0,
                "current_liabilities": 30000.0, "inventory": 14000.0,
                "operating_cash_flow": 18000.0, "capex": 12000.0,
            },
            {
                "fiscal_year": 2024, "revenue": 92000.0, "gross_profit": 27600.0,
                "operating_income": 19320.0, "pretax_income": 14720.0,
                "income_tax_expense": 4121.0, "net_income": 10599.0, "eps": 15.14,
                "interest_expense": 6800.0, "depreciation_amortization": 7600.0,
                "total_assets": 186000.0, "total_equity": 76000.0, "total_debt": 58000.0,
                "cash_and_equivalents": 8000.0, "current_assets": 37000.0,
                "current_liabilities": 29500.0, "inventory": 13200.0,
                "operating_cash_flow": 20000.0, "capex": 11000.0,
            },
            {
                "fiscal_year": 2023, "revenue": 86000.0, "gross_profit": 27520.0,
                "operating_income": 20640.0, "pretax_income": 16512.0,
                "income_tax_expense": 4623.0, "net_income": 11889.0, "eps": 16.98,
                "interest_expense": 6000.0, "depreciation_amortization": 7200.0,
                "total_assets": 180000.0, "total_equity": 74000.0, "total_debt": 54000.0,
                "cash_and_equivalents": 7500.0, "current_assets": 36000.0,
                "current_liabilities": 29000.0, "inventory": 12500.0,
                "operating_cash_flow": 21500.0, "capex": 10000.0,
            },
        ],
    },
    "DMPWR": {
        "profile": {
            "ticker": "DMPWR",
            "name": "Demo Power Generation Ltd. (fiction)",
            "sector": "Power Generation",
            "industry": "Power Generation & Distribution",
            "country": "Pakistan",
            "currency": "PKR",
            "price": 28.0,
            "shares_outstanding": 2000.0,
            "dividend_per_share": 0.0,
            "beta": 1.30,
            "description": (
                "Fictional independent power producer operating a 450 MW furnace-oil "
                "and gas plant under a capacity-purchase arrangement, with a large "
                "receivable balance from the power chain."
            ),
        },
        "peers": ["HUBC", "KEL", "NCPL"],
        "years": [
            {
                "fiscal_year": 2025, "revenue": 210000.0, "gross_profit": 42000.0,
                "operating_income": 30000.0, "pretax_income": 9000.0,
                "income_tax_expense": 2700.0, "net_income": 6300.0, "eps": 3.15,
                "interest_expense": 21000.0, "depreciation_amortization": 24000.0,
                "total_assets": 620000.0, "total_equity": 120000.0, "total_debt": 390000.0,
                "cash_and_equivalents": 18000.0, "current_assets": 95000.0,
                "current_liabilities": 130000.0, "inventory": 22000.0,
                "operating_cash_flow": 34000.0, "capex": 26000.0,
            },
            {
                "fiscal_year": 2024, "revenue": 205000.0, "gross_profit": 45000.0,
                "operating_income": 33000.0, "pretax_income": 14000.0,
                "income_tax_expense": 4200.0, "net_income": 9800.0, "eps": 4.90,
                "interest_expense": 19500.0, "depreciation_amortization": 23500.0,
                "total_assets": 610000.0, "total_equity": 118000.0, "total_debt": 380000.0,
                "cash_and_equivalents": 16000.0, "current_assets": 92000.0,
                "current_liabilities": 128000.0, "inventory": 21000.0,
                "operating_cash_flow": 32000.0, "capex": 25000.0,
            },
            {
                "fiscal_year": 2023, "revenue": 198000.0, "gross_profit": 47000.0,
                "operating_income": 36000.0, "pretax_income": 18600.0,
                "income_tax_expense": 5580.0, "net_income": 13020.0, "eps": 6.51,
                "interest_expense": 18000.0, "depreciation_amortization": 23000.0,
                "total_assets": 600000.0, "total_equity": 116000.0, "total_debt": 370000.0,
                "cash_and_equivalents": 15000.0, "current_assets": 90000.0,
                "current_liabilities": 126000.0, "inventory": 20000.0,
                "operating_cash_flow": 30000.0, "capex": 24000.0,
            },
        ],
    },
}

ALIASES = {"DEMO": "DMEPL", "PSX": "DMEPL", "EXAMPLE": "DMEPL"}


class DemoProvider:
    """Serves the fictional PSX-style universe; no network access required."""

    name = "demo"
    requires_network = False

    def __init__(self) -> None:
        self.universe = tuple(_COMPANIES)

    def available(self) -> bool:
        return True

    def universe_summary(self) -> list[dict[str, str]]:
        return [
            {
                "ticker": payload["profile"]["ticker"],
                "name": payload["profile"]["name"],
                "sector": payload["profile"]["sector"],
            }
            for payload in _COMPANIES.values()
        ]

    def fetch(self, ticker: str) -> CompanyFundamentals:
        key = ticker.strip().upper()
        key = ALIASES.get(key, key)
        payload = _COMPANIES.get(key)
        if payload is None:
            raise DataProviderError(
                f"{ticker!r} is not in the offline PSX demo universe "
                f"({', '.join(self.universe)}). These are fictional companies. "
                "For a real PSX symbol, set STRATA_RESEARCH_PSX_DIR with that "
                "company's statements, or install the live provider "
                "(pip install 'devzonex-strata-kaggle[live]') to read <SYMBOL>.KA."
            )
        profile = CompanyProfile(
            **payload["profile"], data_source="psx-demo-universe", data_quality="synthetic"
        )
        profile.notes.append(
            "Fictional PSX-listed company; all statements and prices are illustrative, "
            "in millions of PKR."
        )
        years = [FinancialYear(**year) for year in payload["years"]]
        return CompanyFundamentals(
            profile=profile, fiscal_years=years, peers=list(payload["peers"])
        )
