"""Parsers for the PSX Data Portal pages.

The portal publishes HTML, not a documented API, so every parser here is
defensive:

* columns are located by their **header text** (or the portal's own
  ``data-name`` attributes), never by a hard-coded position,
* the portal's ``data-order`` attributes are preferred over the formatted cell
  text, because ``1,234`` is displayed but ``1234.4`` is published,
* unknown cells become ``None`` — never a zero, never a guess,
* failures raise :class:`ParseError` with a snippet of what was actually seen,
  so a markup change is diagnosable from a log rather than silently producing
  junk.

Nothing here performs I/O.
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

#: Index codes the portal publishes. Used to recognise membership cells.
KNOWN_INDEX_CODES = frozenset(
    {
        "KSE100", "KSE100PR", "KSE30", "KMI30", "KMIALLSHR", "ALLSHR", "PSXDIV20",
        "BKTI", "OGTI", "MII30", "MZNPI", "NBPPGI", "NITPGI", "UPP9", "ACI",
        "JSGBKTI", "JSMFI", "HBLTTI", "MZNPETF",
    }
)

#: Any token that looks like an index code, for pages that publish new ones.
INDEX_TOKEN_RE = re.compile(
    r"\b(KSE\d{2,3}(?:PR)?|KMI[A-Z0-9]*|ALLSHR|PSX[A-Z0-9]*|MII\d+|MZN[A-Z0-9]*|"
    r"NBPP[A-Z0-9]*|NIT[A-Z0-9]*|UPP\d+[A-Z]*|HBLTTI|BKTI|OGTI|ACI|JS[A-Z0-9]+)\b"
)

PARS_E = 5  # Pakistan Standard Time offset in hours (no DST)

_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*"([^"]*)"')

#: ``K``/``M``/``B`` suffixes the portal prints instead of full numbers.
_MAGNITUDES = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}


class ParseError(RuntimeError):
    """Raised when a portal page does not contain the expected structure."""


# --------------------------------------------------------------------- utils
def clean_text(raw: str) -> str:
    """Strip tags, unescape entities and collapse whitespace."""
    text = _TAG_RE.sub(" ", raw or "")
    text = html_module.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def to_float(text: Any) -> float | None:
    """Parse ``'1,234.56'``, ``'(12.3)'``, ``'5.2%'``, ``'Rs. 99'``; else None."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    cleaned = str(text).strip().replace(",", "").replace("%", "").replace("Rs.", "")
    cleaned = cleaned.replace("PKR", "").strip()
    if not cleaned or cleaned.lower() in {"-", "--", "n/a", "na", "x", "nil"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def magnitude_to_float(text: Any) -> float | None:
    """Parse ``'399.5M'``, ``'7.0K'``, ``'2.1B'`` as well as plain numbers."""
    if text is None:
        return None
    raw = str(text).strip().replace(",", "")
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([KkMmBb][Nn]?)?", raw)
    if not match:
        return to_float(text)
    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    return value * _MAGNITUDES.get(suffix, 1.0)


def to_int(text: Any) -> int | None:
    value = to_float(text)
    return None if value is None else int(value)


@dataclass
class Cell:
    """A table cell: rendered text, its attributes and its inner markup."""

    text: str
    attrs: dict[str, str] = field(default_factory=dict)
    html: str = field(default="", repr=False)

    @property
    def title(self) -> str | None:
        """``data-title`` — the portal puts the company name on the inner link."""
        if self.attrs.get("data-title"):
            return self.attrs["data-title"]
        match = re.search(r'data-title\s*=\s*"([^"]*)"', self.html or "")
        return clean_text(match.group(1)) or None if match else None

    @property
    def order(self) -> str | None:
        """``data-order`` — the unformatted value behind the display text."""
        return self.attrs.get("data-order")

    def number(self) -> float | None:
        """Prefer ``data-order``; fall back to the rendered text (incl. K/M/B)."""
        if self.order is not None:
            parsed = to_float(self.order)
            if parsed is not None:
                return parsed
        return magnitude_to_float(self.text)


def rows(html: str, table_index: int | None = None) -> list[list[Cell]]:
    """Return table rows as lists of :class:`Cell`."""
    source = html
    if table_index is not None:
        tables = _TABLE_RE.findall(html)
        if table_index >= len(tables):
            raise ParseError(f"expected table #{table_index} but the page has {len(tables)}")
        source = tables[table_index]
    parsed: list[list[Cell]] = []
    for row_html in _ROW_RE.findall(source):
        cells = [
            Cell(text=clean_text(body), attrs=dict(_ATTR_RE.findall(attrs)), html=body)
            for _tag, attrs, body in _CELL_RE.findall(row_html)
        ]
        if cells:
            parsed.append(cells)
    return parsed


def tables(html: str) -> list[str]:
    return _TABLE_RE.findall(html)


def _header_map(cells: list[Cell]) -> dict[str, int]:
    """Map normalised header names to column indexes.

    The portal labels its headers with ``data-name`` (``peRatio``), so both the
    visible text and that attribute are indexed: ``"pe ratio (ttm)"`` and
    ``"peratio"`` both resolve.
    """
    mapping: dict[str, int] = {}
    for index, cell in enumerate(cells):
        for candidate in (cell.text, cell.attrs.get("data-name", "")):
            name = re.sub(r"[^a-z0-9%]+", " ", candidate.lower()).strip()
            if name:
                mapping.setdefault(name, index)
    return mapping


def _find(headers: dict[str, int], *candidates: str) -> int | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    for candidate in candidates:
        for name, index in headers.items():
            if candidate and candidate in name:
                return index
    return None


#: A PSX symbol: letters/digits, optionally suffixed by a marker such as "XD"
#: (ex-dividend) or "XR" (ex-rights) that the portal appends to the display text.
_SYMBOL_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,15}")


