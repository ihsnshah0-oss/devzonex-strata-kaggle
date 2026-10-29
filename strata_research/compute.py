"""Deterministic financial ratio engine.

Nothing here calls an LLM. Every number the analyst agent is allowed to cite has
to exist in the :class:`RatioSet` produced by :func:`compute_ratios`, which is
what makes the grounding check meaningful.

Convention: margins, growth rates, yields and returns are stored as
**fractions** (``0.1612`` == 16.12%). Multiples are stored as multiples
(``19.8`` == 19.8x). Balance-sheet and income-statement items are in millions.
"""

from __future__ import annotations

from .schemas import CompanyFundamentals, FinancialYear, RatioSet


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _cagr(first: float | None, last: float | None, years: int) -> float | None:
    if first is None or last is None or years <= 0:
        return None
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def ebitda_for(year: FinancialYear) -> float | None:
    if year.operating_income is not None and year.depreciation_amortization is not None:
        return year.operating_income + year.depreciation_amortization
    if year.net_income is not None:
        parts = [year.net_income, year.interest_expense, year.income_tax_expense,
                 year.depreciation_amortization]
        if all(part is not None for part in parts):
            return sum(part for part in parts if part is not None)
    return None


def effective_tax_rate(year: FinancialYear) -> float | None:
    rate = safe_div(year.income_tax_expense, year.pretax_income)
    if rate is None:
        return None
    return min(max(rate, 0.0), 0.5)


def compute_ratios(company: CompanyFundamentals) -> RatioSet:
    profile = company.profile
    years = company.fiscal_years
    latest = years[0]
    prior = years[1] if len(years) > 1 else None
    oldest = years[-1]
    span = max(len(years) - 1, 0)
    notes: list[str] = []

    market_cap = None
    if profile.price is not None and profile.shares_outstanding is not None:
        market_cap = profile.price * profile.shares_outstanding
    net_debt = None
    if latest.total_debt is not None or latest.cash_and_equivalents is not None:
        net_debt = (latest.total_debt or 0.0) - (latest.cash_and_equivalents or 0.0)
    enterprise_value = None
    if market_cap is not None and net_debt is not None:
        enterprise_value = market_cap + net_debt

    ebitda = ebitda_for(latest)
    if ebitda is None:
        notes.append("EBITDA could not be derived (missing EBIT or D&A).")

    eps = latest.eps
    if eps is None:
        eps = safe_div(latest.net_income, profile.shares_outstanding)

    book_value_per_share = safe_div(latest.total_equity, profile.shares_outstanding)

    tax_rate = effective_tax_rate(latest)
    nopat = None
    roic = None
    if latest.operating_income is not None and tax_rate is not None:
        nopat = latest.operating_income * (1.0 - tax_rate)
        invested = None
        if latest.total_equity is not None:
            invested = (latest.total_debt or 0.0) + latest.total_equity - (
                latest.cash_and_equivalents or 0.0
            )
        roic = safe_div(nopat, invested)

    fcf = None
    if latest.operating_cash_flow is not None and latest.capex is not None:
        fcf = latest.operating_cash_flow - latest.capex

    dividend_per_share = profile.dividend_per_share
    dividend_yield = None
    payout_ratio = None
    if dividend_per_share is not None and profile.price:
        dividend_yield = dividend_per_share / profile.price
        if latest.net_income:
            payout_ratio = safe_div(
                dividend_per_share * (profile.shares_outstanding or 0.0),
                latest.net_income,
            )

    revenue_growth = None
    eps_growth = None
    if prior is not None:
        revenue_growth = safe_div(
            (latest.revenue - prior.revenue)
            if latest.revenue is not None and prior.revenue is not None
            else None,
            prior.revenue,
        )
        prior_eps = prior.eps
        eps_growth = safe_div(
            (eps - prior_eps) if eps is not None and prior_eps is not None else None,
            abs(prior_eps) if prior_eps else None,
        )

    ratios = RatioSet(
        market_cap=_round(market_cap),
        enterprise_value=_round(enterprise_value),
        net_debt=_round(net_debt),
        ebitda=_round(ebitda),
        book_value_per_share=_round(book_value_per_share),
        gross_margin=_round(safe_div(latest.gross_profit, latest.revenue)),
        operating_margin=_round(safe_div(latest.operating_income, latest.revenue)),
        net_margin=_round(safe_div(latest.net_income, latest.revenue)),
        roe=_round(safe_div(latest.net_income, latest.total_equity)),
        roa=_round(safe_div(latest.net_income, latest.total_assets)),
        roic=_round(roic),
        current_ratio=_round(safe_div(latest.current_assets, latest.current_liabilities)),
        quick_ratio=_round(
            safe_div(
                (latest.current_assets - (latest.inventory or 0.0))
                if latest.current_assets is not None
                else None,
                latest.current_liabilities,
            )
        ),
        debt_to_equity=_round(safe_div(latest.total_debt, latest.total_equity)),
        net_debt_to_ebitda=_round(safe_div(net_debt, ebitda)),
        interest_coverage=_round(safe_div(latest.operating_income, latest.interest_expense)),
        revenue_growth_yoy=_round(revenue_growth),
        eps_growth_yoy=_round(eps_growth),
        revenue_cagr=_round(_cagr(oldest.revenue, latest.revenue, span)) if span else None,
        eps_cagr=_round(_cagr(oldest.eps, eps, span)) if span else None,
        fcf=_round(fcf),
        fcf_margin=_round(safe_div(fcf, latest.revenue)),
        fcf_conversion=_round(
            safe_div(fcf, latest.net_income)
            if latest.net_income is not None and latest.net_income > 0
            else None
        ),
        pe=_round(safe_div(profile.price, eps)),
        ps=_round(safe_div(market_cap, latest.revenue)),
        pb=_round(safe_div(market_cap, latest.total_equity)),
        ev_ebitda=_round(safe_div(enterprise_value, ebitda)),
        fcf_yield=_round(safe_div(fcf, market_cap)),
        dividend_yield=_round(dividend_yield),
        payout_ratio=_round(payout_ratio),
        basis_year=latest.fiscal_year,
        prior_year=prior.fiscal_year if prior else None,
        cagr_years=span or None,
        notes=notes,
    )
    if profile.price is None or profile.shares_outstanding is None:
        ratios.notes.append(
            "Market price or share count missing; valuation multiples are unavailable."
        )
    if span == 0:
        ratios.notes.append("Only one fiscal year available; no growth metrics.")
    ratios.notes.extend(profile.notes)
    return ratios


