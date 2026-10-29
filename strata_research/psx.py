"""PSX (Pakistan Stock Exchange) specifics.

Everything market-specific lives here so the analyst code stays generic:

* symbol normalisation (``OGDC``, ``ogdc``, ``PSX:OGDC``, ``OGDC.KA`` -> ``OGDC``),
* the PSX sector taxonomy and sector-level risk notes,
* the Pakistan macro lens every report has to consider,
* unit conversion (annual reports are usually in PKR thousands),
* a small, dependency-free quote client for the PSX Data Portal.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

import httpx

PSX_DEFAULT_BASE_URL = "https://dps.psx.com.pk"
YAHOO_SUFFIX = ".KA"  # Yahoo Finance uses <SYMBOL>.KA for Karachi listings

#: Sectors used by the PSX data portal (grouped for research purposes).
PSX_SECTORS: dict[str, tuple[str, ...]] = {
    "Cement": ("cement",),
    "Oil & Gas Exploration": ("oil and gas exploration", "oil & gas exploration"),
    "Oil & Gas Marketing": ("oil and gas marketing", "oil & gas marketing companies"),
    "Fertilizer": ("fertilizer", "fertiliser"),
    "Power Generation": ("power generation", "power generation & distribution"),
    "Commercial Banks": ("commercial banks", "banks"),
    "Technology & Communication": ("technology", "technology & communication"),
    "Textile Composite": ("textile composite", "textile"),
    "Chemical": ("chemical",),
    "Automobile Assembler": ("automobile assembler", "autos"),
    "Food & Personal Care": ("food", "food & personal care"),
    "Engineering": ("engineering",),
    "Refinery": ("refinery",),
    "Real Estate": ("real estate",),
}

#: Sector-specific things a PSX analyst must not ignore.
SECTOR_NOTES: dict[str, str] = {
    "Cement": (
        "Cement is a domestic cycle play: despatches, coal and power cost per tonne, "
        "retention prices and capacity utilisation drive margins. High leverage is "
        "common, so interest cover matters as much as volume."
    ),
    "Oil & Gas Exploration": (
        "E&P earnings track crude and gas prices, the PKR/USD rate and the circular "
        "debt position on gas receivables. Exploration write-offs and concession "
        "renewals are the main qualitative risks."
    ),
    "Oil & Gas Marketing": (
        "OMC margins are regulated and inventory gains/losses swing with oil prices; "
        "receivables from the power sector are the usual balance-sheet risk."
    ),
    "Fertilizer": (
        "Fertilizer economics depend on gas tariff and supply allocation, urea/DAP "
        "pricing and seasonal demand. High dividend payout is normal; check whether "
        "payout is funded by cash flow or by balance-sheet capacity."
    ),
    "Power Generation": (
        "IPPs are capacity-payment driven and exposed to circular debt: receivables "
        "from CPPA/NTDC can be a multiple of annual profit. Leverage is high by "
        "design, so covenant headroom and receivable ageing are the key checks."
    ),
    "Commercial Banks": (
        "Banks need a different model: net interest margin, provisioning, ADR, CASA "
        "mix and capital adequacy. This desk's industrial ratio engine does not apply "
        "cleanly to financials; treat coverage warnings accordingly."
    ),
    "Technology & Communication": (
        "Tech earnings are driven by USD-linked revenue, PKR depreciation and client "
        "concentration. Growth multiples are higher than the market average."
    ),
}

#: Macro checklist injected into every prompt and used for watch items.
MACRO_LENS: tuple[tuple[str, str], ...] = (
    ("Policy rate", "SBP policy rate drives interest cost, bank margins and valuation multiples."),
    ("PKR/USD", "Rupee depreciation lifts USD-linked revenue and imported input costs."),
    ("Inflation", "Nominal revenue growth can flatter real growth; high inflation also lifts working capital."),
    ("Circular debt", "Power and gas chain receivables can sit on the balance sheet for years."),
    ("Regulation & tariffs", "Administered prices, duties and gas allocation can reset sector economics."),
    ("Liquidity & free float", "Thin free float means the market price may not be a fair value signal."),
    ("IMF programme & FX reserves", "External account stress changes the discount rate for the whole market."),
)

_SYMBOL_PREFIXES = ("PSX:", "PSX ", "KSE:", "PSX-")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


def normalize_symbol(raw: str) -> str:
    """Convert any common PSX ticker spelling into the canonical symbol.

    ``ogdc``, `` PSX:OGDC ``, ``OGDC.KA`` and ``OGDC-KA`` all become ``OGDC``.
    """
    if raw is None:
        raise ValueError("ticker is required")
    text = str(raw).strip().upper()
    for prefix in _SYMBOL_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if text.endswith(".KA"):
        text = text[:-3]
    if text.endswith("-KA"):
        text = text[:-3]
    text = text.replace(" ", "")
    if not text:
        raise ValueError("ticker is required")
    if not _SYMBOL_RE.match(text):
        raise ValueError(f"{raw!r} is not a valid PSX symbol")
    return text


def yahoo_symbol(symbol: str) -> str:
    """Yahoo Finance listing code for a PSX symbol (``OGDC`` -> ``OGDC.KA``)."""
    base = normalize_symbol(symbol)
    return base if base.endswith(YAHOO_SUFFIX) else base + YAHOO_SUFFIX


def sector_group(sector: str | None) -> str | None:
    """Map a free-text sector label onto the PSX sector taxonomy."""
    if not sector:
        return None
    lowered = sector.strip().lower()
    for group, aliases in PSX_SECTORS.items():
        if lowered == group.lower() or any(alias in lowered for alias in aliases):
            return group
    return None


def sector_note(sector: str | None) -> str | None:
    group = sector_group(sector)
    return SECTOR_NOTES.get(group) if group else None


# --------------------------------------------------------------------- units
#: Multipliers that convert a reported figure into millions of PKR.
UNIT_SCALE: dict[str, float] = {
    "millions": 1.0,
    "million": 1.0,
    "mn": 1.0,
    "thousands": 0.001,
    "thousand": 0.001,
    "'000": 0.001,
    "000": 0.001,
    "billions": 1_000.0,
    "billion": 1_000.0,
    "bn": 1_000.0,
    "units": 1e-6,
    "rupees": 1e-6,
    "crore": 10.0,
    "crores": 10.0,
    "lakh": 0.1,
    "lakhs": 0.1,
}


def unit_scale(units: str | None) -> float:
    """Multiplier converting ``units`` into millions (default: millions)."""
    if not units:
        return 1.0
    key = str(units).strip().lower().replace(",", "")
    if key in UNIT_SCALE:
        return UNIT_SCALE[key]
    raise ValueError(
        f"unknown units {units!r}; use one of {', '.join(sorted(UNIT_SCALE))}"
    )


UNSCALED_FIELDS = frozenset({"eps", "dividend_per_share", "price", "fiscal_year"})


def scale_statements(years: Iterable[dict[str, Any]], units: str | None) -> list[dict[str, Any]]:
    """Scale statement fields of ``years`` from ``units`` into millions.

    Per-share fields (``eps``) and identifiers are never scaled: a company
    reporting in PKR thousands still quotes EPS in rupees.
    """
    factor = unit_scale(units)
    scaled: list[dict[str, Any]] = []
    for year in years:
        record: dict[str, Any] = {}
        for key, value in dict(year).items():
            if key in UNSCALED_FIELDS or key in {"period", "notes"}:
                record[key] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                record[key] = round(float(value) * factor, 4)
            else:
                record[key] = value
        scaled.append(record)
    return scaled


# -------------------------------------------------------------------- quotes
@dataclass
class PsxQuote:
    symbol: str
    price: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    as_of: str | None = None
    source: str = "psx-data-portal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "as_of": self.as_of,
            "source": self.source,
        }


_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_cell(raw: str) -> str:
    text = _TAG_RE.sub("", raw)
    return html_module.unescape(text).replace("\xa0", " ").strip()


def _to_float(text: str) -> float | None:
    cleaned = text.replace(",", "").replace("%", "").strip()
    if cleaned in {"", "-", "--", "N/A", "n/a"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_historical_table(html: str) -> list[dict[str, Any]]:
    """Parse the PSX Data Portal historical table into rows oldest-first.

    The portal returns ``TIME | OPEN | HIGH | LOW | CLOSE | VOLUME``; parsing is
    tolerant of extra columns and header rows so a markup change degrades into an
    empty result instead of an exception.
    """
    rows: list[dict[str, Any]] = []
    for row_html in _ROW_RE.findall(html or ""):
        cells = [_clean_cell(cell) for cell in _CELL_RE.findall(row_html)]
        if len(cells) < 2:
            continue
        if cells[0].strip().upper() in {"TIME", "DATE", ""}:
            continue
        close = None
        volume = None
        if len(cells) >= 6:
            close = _to_float(cells[4])
            volume = _to_float(cells[5])
        if close is None:
            numbers = [_to_float(cell) for cell in cells[1:]]
            numeric = [value for value in numbers if value is not None]
            if not numeric:
                continue
            close = numeric[0]
            volume = numeric[-1] if len(numeric) > 1 else None
        parsed_date = None
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%d %b %Y"):
            try:
                parsed_date = datetime.strptime(cells[0], fmt).date()
                break
            except ValueError:
                continue
        rows.append({"date": parsed_date, "close": close, "volume": volume})
    rows.sort(key=lambda item: item["date"] or date.min)
    return rows


class PsxQuoteClient:
    """Minimal PSX Data Portal client: symbols list and daily closes.

    The portal exposes no documented JSON quote API, so this reads the public
    historical table for the current month (falling back one month) and keeps the
    last two closes. Failures are reported as ``None`` values, never exceptions,
    because a missing quote must not stop a research report.
    """

    def __init__(
        self,
        base_url: str = PSX_DEFAULT_BASE_URL,
        timeout: float = 12.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None
        self.last_error: str | None = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout, follow_redirects=True)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def symbols(self) -> list[str]:
        try:
            response = self._http().get(f"{self.base_url}/symbols")
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # network/parse failures are non-fatal
            self.last_error = f"symbol list unavailable: {exc}"
            return []
        found: list[str] = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    found.append(item.strip().upper())
                elif isinstance(item, dict):
                    for key in ("symbol", "Symbol", "SYMBOL", "scrip"):
                        if isinstance(item.get(key), str):
                            found.append(item[key].strip().upper())
                            break
        return [item for item in found if item]

    def quote(self, symbol: str) -> PsxQuote:
        base = normalize_symbol(symbol)
        rows: list[dict[str, Any]] = []
        today = date.today()
        for months_back in (0, 1):
            year = today.year
            month = today.month - months_back
            if month < 1:
                month += 12
                year -= 1
            try:
                response = self._http().post(
                    f"{self.base_url}/historical",
                    data={"month": str(month), "year": str(year), "symbol": base},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
            except Exception as exc:
                self.last_error = f"quote unavailable for {base}: {exc}"
                continue
            rows = parse_historical_table(response.text)
            if rows:
                break
        if not rows:
            return PsxQuote(symbol=base)
        latest = rows[-1]
        previous = rows[-2] if len(rows) > 1 else None
        change_pct = None
        if previous and previous["close"] and latest["close"]:
            change_pct = latest["close"] / previous["close"] - 1.0
        return PsxQuote(
            symbol=base,
            price=latest["close"],
            change_pct=round(change_pct, 6) if change_pct is not None else None,
            volume=latest["volume"],
            as_of=latest["date"].isoformat() if latest["date"] else None,
        )