def symbol_of(cell: Cell) -> str | None:
    """The trading symbol of a row's first cell.

    The portal appends market markers to the display text ("AHCL XD"), so the
    first whitespace-separated token is used, with ``data-order`` preferred when
    the cell ships one.
    """
    if cell is None:
        return None
    for candidate in (cell.order, cell.text):
        if not candidate:
            continue
        token = str(candidate).strip().split(" ")[0].upper()
        if token and _SYMBOL_RE.fullmatch(token):
            return token
    return None


def index_tokens(raw_html: str) -> set[str]:
    """Every index code mentioned in a cell's text or attributes."""
    text = clean_text(raw_html)
    tokens = {match.group(1).upper() for match in INDEX_TOKEN_RE.finditer(text)}
    for name, value in _ATTR_RE.findall(raw_html or ""):
        upper = value.upper()
        tokens |= {match.group(1).upper() for match in INDEX_TOKEN_RE.finditer(upper)}
        if name.lower() in {"data-index", "data-indices", "data-listed"} and value.strip():
            tokens |= {part.strip().upper() for part in re.split(r"[,\s|;]+", upper) if part.strip()}
    return tokens


# ------------------------------------------------------------------ date/time
def derive_trade_date(epoch: int | float | str | None) -> date | None:
    """Convert a portal timestamp into the Karachi trading date.

    The portal emits Pakistan wall-clock timestamps (in milliseconds for
    ``data-latest``). Treating them as UTC and adding the +5h offset lands on the
    correct Karachi day; if that would land on a weekend the plain UTC reading is
    used instead, which covers feeds that emit true UTC.
    """
    if epoch is None:
        return None
    try:
        stamp = float(epoch)
    except (TypeError, ValueError):
        return None
    if stamp > 1e11:  # milliseconds
        stamp = stamp / 1000.0
    if stamp <= 0:
        return None
    moment = datetime.fromtimestamp(stamp, tz=timezone.utc)
    plain = moment.date()
    shifted = (moment + timedelta(hours=PARS_E)).date()
    if shifted.weekday() < 5 or plain.weekday() >= 5:
        return shifted
    return plain