def margin_trend(company: CompanyFundamentals, field: str) -> list[float | None]:
    """Return a per-year margin history for ``gross``/``operating``/``net``."""
    mapping = {
        "gross": ("gross_profit",),
        "operating": ("operating_income",),
        "net": ("net_income",),
    }
    keys = mapping.get(field)
    if not keys:
        return []
    history: list[float | None] = []
    for year in reversed(company.fiscal_years):  # oldest first
        ratios = [safe_div(getattr(year, key), year.revenue) for key in keys]
        value = ratios[0] if ratios else None
        history.append(_round(value))
    return history


def ratio_lines(ratios: RatioSet, currency: str = "") -> list[tuple[str, str]]:
    """Human-readable ``(label, formatted value)`` pairs for prompts and UI."""
    from .formatting import fmt_money, fmt_pct, fmt_per_share, fmt_x

    def money(value: float | None) -> str:
        return fmt_money(value, currency=currency)

    return [
        ("Market cap", money(ratios.market_cap)),
        ("Enterprise value", money(ratios.enterprise_value)),
        ("Net debt", money(ratios.net_debt)),
        ("EBITDA", money(ratios.ebitda)),
        ("Revenue growth YoY", fmt_pct(ratios.revenue_growth_yoy, signed=True)),
        ("EPS growth YoY", fmt_pct(ratios.eps_growth_yoy, signed=True)),
        (f"Revenue CAGR ({ratios.cagr_years or 0}y)", fmt_pct(ratios.revenue_cagr)),
        (f"EPS CAGR ({ratios.cagr_years or 0}y)", fmt_pct(ratios.eps_cagr)),
        ("Gross margin", fmt_pct(ratios.gross_margin)),
        ("Operating margin", fmt_pct(ratios.operating_margin)),
        ("Net margin", fmt_pct(ratios.net_margin)),
        ("ROE", fmt_pct(ratios.roe)),
        ("ROA", fmt_pct(ratios.roa)),
        ("ROIC", fmt_pct(ratios.roic)),
        ("Current ratio", fmt_x(ratios.current_ratio, 2)),
        ("Quick ratio", fmt_x(ratios.quick_ratio, 2)),
        ("Debt / equity", fmt_x(ratios.debt_to_equity, 2)),
        ("Net debt / EBITDA", fmt_x(ratios.net_debt_to_ebitda)),
        ("Interest coverage", fmt_x(ratios.interest_coverage)),
        ("Free cash flow", money(ratios.fcf)),
        ("FCF margin", fmt_pct(ratios.fcf_margin)),
        ("FCF conversion (FCF/NI)", fmt_pct(ratios.fcf_conversion)),
        ("P/E", fmt_x(ratios.pe)),
        ("P/S", fmt_x(ratios.ps)),
        ("P/B", fmt_x(ratios.pb)),
        ("EV/EBITDA", fmt_x(ratios.ev_ebitda)),
        ("FCF yield", fmt_pct(ratios.fcf_yield)),
        ("Dividend yield", fmt_pct(ratios.dividend_yield)),
        ("Payout ratio", fmt_pct(ratios.payout_ratio)),
        ("Book value / share", fmt_per_share(ratios.book_value_per_share, currency)),
    ]
