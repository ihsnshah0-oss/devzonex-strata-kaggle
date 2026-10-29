"""PSX statements provider.

Real PSX fundamentals are not available from a stable, documented public API, so
this provider takes the honest route: it reads statements you supply as JSON —
from the PSX Data Portal financial reports or the company's annual report — and
optionally enriches the price from the live PSX Data Portal quote feed.

Folder layout (``STRATA_RESEARCH_PSX_DIR``)::

    data/psx/
      DMEPL.json        # one company per file, or...
      companies.json    # ...one aggregate file with {"companies": [...]}

Each company accepts an optional ``"units"`` key describing the statements
(``"thousands"`` is what most PSX annual reports use; ``"millions"`` is the
default; ``"crore"``, ``"lakh"``, ``"billions"`` and ``"units"`` also work).
Everything is converted to millions of PKR internally.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..psx import normalize_symbol, scale_statements, yahoo_symbol
from ..schemas import CompanyFundamentals, CompanyProfile, FinancialYear
from .base import DataProviderError, to_number

STATEMENT_FIELDS = {
    "revenue", "gross_profit", "operating_income", "pretax_income",
    "income_tax_expense", "net_income", "eps", "interest_expense",
    "depreciation_amortization", "total_assets", "total_equity", "total_debt",
    "cash_and_equivalents", "current_assets", "current_liabilities", "inventory",
    "operating_cash_flow", "capex",
}
def _coerce_company(payload: dict[str, Any], fallback_ticker: str | None,
                    source: Path) -> CompanyFundamentals:
    if not isinstance(payload, dict):
        raise DataProviderError(f"{source.name}: each company must be a JSON object")
    profile_data = dict(payload.get("profile") or {})
    ticker = normalize_symbol(profile_data.get("ticker") or fallback_ticker or "")
    profile_data["ticker"] = ticker
    profile_data.setdefault("name", ticker)
    profile_data.setdefault("currency", "PKR")
    profile_data.setdefault("country", "Pakistan")
    profile_data.setdefault("exchange", "PSX")
    profile_data.setdefault("data_source", f"psx-file:{source.name}")
    profile_data.setdefault("data_quality", "reported")

    raw_years = payload.get("fiscal_years") or payload.get("years") or []
    if not raw_years:
        raise DataProviderError(f"{source.name}: {ticker} has no fiscal_years")

    units = payload.get("units")
    cleaned: list[dict[str, Any]] = []
    for year in raw_years:
        record = dict(year)
        parsed: dict[str, Any] = {}
        for key, value in record.items():
            if key == "fiscal_year":
                number = to_number(value)
                if number is None:
                    raise DataProviderError(
                        f"{source.name}: {ticker} has a fiscal year without 'fiscal_year'"
                    )
                parsed[key] = int(number)
            elif key in STATEMENT_FIELDS:
                parsed[key] = to_number(value)
            elif key in {"period", "notes"}:
                parsed[key] = value
        cleaned.append(parsed)

    scaled = scale_statements(cleaned, units)

    try:
        company = CompanyFundamentals(
            profile=CompanyProfile(**profile_data),
            fiscal_years=[FinancialYear(**year) for year in scaled],
            peers=[normalize_symbol(peer) for peer in (payload.get("peers") or [])
                   if isinstance(peer, str) and peer.strip()],
        )
    except Exception as exc:  # surfaced as a provider error with context
        raise DataProviderError(f"{source.name}: invalid PSX company payload: {exc}") from exc

    unit_note = f"statement units: {units}" if units else "statement units: millions"
    company.profile.notes.append(
        f"Statements read from local PSX file {source.name} ({unit_note}, converted "
        "to millions of PKR). Verify against the published accounts."
    )
    return company


class PsxStatementsProvider:
    """Local PSX statements, optionally priced from the PSX Data Portal."""

    name = "psx"
    requires_network = False

    def __init__(self, data_dir: Path | None, quote_client: Any | None = None,
                 use_quotes: bool = True) -> None:
        self.data_dir = Path(data_dir).expanduser() if data_dir else None
        self.quote_client = quote_client
        self.use_quotes = use_quotes
        self._index: dict[str, CompanyFundamentals] | None = None
        self.quote_notes: list[str] = []

    # ------------------------------------------------------------------
    def available(self) -> bool:
        if not self.data_dir or not self.data_dir.is_dir():
            return False
        return any(self.data_dir.glob("*.json"))

    def _load(self) -> dict[str, CompanyFundamentals]:
        if self._index is not None:
            return self._index
        index: dict[str, CompanyFundamentals] = {}
        if not self.available():
            self._index = index
            return index
        assert self.data_dir is not None
        for path in sorted(self.data_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DataProviderError(f"Cannot read {path.name}: {exc}") from exc
            if isinstance(payload, dict) and isinstance(payload.get("companies"), list):
                for entry in payload["companies"]:
                    company = _coerce_company(entry, None, path)
                    index[company.profile.ticker] = company
            elif isinstance(payload, dict) and (
                "profile" in payload or "fiscal_years" in payload or "years" in payload
            ):
                company = _coerce_company(payload, path.stem, path)
                index[company.profile.ticker] = company
            else:
                continue
        self._index = index
        return index

    def universe(self) -> list[dict[str, str]]:
        try:
            index = self._load()
        except DataProviderError:
            return []
        return [
            {
                "ticker": company.profile.ticker,
                "name": company.profile.name,
                "sector": company.profile.sector or "n/a",
            }
            for company in sorted(index.values(), key=lambda item: item.profile.ticker)
        ]

    # ------------------------------------------------------------------
    def _price_from_feed(self, symbol: str) -> float | None:
        if not (self.use_quotes and self.quote_client is not None):
            return None
        try:
            quote = self.quote_client.quote(symbol)
        except Exception as exc:  # quotes must never break a report
            self.quote_notes.append(f"PSX quote failed for {symbol}: {exc}")
            return None
        if quote.price is None:
            error = getattr(self.quote_client, "last_error", None)
            self.quote_notes.append(
                f"No PSX quote for {symbol}" + (f": {error}" if error else ".")
            )
            return None
        self.quote_notes.append(
            f"Price for {symbol} from the PSX Data Portal"
            + (f" at {quote.as_of}" if quote.as_of else "")
            + "."
        )
        return quote.price

    def fetch(self, ticker: str) -> CompanyFundamentals:
        symbol = normalize_symbol(ticker)
        index = self._load()
        if symbol not in index:
            raise DataProviderError(
                f"{symbol} is not in {self.data_dir} "
                f"(available: {', '.join(sorted(index)) or 'none'})"
            )
        company = index[symbol].model_copy(deep=True)
        live_price = self._price_from_feed(symbol)
        if live_price is not None:
            company.profile.price = live_price
            company.profile.data_source = f"{company.profile.data_source}+psx-quote"
            company.profile.notes.append("Latest close sourced from the PSX Data Portal.")
        elif company.profile.price is None:
            company.profile.notes.append(
                "No price available: live quotes are off/unavailable and the file has "
                "no price. Set profile.price or enable STRATA_RESEARCH_PSX_QUOTES."
            )
        if not company.profile.name or company.profile.name == symbol:
            company.profile.name = symbol
        company.profile.notes.extend(note for note in self.quote_notes if note not in company.profile.notes)
        company.profile.notes.append(f"Yahoo Finance listing code for cross-checks: {yahoo_symbol(symbol)}")
        return company