def parse_latest_trade_date(html: str) -> tuple[date | None, str]:
    """Read the portal's own "latest trading date" stamp.

    ``/historical`` ships ``<input id="historicalDatePicker" data-latest="…">``;
    ``/indices`` stamps a trailing-index cell as ``(DD-MM-YYYY HH:MM:SS)``. The
    second return value says which source answered, for the ingest report.
    """
    match = re.search(r'data-latest\s*=\s*"(\d{10,13})"', html or "")
    if match:
        parsed = derive_trade_date(match.group(1))
        if parsed:
            return parsed, "historical-data-latest"
    match = re.search(r"\((\d{2})-(\d{2})-(\d{4})\s+\d{1,2}:\d{2}:\d{2}\)", html or "")
    if match:
        try:
            parsed = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            return parsed, "indices-timestamp"
        except ValueError:
            pass
    return None, "unavailable"


# ------------------------------------------------------------------ screener
@dataclass
class ScreenerRow:
    symbol: str
    name: str | None = None
    sector_code: str | None = None
    listed_in: set[str] = field(default_factory=set)
    market_cap: float | None = None
    price: float | None = None
    change_pct: float | None = None
    year_change_pct: float | None = None
    pe: float | None = None
    dividend_yield: float | None = None
    free_float: float | None = None
    avg_volume_30d: float | None = None


def parse_screener(html: str) -> list[ScreenerRow]:
    """Parse ``/screener``: one row per listed symbol for the whole market.

    Columns (as published): SYMBOL, SECTOR, LISTED IN, MARKET CAP., PRICE,
    CHANGE (%), 1-YEAR CH. (%), PE RATIO (TTM), DIVIDEND YIELD (%), FREE FLOAT,
    30D VOLUME AVG. The SECTOR column carries the portal's numeric sector code,
    so the industry name, when we have one, comes from the company page.
    """
    table_rows = rows(html)
    if not table_rows:
        raise ParseError("screener page contained no table rows")

    header_index: int | None = None
    headers: dict[str, int] = {}
    for position, cells in enumerate(table_rows):
        candidate = _header_map(cells)
        if _find(candidate, "symbol") is not None and len(candidate) >= 4:
            header_index, headers = position, candidate
            break
    if header_index is None:
        raise ParseError(
            f"screener: no header row containing 'symbol'; saw {[c.text for c in table_rows[0][:4]]}"
        )

    col_symbol = _find(headers, "symbol")
    col_sector = _find(headers, "sector")
    col_listed = _find(headers, "listed in", "listed")
    col_cap = _find(headers, "market cap")
    col_price = _find(headers, "price", "close", "current")
    col_change_pct = _find(headers, "change %", "percentchange", "change")
    col_year = _find(headers, "1 year ch", "changeyear", "1 year")
    col_pe = _find(headers, "pe ratio", "peratio", "p e")
    col_yield = _find(headers, "dividend yield", "dividendyield")
    col_float = _find(headers, "free float", "freefloat")
    col_volume = _find(headers, "30d volume", "volume30avg", "volume")

    def cell(cells: list[Cell], index: int | None) -> Cell | None:
        if index is None or index >= len(cells):
            return None
        return cells[index]

    parsed: list[ScreenerRow] = []
    for cells in table_rows[header_index + 1:]:
        symbol_cell = cell(cells, col_symbol)
        symbol = symbol_of(symbol_cell) if symbol_cell is not None else None
        if symbol is None:
            continue
        listed_cell = cell(cells, col_listed)
        listing_text = listed_cell.text if listed_cell else ""
        listed = index_tokens(listing_text)
        if listed_cell is not None:
            listed |= index_tokens(" ".join(f"{k}={v}" for k, v in listed_cell.attrs.items()))
        parsed.append(
            ScreenerRow(
                symbol=symbol,
                name=symbol_cell.title,
                sector_code=(cell(cells, col_sector).text if cell(cells, col_sector) else None),
                listed_in=listed,
                market_cap=(cell(cells, col_cap).number() if cell(cells, col_cap) else None),
                price=(cell(cells, col_price).number() if cell(cells, col_price) else None),
                change_pct=(cell(cells, col_change_pct).number() if cell(cells, col_change_pct) else None),
                year_change_pct=(cell(cells, col_year).number() if cell(cells, col_year) else None),
                pe=(cell(cells, col_pe).number() if cell(cells, col_pe) else None),
                dividend_yield=(cell(cells, col_yield).number() if cell(cells, col_yield) else None),
                free_float=(cell(cells, col_float).number() if cell(cells, col_float) else None),
                avg_volume_30d=(cell(cells, col_volume).number() if cell(cells, col_volume) else None),
            )
        )
    if not parsed:
        raise ParseError("screener: header row found but no data rows parsed")
    return parsed


