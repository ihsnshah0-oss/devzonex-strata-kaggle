"""Bring-your-own fundamentals from local JSON files.

Two layouts are supported inside ``STRATA_RESEARCH_DATA_DIR``:

1. ``<TICKER>.json`` holding one object shaped like ``CompanyFundamentals``.
2. ``companies.json`` (or any ``*.json``) holding ``{"companies": [...]}``.

All figures are in millions of the reporting currency, matching
:class:`strata_research.schemas.FinancialYear`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import CompanyFundamentals
from .base import DataProviderError, ProviderUnavailable, to_number


def _coerce_company(payload: dict, fallback_ticker: str | None, source: Path) -> CompanyFundamentals:
    if not isinstance(payload, dict):
        raise DataProviderError(f"{source.name}: each company must be an object")
    data = dict(payload)
    profile = dict(data.get("profile") or {})
    profile.setdefault("ticker", fallback_ticker or "")
    profile.setdefault("name", profile.get("ticker") or "Unknown")
    profile.setdefault("data_source", f"json:{source.name}")
    profile.setdefault("data_quality", "reported")
    years = data.get("fiscal_years") or data.get("years") or []
    if not years:
        raise DataProviderError(f"{source.name}: company has no fiscal_years")
    cleaned_years = []
    for year in years:
        record = {key: to_number(value) for key, value in dict(year).items()}
        if record.get("fiscal_year") is None:
            raise DataProviderError(f"{source.name}: a fiscal year is missing 'fiscal_year'")
        record["fiscal_year"] = int(record["fiscal_year"])
        # Keep only fields the schema knows about.
        cleaned_years.append(record)
    try:
        company = CompanyFundamentals(
            profile=profile,
            fiscal_years=cleaned_years,
            peers=list(data.get("peers") or []),
        )
    except Exception as exc:  # pragma: no cover - surfaced as a clear provider error
        raise DataProviderError(f"{source.name}: invalid company payload: {exc}") from exc
    company.profile.notes.append(f"Loaded from local file {source.name}.")
    return company


class JsonProvider:
    name = "json"
    requires_network = False

    def __init__(self, data_dir: Path | None) -> None:
        self.data_dir = Path(data_dir) if data_dir else None
        self._index: dict[str, CompanyFundamentals] | None = None

    def available(self) -> bool:
        return bool(self.data_dir and self.data_dir.is_dir())

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
                raise DataProviderError(f"Cannot parse {path.name}: {exc}") from exc
            if isinstance(payload, dict) and "companies" in payload:
                for entry in payload.get("companies") or []:
                    company = _coerce_company(entry, None, path)
                    index[company.profile.ticker] = company
            elif isinstance(payload, dict) and (
                "profile" in payload or "fiscal_years" in payload or "years" in payload
            ):
                company = _coerce_company(payload, path.stem.upper(), path)
                index[company.profile.ticker] = company
        self._index = index
        return index

    def fetch(self, ticker: str) -> CompanyFundamentals:
        if not self.available():
            raise ProviderUnavailable(
                "No STRATA_RESEARCH_DATA_DIR configured for the JSON provider."
            )
        index = self._load()
        key = ticker.strip().upper()
        if key not in index:
            raise DataProviderError(
                f"{key} not found in {self.data_dir} "
                f"(available: {', '.join(sorted(index)) or 'none'})"
            )
        return index[key].model_copy(deep=True)
