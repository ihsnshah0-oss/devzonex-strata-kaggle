"""Live fundamentals via the optional ``yfinance`` package.

``yfinance`` is an optional dependency: the rest of the desk works without it.
Field labels differ between companies, so every statement line is read from a
list of candidate labels and anything missing is simply reported as ``None``.
"""

from __future__ import annotations

from typing import Any

from ..schemas import CompanyFundamentals, CompanyProfile, FinancialYear
from .base import DataProviderError, ProviderUnavailable, to_number

INCOME_LABELS = {
    "revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income", "EBIT", "Total Operating Income As Reported"),
    "pretax_income": ("Pretax Income", "Income Before Tax"),
    "income_tax_expense": ("Tax Provision", "Income Tax Expense"),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "eps": ("Diluted EPS", "Basic EPS"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "depreciation_amortization": (
        "Reconciled Depreciation",
        "Depreciation And Amortization",
        "Depreciation",
    ),
}

BALANCE_LABELS = {
    "total_assets": ("Total Assets",),
    "total_equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    "total_debt": ("Total Debt",),
    "cash_and_equivalents": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "inventory": ("Inventory",),
}

CASHFLOW_LABELS = {
    "operating_cash_flow": ("Operating Cash Flow", "Total Cash From Operating Activities"),
    "capex": ("Capital Expenditure", "Capital Expenditures"),
}


def _import_yfinance() -> Any:
    try:
        import yfinance  # noqa: F401  (imported for side-effect free availability check)
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ProviderUnavailable(
            "yfinance is not installed. Install it with "
            "`pip install strata-research[live]` or use the demo/JSON provider."
        ) from exc
    return yfinance


def _frame_lookup(frame: Any, labels: tuple[str, ...], column: Any) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        available = set(frame.index)
    except TypeError:
        return None
    for label in labels:
        if label in available:
            try:
                value = frame.at[label, column]
            except (KeyError, ValueError):
                continue
            number = to_number(value)
            if number is not None:
                return number
    return None


def _year_of(column: Any) -> int | None:
    for attr in ("year",):
        value = getattr(column, attr, None)
        if isinstance(value, int):
            return value
    text = str(column)
    digits = "".join(ch for ch in text[:4] if ch.isdigit())
    return int(digits) if len(digits) == 4 else None


class YFinanceProvider:
    name = "yfinance"
    requires_network = True

    def available(self) -> bool:
        try:
            _import_yfinance()
        except ProviderUnavailable:
            return False
        return True

    def fetch(self, ticker: str) -> CompanyFundamentals:
        yf = _import_yfinance()
        symbol = ticker.strip().upper()
        try:
            handle = yf.Ticker(symbol)
            income = handle.income_stmt
            balance = handle.balance_sheet
            cashflow = handle.cashflow
        except Exception as exc:
            raise DataProviderError(f"yfinance failed for {symbol}: {exc}") from exc

        columns: list[Any] = []
        if income is not None and not getattr(income, "empty", True):
            columns = list(income.columns)
        if not columns and cashflow is not None and not getattr(cashflow, "empty", True):
            columns = list(cashflow.columns)

        years: list[FinancialYear] = []
        for column in columns[:4]:
            fiscal_year = _year_of(column)
            if fiscal_year is None:
                continue
            record: dict[str, Any] = {"fiscal_year": fiscal_year}
            for target, labels in INCOME_LABELS.items():
                record[target] = _frame_lookup(income, labels, column)
            for target, labels in BALANCE_LABELS.items():
                record[target] = _frame_lookup(balance, labels, column)
            for target, labels in CASHFLOW_LABELS.items():
                record[target] = _frame_lookup(cashflow, labels, column)
            capex = record.get("capex")
            if capex is not None and capex < 0:
                record["capex"] = abs(capex)
            years.append(FinancialYear(**record))

        if not years:
            raise DataProviderError(
                f"yfinance returned no annual statements for {symbol}."
            )

        info: dict[str, Any] = {}
        try:
            info = handle.info or {}
        except Exception:
            info = {}
        price = to_number(info.get("currentPrice")) or to_number(info.get("regularMarketPrice"))
        shares = to_number(info.get("sharesOutstanding"))
        if shares is not None:
            shares = shares / 1_000_000  # to millions
        if price is None or shares is None:
            try:
                fast = handle.fast_info
                price = price or to_number(fast.get("last_price"))
                raw_shares = to_number(fast.get("shares"))
                shares = shares or (raw_shares / 1_000_000 if raw_shares else None)
            except Exception:
                pass

        profile = CompanyProfile(
            ticker=symbol,
            name=info.get("longName") or info.get("shortName") or symbol,
            sector=info.get("sector"),
            industry=info.get("industry"),
            country=info.get("country"),
            currency=info.get("currency") or "USD",
            description=(info.get("longBusinessSummary") or "")[:1200] or None,
            price=price,
            shares_outstanding=shares,
            dividend_per_share=to_number(info.get("dividendRate")),
            beta=to_number(info.get("beta")),
            data_source="yfinance",
            data_quality="reported",
        )
        profile.notes.append(
            "Figures fetched from Yahoo Finance via yfinance; verify against the "
            "company's filings before relying on them."
        )
        return CompanyFundamentals(profile=profile, fiscal_years=years, peers=[])