def parse_sector_codes(html: str) -> dict[str, str]:
    """The portal's sector filter maps codes to industry names.

    ``/screener`` carries ``<option value="0807">COMMERCIAL BANKS</option>``, and
    its table rows only publish the code, so this lookup is what turns "0807"
    into a sector a reader recognises.
    """
    mapping: dict[str, str] = {}
    for value, label in re.findall(
        r"<option[^>]*value=\"([^\"]*)\"[^>]*>(.*?)</option>", html or "", re.DOTALL
    ):
        code = (value or "").strip()
        name = clean_text(label)
        if code and name and re.fullmatch(r"[0-9]{3,5}", code):
            mapping[code] = name
    return mapping


# ------------------------------------------------------- index constituents
@dataclass
class ConstituentRow:
    symbol: str
    name: str | None = None
    ldcp: float | None = None
    close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    weight_pct: float | None = None
    index_points: float | None = None
    volume: float | None = None
    free_float: float | None = None
    market_cap: float | None = None


def parse_index_constituents(html: str, index_code: str = "?") -> list[ConstituentRow]:
    """Parse ``/indices/{CODE}``: the constituents of one index.

    Columns (as published): SYMBOL, NAME, LDCP, CURRENT, CHANGE, CHANGE (%),
    IDX WTG (%), IDX POINT, VOLUME, FREEFLOAT (M), MARKET CAP (M). Every numeric
    cell carries ``data-order`` with the unrounded value.
    """
    table_rows = rows(html)
    if not table_rows:
        raise ParseError(f"indices/{index_code}: page contained no table rows")

    header_index: int | None = None
    headers: dict[str, int] = {}
    for position, cells in enumerate(table_rows):
        candidate = _header_map(cells)
        if _find(candidate, "symbol") is not None and len(candidate) >= 4:
            header_index, headers = position, candidate
            break
    if header_index is None:
        raise ParseError(f"indices/{index_code}: no header row containing 'symbol'")

    col_symbol = _find(headers, "symbol")
    col_name = _find(headers, "name", "company")
    col_ldcp = _find(headers, "ldcp", "previous close")
    col_current = _find(headers, "current", "close", "price")
    col_change = _find(headers, "change")
    col_change_pct = _find(headers, "change %", "change pct")
    col_weight = _find(headers, "idx wtg", "weight")
    col_points = _find(headers, "idx point", "index point", "points")
    col_volume = _find(headers, "volume", "turnover")
    col_float = _find(headers, "freefloat", "free float")
    col_cap = _find(headers, "market cap")

    def cell(cells: list[Cell], index: int | None) -> Cell | None:
        if index is None or index >= len(cells):
            return None
        return cells[index]

    parsed: list[ConstituentRow] = []
    for cells in table_rows[header_index + 1:]:
        symbol_cell = cell(cells, col_symbol)
        symbol = symbol_of(symbol_cell) if symbol_cell is not None else None
        if symbol is None:
            continue
        name_cell = cell(cells, col_name)
        parsed.append(
            ConstituentRow(
                symbol=symbol,
                name=(name_cell.text or None) if name_cell else symbol_cell.title,
                ldcp=(cell(cells, col_ldcp).number() if cell(cells, col_ldcp) else None),
                close=(cell(cells, col_current).number() if cell(cells, col_current) else None),
                change=(cell(cells, col_change).number() if cell(cells, col_change) else None),
                change_pct=(cell(cells, col_change_pct).number() if cell(cells, col_change_pct) else None),
                weight_pct=(cell(cells, col_weight).number() if cell(cells, col_weight) else None),
                index_points=(cell(cells, col_points).number() if cell(cells, col_points) else None),
                volume=(cell(cells, col_volume).number() if cell(cells, col_volume) else None),
                free_float=(cell(cells, col_float).number() if cell(cells, col_float) else None),
                market_cap=(cell(cells, col_cap).number() if cell(cells, col_cap) else None),
            )
        )
    if not parsed:
        raise ParseError(f"indices/{index_code}: header row found but no constituents parsed")
    return parsed


