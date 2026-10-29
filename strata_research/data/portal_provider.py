"""Fundamentals straight out of the PSX Data Portal mirror.

The desk used to demand hand-keyed statements (``STRATA_RESEARCH_PSX_DIR``) before it
would analyse a real PSX symbol, which is why ``analyze OGDC`` answered "not in the
offline demo universe". This provider closes that gap honestly: it reads
``data/psx.db`` — the mirror built from ``https://dps.psx.com.pk`` by
``python -m strata_research.psxdb ingest`` — and shapes what the portal actually
publishes into the desk's statement contract.

What the portal gives us, per company (see ``docs/psx-database.md``):

* a price snapshot (close, prev close, day range, 52-week range, P/E, dividend
  yield, shares, free float, market cap);
* annual and quarterly rows for Sales, Profit after Taxation, EPS and the margins
  the portal publishes ("Gross Profit Margin (%)", "Net Profit Margin (%)");
* index membership.

What it does **not** give us: balance sheet, cash flow, EBITDA, interest expense.
Those fields stay ``None``; the ratio engine reports ``n/a`` and the report says
so instead of inventing them. Values on the portal are in **thousands of PKR**, so
everything except EPS is divided by 1 000 to reach the desk's millions of PKR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..psx import expand_mirror, normalize_symbol
from ..schemas import CompanyFundamentals, CompanyProfile, FinancialYear
from .base import DataProviderError

#: The portal prints monetary values in thousands of rupees.
PORTAL_MONEY_DIVISOR = 1_000.0

#: Annual metrics that share a name with a desk statement field.
_ANNUAL_FIELDS = {
    "revenue": "revenue",
    "total_income": "revenue",
    "mark_up_earned": "revenue",
    "net_income": "net_income",
}

_PORTAL_NOTE = (
    "Statements read from the PSX Data Portal (dps.psx.com.pk) mirror: Sales, "
    "Profit after Taxation, EPS and published margins, in thousands of PKR "
    "converted to millions. No balance sheet, cash flow or EBITDA is published, "
    "so those ratios are n/a rather than estimated."
)


def _millions(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / PORTAL_MONEY_DIVISOR


class PortalStatementsProvider:
    """Real PSX companies, from the portal mirror. Offline, no API key."""

    name = "portal"
    requires_network = False

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path else None

    # ------------------------------------------------------------------
    def _mirror_path(self) -> Path | None:
        from ..psxdb.store import DEFAULT_DB_PATH

        path = Path(self.db_path or DEFAULT_DB_PATH)
        if path.exists():
            return path
        return expand_mirror(path)

    def _database(self):
        path = self._mirror_path()
        if path is None:
            return None
        from ..psxdb.store import PsxDatabase

        return PsxDatabase(path)

    def available(self) -> bool:
        try:
            path = self._mirror_path()
        except Exception:  # a broken mirror must not break provider selection
            return False
        return path is not None

    # ------------------------------------------------------------------
    def universe(self) -> list[dict[str, str]]:
        database = self._database()
        if database is None:
            return []
        try:
            from ..psxdb.query import symbols as db_symbols

            return [
                {
                    "ticker": row["symbol"],
                    "name": row["name"] or row["symbol"],
                    "sector": row["sector"] or "n/a",
                }
                for row in db_symbols(database)
            ]
        finally:
            database.close()

    def _periods(self, symbol: str) -> dict[str, Any]:
        database = self._database()
        if database is None:
            raise DataProviderError(
                "No PSX mirror found. Build one with "
                "`python -m strata_research.psxdb ingest` (portal only)."
            )
        try:
            from ..psxdb.query import run_fundamentals

            return run_fundamentals(database, symbol=symbol)
        finally:
            database.close()

    # ------------------------------------------------------------------
    def fetch(self, ticker: str) -> CompanyFundamentals:
        symbol = normalize_symbol(ticker)
        payload = self._periods(symbol)
        profile_row = payload.get("profile")
        periods = payload.get("periods") or []
        if not profile_row:
            raise DataProviderError(f"{symbol} is not listed in the PSX mirror")
        annual = [period for period in periods if not period.get("quarter")]
        if not annual:
            raise DataProviderError(
                f"{symbol}: the PSX Data Portal publishes no annual financials for this "
                "company, so a fundamental report would be guesswork. Supply statements "
                "via STRATA_RESEARCH_PSX_DIR instead."
            )

        snapshot = payload.get("snapshot") or {}
        last_close = payload.get("last_close") or {}
        price = snapshot.get("price") or last_close.get("close")
        shares = snapshot.get("shares")
        dividend_yield = snapshot.get("dividend_yield")
        notes = list(_PORTAL_NOTE.split(". "))

        years: list[FinancialYear] = []
        for period in sorted(annual, key=lambda item: item.get("fiscal_year") or 0):
            metrics = period.get("metrics") or {}
            fiscal_year = period.get("fiscal_year")
            if not fiscal_year:
                continue
            record: dict[str, Any] = {"fiscal_year": int(fiscal_year)}
            for metric, value in metrics.items():
                field = _ANNUAL_FIELDS.get(metric)
                if field and record.get(field) is None:
                    record[field] = _millions(value)
            record["eps"] = metrics.get("eps")
            gross_margin = metrics.get("gross_margin_pct")
            if gross_margin is not None and record.get("revenue") is not None:
                # The portal publishes the margin, not the profit: this is arithmetic on
                # two published numbers, and it is labelled as such below.
                record["gross_profit"] = record["revenue"] * float(gross_margin) / 100.0
            years.append(FinancialYear(**record))

        if not any(year.revenue or year.net_income for year in years):
            raise DataProviderError(
                f"{symbol}: the mirror holds no Sales/Profit rows for this company."
            )

        profile = CompanyProfile(
            ticker=symbol,
            name=profile_row.get("name") or symbol,
            sector=profile_row.get("sector"),
            description=None,
            price=price,
            shares_outstanding=(shares / 1_000_000.0) if shares else None,
            dividend_per_share=(
                price * float(dividend_yield) / 100.0
                if price and dividend_yield
                else None
            ),
            as_of=str(snapshot.get("as_of") or last_close.get("trade_date") or ""),
            data_source="psx-portal",
            data_quality="reported",
        )
        profile.notes.extend(notes)
        if snapshot.get("market_cap"):
            profile.notes.append(
                f"Market cap {snapshot['market_cap']:,.0f} PKR as published by the portal "
                "(converted from thousands)."
            )
        if payload.get("indices"):
            profile.notes.append(
                "Index membership: " + ", ".join(payload["indices"]) + "."
            )
        if profile.dividend_per_share:
            profile.notes.append(
                "Dividend per share derived from the portal's dividend-yield snapshot."
            )
        profile.notes.append(
            "Gross profit derived from the portal's published Gross Profit Margin (%)."
        )
        portal_pe = snapshot.get("pe")
        latest_eps = years[-1].eps if years else None
        if portal_pe and latest_eps and price:
            computed_pe = price / latest_eps if latest_eps > 0 else None
            if computed_pe and (computed_pe / portal_pe > 2.5 or portal_pe / computed_pe > 2.5):
                profile.notes.append(
                    f"The portal publishes P/E (TTM) of {portal_pe:.2f}x, while the latest "
                    f"annual EPS of {latest_eps:.2f} gives {computed_pe:.1f}x — the annual "
                    "column looks like a partial, restated or transitional period. The ratio "
                    "engine uses the annual EPS; treat the multiple with caution."
                )
        quarterly = [period["period"] for period in periods if period.get("quarter")]
        if quarterly:
            profile.notes.append("Quarterly periods on the portal: " + ", ".join(quarterly) + ".")

        return CompanyFundamentals(profile=profile, fiscal_years=years, peers=[])


__all__ = ["PortalStatementsProvider"]