# ---------------------------------------------------------------- index table
@dataclass
class IndexRow:
    code: str
    name: str | None = None
    level: float | None = None
    change: float | None = None
    change_pct: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None


#: PSX prints history dates as ``2026-10-29`` (and, on some pages, ``29-Oct-2026``).
_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y", "%b %d, %Y")


def parse_history_date(text: str) -> date | None:
    """Parse a history-table date cell, tolerating the portal's spellings."""
    cleaned = clean_text(text)
    if not cleaned:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


#: The chart feed's row layout: ``[epoch, close, volume, open]``.
TIMESERIES_FIELDS = ("trade_date", "close", "volume", "open")


def parse_timeseries_eod(payload: Any, symbol: str = "?") -> list[dict[str, Any]]:
    """Parse ``GET /timeseries/eod/{SYM}`` — the portal's compact OHLCV feed.

    The feed answers ``{"status": 1, "message": "", "data": [[epoch, close,
    volume, open], ...]}`` newest first. It carries no high/low (``POST
    /historical`` does), so those stay ``None`` here and are never invented.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ParseError(
                f"timeseries/{symbol}: not JSON ({payload[:60]!r})"
            ) from exc
    if not isinstance(payload, dict):
        raise ParseError(f"timeseries/{symbol}: expected a JSON object")
    if payload.get("status") not in (1, "1", True):
        message = payload.get("message") or "no status"
        raise ParseError(f"timeseries/{symbol}: portal said {message!r}")
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ParseError(f"timeseries/{symbol}: the feed carried no rows")

    bars: dict[date, dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, (list, tuple)) or len(entry) < 4:
            continue
        moment = derive_trade_date(entry[0])
        if moment is None:
            continue
        bar = {
            "trade_date": moment,
            "open": to_float(entry[3]),
            "high": None,   # the chart feed carries no intraday range
            "low": None,
            "close": to_float(entry[1]),
            "volume": to_float(entry[2]),
        }
        if bar["close"] is None:
            continue
        bars[moment] = bar
    if not bars:
        raise ParseError(f"timeseries/{symbol}: no parsable rows")
    return [bars[day] for day in sorted(bars)]


def parse_history(html: str, symbol: str = "?") -> list[dict[str, Any]]:
    """Parse the ``POST /historical`` table into daily bars.

    The portal answers the form post with an HTML table of
    ``Date | Open | High | Low | Close | Volume`` rows — the whole listing
    history, oldest first. Columns are matched by header text, so an extra
    column (the portal sometimes adds ``Change`` fields) is ignored rather than
    shifting every number by one.
    """
    table_rows = rows(html)
    if not table_rows:
        raise ParseError(f"history/{symbol}: the portal returned no table rows")

    header_index: int | None = None
    headers: dict[str, int] = {}
    for position, cells in enumerate(table_rows):
        candidate = _header_map(cells)
        if _find(candidate, "date") is not None and _find(candidate, "close") is not None:
            header_index, headers = position, candidate
            break
    if header_index is None:
        raise ParseError(
            f"history/{symbol}: no header row with 'date' and 'close' "
            f"(saw: {summarise_parse_gap(html)})"
        )

    col_date = _find(headers, "date")
    col_open = _find(headers, "open")
    col_high = _find(headers, "high")
    col_low = _find(headers, "low")
    col_close = _find(headers, "close")
    col_volume = _find(headers, "volume", "turnover")

    def cell(cells: list[Cell], index: int | None) -> float | None:
        if index is None or index >= len(cells):
            return None
        return to_float(cells[index].attrs.get("data-order") or cells[index].text)

    bars: dict[date, dict[str, Any]] = {}
    for cells in table_rows[header_index + 1 :]:
        if col_date is None or col_date >= len(cells):
            continue
        day = parse_history_date(cells[col_date].text)
        if day is None:
            continue
        bar = {
            "trade_date": day,
            "open": cell(cells, col_open),
            "high": cell(cells, col_high),
            "low": cell(cells, col_low),
            "close": cell(cells, col_close),
            "volume": cell(cells, col_volume),
        }
        if bar["close"] is None and bar["open"] is None:
            continue
        bars[day] = bar  # a repeated date keeps the last (most complete) row
    if not bars:
        raise ParseError(f"history/{symbol}: the table had no parsable date rows")
    return [bars[day] for day in sorted(bars)]


def parse_indices(html: str) -> list[IndexRow]:
    """Parse ``/indices``: current level, day high/low and change per index."""
    table_rows = rows(html)
    if not table_rows:
        raise ParseError("indices page contained no table rows")
    headers = _header_map(table_rows[0])
    col_name = _find(headers, "index", "name")
    col_high = _find(headers, "high")
    col_low = _find(headers, "low")
    col_current = _find(headers, "current", "level", "close")
    col_change = _find(headers, "change")
    col_pct = _find(headers, "change %", "change pct")

    out: list[IndexRow] = []
    for cells in table_rows[1:]:
        raw_name = cells[col_name].text if col_name is not None and col_name < len(cells) else cells[0].text
        match = INDEX_TOKEN_RE.search(raw_name.upper())
        if not match:
            continue

        def cell(index: int | None) -> Cell | None:
            if index is None or index >= len(cells):
                return None
            return cells[index]

        out.append(
            IndexRow(
                code=match.group(1).upper(),
                name=raw_name,
                level=(cell(col_current).number() if cell(col_current) else None),
                change=(cell(col_change).number() if cell(col_change) else None),
                change_pct=(cell(col_pct).number() if cell(col_pct) else None),
                high=(cell(col_high).number() if cell(col_high) else None),
                low=(cell(col_low).number() if cell(col_low) else None),
            )
        )
    if not out:
        raise ParseError("indices: table found but no index codes recognised")
    return out


# ------------------------------------------------------------- company pages
_STAT_LABELS = {
    # "close" only: a bare "price" needle would match "Ask Price"/"Bid Price",
    # which are the (usually zero) order-book quotes, not the traded price.
    "price": ("close", "current price"),
    "open": ("open",),
    "prev_close": ("ldcp", "previous close"),
    "volume": ("volume",),
    "shares": ("shares outstanding", "shares", "no of shares"),
    "free_float": ("free float",),
    "free_float_pct": ("free float %", "free float percentage"),
    "pe": ("p/e ratio", "p/e", "pe ratio"),
    "pb": ("p/b", "price to book"),
    "year_change_pct": ("1 year change", "1-year change"),
    "ytd_change_pct": ("ytd change", "ytd"),
    "market_cap": ("market cap", "market capitalization"),
    # range keys are filled by _RANGE_TARGETS, never by a single value
    "high": ("day high",),
    "low": ("day low",),
    "high_52w": ("52 week high",),
    "low_52w": ("52 week low",),
    "circuit_high": ("circuit high",),
    "circuit_low": ("circuit low",),
}

#: labels the portal renders as "low — high" pairs; one label yields two numbers.
_RANGE_LABELS = {
    "52_week": ("52 week range", "52-week range", "52 week range ^"),
    "day": ("day range",),
    "circuit": ("circuit breaker",),
}

#: ``_RANGE_LABELS`` group -> (low key, high key)
_RANGE_TARGETS = {
    "52_week": ("low_52w", "high_52w"),
    "day": ("low", "high"),
    "circuit": ("circuit_low", "circuit_high"),
}

#: canonical metric keys for the financial tables the portal publishes
_FIN_LABELS = {
    "revenue": ("sales", "revenue", "net sales"),
    "gross_profit": ("gross profit",),
    "operating_income": ("operating profit", "profit from operations"),
    "pretax_income": ("profit before taxation", "profit before tax"),
    "income_tax_expense": ("taxation",),
    "net_income": ("profit after taxation", "profit after tax", "net profit"),
    "eps": ("eps", "earnings per share"),
    "dividend_per_share": ("dividend per share", "dps"),
    "gross_margin_pct": ("gross profit margin",),
    "net_margin_pct": ("net profit margin",),
    "eps_growth_pct": ("eps growth",),
    "peg": ("peg",),
}

_RANGE_RE = re.compile(
    r"(-?\d[\d,]*(?:\.\d+)?)\s*(?:—|–|-|to)\s*(-?\d[\d,]*(?:\.\d+)?)"
)


def _stat_pairs(html: str) -> list[tuple[str, str, str]]:
    """``(label, value_text, raw_value_block)`` from the portal's stat blocks."""
    pairs: list[tuple[str, str, str]] = []
    pattern = re.compile(
        r'class="[^"]*stats_label[^"]*"[^>]*>(.*?)</(?:div|span|p)>'
        r'\s*<(?:div|span|p)[^>]*class="[^"]*stats_value[^"]*"[^>]*>(.*?)</(?:div|span|p)>',
        re.IGNORECASE | re.DOTALL,
    )
    for label_block, value_block in pattern.findall(html or ""):
        pairs.append((clean_text(label_block), clean_text(value_block), value_block))
    # two-cell label/value tables, for pages that render stats that way
    for cells in rows(html or ""):
        if len(cells) == 2:
            pairs.append((cells[0].text, cells[1].text, ""))
    return pairs


def _best_label(label: str, table: dict[str, tuple[str, ...]]) -> str | None:
    """Pick the longest matching needle, so "free float %" beats "free float"."""
    best_key: str | None = None
    best_score = 0
    for key, needles in table.items():
        for needle in needles:
            if needle in label and len(needle) > best_score:
                best_key, best_score = key, len(needle)
    return best_key


def parse_company_stats(html: str) -> dict[str, float | None]:
    """Company statistics: quote, ranges, ratios — whatever the page publishes.

    Range blocks ("303.00 — 307.99", "238.20 — 352.00") are split into their low
    and high halves; a range with no parsable numbers stays ``None``.
    """
    stats: dict[str, float | None] = {key: None for key in _STAT_LABELS}
    for raw_label, value_text, value_html in _stat_pairs(html):
        label = re.sub(r"[^a-z0-9%. /-]+", " ", raw_label.lower()).strip()

        # "238.20 — 352.00" style blocks publish two numbers under one label
        range_group = _best_label(label, _RANGE_LABELS)
        if range_group is not None:
            match = _RANGE_RE.search(value_html) or _RANGE_RE.search(value_text)
            if match:
                low, high = to_float(match.group(1)), to_float(match.group(2))
                low_key, high_key = _RANGE_TARGETS[range_group]
                if low is not None and stats.get(low_key) is None:
                    stats[low_key] = low
                if high is not None and stats.get(high_key) is None:
                    stats[high_key] = high
            continue

        key = _best_label(label, _STAT_LABELS)
        if key is None:
            continue
        parsed = to_float(value_text)
        if parsed is None:
            # the DAY RANGE row also feeds the High/Low cells on some layouts
            match = _RANGE_RE.search(value_text)
            if match and key in {"high", "low"}:
                parsed = to_float(match.group(2)) if key == "high" else to_float(match.group(1))
        if parsed is not None and stats.get(key) is None:
            stats[key] = parsed
    return stats


def _period_of(text: str) -> tuple[str, int | None, int | None] | None:
    """Turn ``'FY2024'``, ``'2026'`` or ``'Q3 2026'`` into a period descriptor."""
    cleaned = clean_text(text)
    quarter = re.search(r"\bQ([1-4])\b", cleaned, re.IGNORECASE)
    year = re.search(r"(20\d{2})", cleaned)
    if not year:
        return None
    fiscal_year = int(year.group(1))
    if quarter:
        return f"Q{quarter.group(1)} {fiscal_year}", fiscal_year, int(quarter.group(1))
    return str(fiscal_year), fiscal_year, None


def parse_company_financials(html: str, max_periods: int = 8) -> list[dict[str, Any]]:
    """Published financial line items, normalised to ``(period, metric, value)``.

    The portal renders these tables in either orientation — metrics as rows with
    years across the top, or periods as rows with metrics across the top — so
    both are detected. Only labels the page actually prints are stored, plus a
    canonical metric key where the label maps to one; anything unrecognised is
    kept under a slug of its published label rather than dropped.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for table in tables(html or ""):
        table_rows = rows(table)
        if len(table_rows) < 2:
            continue
        for header_position, header in enumerate(table_rows[:3]):
            # orientation A: periods across the top
            period_columns = [
                (index, _period_of(cell.text))
                for index, cell in enumerate(header)
                if _period_of(cell.text)
            ]
            if len(period_columns) >= 2:
                for row in table_rows[header_position + 1:]:
                    if len(row) <= max(index for index, _ in period_columns):
                        continue
                    label = row[0].text
                    key = _best_label(re.sub(r"[^a-z0-9 ]+", " ", label.lower()).strip(), _FIN_LABELS)
                    metric = key or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
                    if not metric:
                        continue
                    for index, period in period_columns:
                        assert period is not None
                        value = row[index].number()
                        if value is None:
                            continue
                        token = (period[0], metric)
                        if token in seen:
                            continue
                        seen.add(token)
                        out.append(
                            {
                                "period": period[0],
                                "fiscal_year": period[1],
                                "quarter": period[2],
                                "metric": metric,
                                "label": label,
                                "value": value,
                            }
                        )
                break
            # orientation B: periods down the side, metrics across the top
            metric_columns = [
                (index, cell.text)
                for index, cell in enumerate(header)
                if index > 0 and _best_label(
                    re.sub(r"[^a-z0-9 ]+", " ", cell.text.lower()).strip(), _FIN_LABELS
                )
            ]
            if len(metric_columns) >= 2:
                for row in table_rows[header_position + 1:]:
                    period = _period_of(row[0].text)
                    if not period or len(row) <= max(index for index, _ in metric_columns):
                        continue
                    for index, label in metric_columns:
                        value = row[index].number()
                        if value is None:
                            continue
                        key = _best_label(
                            re.sub(r"[^a-z0-9 ]+", " ", label.lower()).strip(), _FIN_LABELS
                        )
                        metric = key or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
                        token = (period[0], metric)
                        if not metric or token in seen:
                            continue
                        seen.add(token)
                        out.append(
                            {
                                "period": period[0],
                                "fiscal_year": period[1],
                                "quarter": period[2],
                                "metric": metric,
                                "label": label,
                                "value": value,
                            }
                        )
                break

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        return (
            -(item["fiscal_year"] or 0),
            -(item["quarter"] or 0),
        )

    out.sort(key=sort_key)
    periods: list[str] = []
    for item in out:
        if item["period"] not in periods:
            periods.append(item["period"])
    keep = set(periods[:max_periods])
    return [item for item in out if item["period"] in keep]


def parse_sector_name(html: str) -> str | None:
    """The company page sometimes prints its industry name; grab it if present."""
    for raw_label, value_text, _value_html in _stat_pairs(html):
        if re.sub(r"[^a-z ]+", " ", raw_label.lower()).strip() == "sector":
            return value_text or None
    return None


def parse_company_meta(html: str) -> dict[str, Any]:
    """Symbol/company identity bits the company page restates."""
    name = None
    match = re.search(r'<h1[^>]*class="[^"]*company__name[^"]*"[^>]*>(.*?)</h1>', html or "", re.DOTALL)
    if match:
        name = clean_text(match.group(1)) or None
    return {"name": name, "sector": parse_sector_name(html)}


def summarise_parse_gap(html: str) -> str:
    """Short description of what a page contained, for error messages."""
    text = clean_text(html or "")
    return text[:200] if text else "empty page"


__all__ = [
    "Cell",
    "ConstituentRow",
    "IndexRow",
    "KNOWN_INDEX_CODES",
    "ParseError",
    "ScreenerRow",
    "clean_text",
    "derive_trade_date",
    "index_tokens",
    "magnitude_to_float",
    "parse_company_financials",
    "parse_company_meta",
    "parse_company_stats",
    "parse_history",
    "parse_history_date",
    "parse_timeseries_eod",
    "parse_index_constituents",
    "parse_indices",
    "parse_latest_trade_date",
    "parse_screener",
    "parse_sector_codes",
    "rows",
    "summarise_parse_gap",
    "symbol_of",
    "tables",
    "to_float",
    "to_int",
]
