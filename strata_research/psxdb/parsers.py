"""Parsers for the PSX Data Portal's HTML pages.

The portal publishes no schemas, so every parser here is defensive:

* it locates columns by **header text** first and falls back to the known
  positional layout,
* unknown cells become ``None`` rather than zero or a guess,
* it raises :class:`ParseError` with a snippet of what it actually saw, so a
  markup change is diagnosable from a CI log instead of producing silent junk.

Nothing in this module performs I/O.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

#: Index codes the portal uses. Used to recognise the membership column and to
#: filter tokens out of free text.
KNOWN_INDEX_CODES = frozenset(
    {
        "KSE100", "KSE30", "KMI30", "KMIALLSHR", "ALLSHR", "PSXDIV20", "BKTI",
        "OGTI", "KSE100PR", "MII30", "MZNPI", "NBPPGI", "NITPGI", "UPP9", "ACI",
        "JSGBKTI", "JSMFI", "NBPGETF", "MZNPETF", "UPP9ETF",
    }
)

#: Any token that *looks* like an index code, for pages with unknown codes.
INDEX_TOKEN_RE = re.compile(
    r"\b(KSE\d{2,3}(?:PR)?|KMI[A-Z0-9]*|ALLSHR|PSX[A-Z0-9]*|MII\d+|MZN[A-Z0-9]*|"
    r"NBPP[A-Z0-9]*|NIT[A-Z0-9]*|UPP\d+[A-Z]*|BKTI|OGTI|ACI|JS[A-Z0-9]+)\b"
)

PARS_E = 5  # Pakistan Standard Time offset, hours (no DST)

_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_RE = re.compile(r'(data-[a-z0-9_-]+)\s*=\s*"([^"]*)"', re.IGNORECASE)


class ParseError(RuntimeError):
    """Raised when a portal page does not contain the expected structure."""


# --------------------------------------------------------------------- utils
def clean_text(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    text = html_module.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def to_float(text: Any) -> float | None:
    """Parse ``'1,234.56'``, ``'(12.3)'``, ``'5.2%'``; return None if not numeric."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    cleaned = str(text).strip().replace(",", "").replace("%", "").replace("Rs.", "")
    cleaned = cleaned.replace("PKR", "").strip()
    if not cleaned or cleaned in {"-", "--", "n/a", "N/A", "NA", "x", "X"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def to_int(text: Any) -> int | None:
    value = to_float(text)
    return None if value is None else int(value)


@dataclass
class Cell:
    text: str
    attrs: dict[str, str] = field(default_factory=dict)


def rows(html: str, table_index: int | None = None) -> list[list[Cell]]:
    """Return table rows as lists of :class:`Cell` (text + data-* attributes)."""
    source = html
    if table_index is not None:
        tables = _TABLE_RE.findall(html)
        if table_index >= len(tables):
            raise ParseError(
                f"expected table #{table_index} but the page has {len(tables)}"
            )
        source = tables[table_index]
    parsed: list[list[Cell]] = []
    for row_html in _ROW_RE.findall(source):
        cells = [
            Cell(text=clean_text(body), attrs=dict(_ATTR_RE.findall(attrs)))
            for _tag, attrs, body in _CELL_RE.findall(row_html)
        ]
        if cells:
            parsed.append(cells)
    return parsed


def _header_map(cells: list[Cell]) -> dict[str, int]:
    """Map normalised header names to column indexes."""
    mapping: dict[str, int] = {}
    for index, cell in enumerate(cells):
        # keep "%" — "Change" and "Change %" are different columns
        name = re.sub(r"[^a-z0-9%]+", " ", cell.text.lower()).strip()
        if name:
            mapping[name] = index
    return mapping


def _find(headers: dict[str, int], *candidates: str) -> int | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    for candidate in candidates:  # substring match, longest first
        for name, index in headers.items():
            if candidate in name:
                return index
    return None


def index_tokens(raw_html: str) -> set[str]:
    """Every index code mentioned in a row's markup (text or data attributes)."""
    text = clean_text(raw_html)
    tokens = {match.group(1).upper() for match in INDEX_TOKEN_RE.finditer(text)}
    for name, value in _ATTR_RE.findall(raw_html):
        for match in INDEX_TOKEN_RE.finditer(value.upper()):
            tokens.add(match.group(1).upper())
        if name.lower() in {"data-index", "data-indices"} and value.strip():
            tokens |= {part.strip().upper() for part in re.split(r"[,\s|;]+", value) if part.strip()}
    return tokens


# ------------------------------------------------------------------ epoch/date
def derive_trade_date(epoch_seconds: int | float | None) -> date | None:
    """Convert a PSX epoch into a calendar trading date.

    PSX emits *Pakistan wall-clock* seconds. Treating them as UTC and adding the
    +5h offset lands the bar on the correct Karachi trading day; if that lands on
    a weekend we fall back to the plain UTC reading, which covers feeds that emit
    true UTC instead.
    """
    if epoch_seconds is None:
        return None
    try:
        stamp = float(epoch_seconds)
    except (TypeError, ValueError):
        return None
    if stamp > 1e11:  # milliseconds
        stamp = stamp / 1000.0
    if stamp <= 0:
        return None
    plain = datetime.fromtimestamp(stamp, tz=timezone.utc).date()
    shifted = (datetime.fromtimestamp(stamp, tz=timezone.utc) + timedelta(hours=PARS_E)).date()
    if shifted.weekday() < 5 or plain.weekday() >= 5:
        return shifted
    return plain


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5


# ------------------------------------------------------------- market-watch
@dataclass
class WatchRow:
    symbol: str
    ldcp: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    current: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    sector: str | None = None
    indices: set[str] = field(default_factory=set)


def parse_market_watch(html: str) -> list[WatchRow]:
    """Parse the market-watch table: quotes **and** index membership per symbol."""
    table_rows = rows(html)
    if not table_rows:
        hint = clean_text(html)[:200]
        raise ParseError(f"market-watch page contained no table rows ({hint!r})")

    header_index = None
    headers: dict[str, int] = {}
    for position, cells in enumerate(table_rows):
        candidate = _header_map(cells)
        if any("symbol" in name for name in candidate) and len(candidate) >= 4:
            header_index, headers = position, candidate
            break
    if header_index is None:
        raise ParseError(
            "market-watch: could not find a header row containing 'symbol'; "
            f"saw {table_rows[0][:3]}"
        )

    col_symbol = _find(headers, "symbol", "scrip")
    col_sector = _find(headers, "sector")
    col_listed = _find(headers, "listed in", "listed", "index")
    col_ldcp = _find(headers, "ldcp", "previous close", "prev")
    col_open = _find(headers, "open")
    col_high = _find(headers, "high")
    col_low = _find(headers, "low")
    col_current = _find(headers, "current", "close", "last")
    col_change = _find(headers, "change")
    col_change_pct = _find(headers, "change %", "change pct", "change percentage")
    col_volume = _find(headers, "volume", "turnover")

    parsed: list[WatchRow] = []
    for cells in table_rows[header_index + 1:]:
        if not cells:
            continue

        def cell(index: int | None) -> str | None:
            if index is None or index >= len(cells):
                return None
            return cells[index].text or None

        symbol = (cell(col_symbol) or "").strip().upper()
        if not symbol or symbol in {"SYMBOL", "-"}:
            continue
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,15}", symbol):
            continue

        row_markup = "".join(f"<td>{c.text}</td>" for c in cells)
        if col_listed is not None and col_listed < len(cells):
            listed_text = cells[col_listed].text
            row_markup += listed_text
        membership = index_tokens(row_markup) & (KNOWN_INDEX_CODES | index_tokens(row_markup))

        parsed.append(
            WatchRow(
                symbol=symbol,
                ldcp=to_float(cell(col_ldcp)),
                open=to_float(cell(col_open)),
                high=to_float(cell(col_high)),
                low=to_float(cell(col_low)),
                current=to_float(cell(col_current)),
                change=to_float(cell(col_change)),
                change_pct=to_float(cell(col_change_pct)),
                volume=to_float(cell(col_volume)),
                sector=cell(col_sector),
                indices=membership,
            )
        )
    if not parsed:
        raise ParseError("market-watch: header row found but no data rows parsed")
    return parsed


# ------------------------------------------------------------------- indices
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


def parse_indices(html: str) -> list[IndexRow]:
    """Parse the ``/indices`` page (levels for every published index)."""
    table_rows = rows(html)
    if not table_rows:
        raise ParseError("indices page contained no table rows")
    headers = _header_map(table_rows[0])
    col_name = _find(headers, "index", "name", "indices")
    col_high = _find(headers, "high")
    col_low = _find(headers, "low")
    col_current = _find(headers, "current", "level", "close")
    col_change = _find(headers, "change")
    col_pct = _find(headers, "change %", "% change", "%")
    col_volume = _find(headers, "volume", "turnover")

    out: list[IndexRow] = []
    for cells in table_rows[1:]:
        if not cells:
            continue
        raw_name = cells[col_name].text if col_name is not None and col_name < len(cells) else cells[0].text
        match = INDEX_TOKEN_RE.search(raw_name.upper())
        if not match:
            continue

        def cell(index: int | None) -> float | None:
            if index is None or index >= len(cells):
                return None
            return to_float(cells[index].text)

        out.append(
            IndexRow(
                code=match.group(1).upper(),
                name=raw_name,
                level=cell(col_current),
                change=cell(col_change),
                change_pct=cell(col_pct),
                high=cell(col_high),
                low=cell(col_low),
                volume=cell(col_volume),
            )
        )
    return out


# ---------------------------------------------------------- company page
_STAT_LABELS = {
    "market_cap": ("market cap", "market capitalization"),
    "shares": ("shares", "shares outstanding", "outstanding shares", "no. of shares"),
    "free_float": ("free float", "freefloat"),
    "free_float_pct": ("free float %", "free float percentage"),
    "pe": ("p/e", "pe ratio", "price to earnings", "p/e ratio"),
    "pb": ("p/b", "price to book", "p/b ratio"),
    "high_52w": ("52 week high", "52-week high", "52w high", "high 52"),
    "low_52w": ("52 week low", "52-week low", "52w low", "low 52"),
    "year_change_pct": ("1 year change", "year change", "1y change"),
    "ytd_change_pct": ("ytd", "year to date"),
}

_FIN_LABELS = {
    "revenue": ("sales", "revenue", "net sales", "turnover"),
    "gross_profit": ("gross profit",),
    "operating_income": ("operating profit", "operating income", "profit from operations"),
    "pretax_income": ("profit before tax", "profit before taxation", "pbt"),
    "income_tax_expense": ("taxation", "tax"),
    "net_income": ("profit after tax", "profit after taxation", "net profit", "pat"),
    "eps": ("eps", "earnings per share"),
    "dividend_per_share": ("dividend per share", "dps", "cash dividend"),
}


def _label_value_pairs(html: str) -> list[tuple[str, str]]:
    """Extract ``(label, value)`` pairs from stat blocks and label/value tables."""
    pairs: list[tuple[str, str]] = []
    # <div class="stats_label">X</div><div class="stats_value">Y</div>
    for label_block, value_block in re.findall(
        r"<(?:div|span|p)[^>]*class=\"[^\"]*(?:label|title|name)[^\"]*\"[^>]*>(.*?)"
        r"</(?:div|span|p)>\s*<(?:div|span|p)[^>]*class=\"[^\"]*(?:value|val|data|figure)[^\"]*\"[^>]*>(.*?)"
        r"</(?:div|span|p)>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        pairs.append((clean_text(label_block), clean_text(value_block)))
    # two-cell table rows
    for cells in rows(html):
        if len(cells) == 2:
            pairs.append((cells[0].text, cells[1].text))
    return pairs


def _best_label(label: str, table: dict[str, tuple[str, ...]]) -> str | None:
    """Pick the key whose needle is the *longest* match, not the first one.

    Without this, "free float %" is captured as ``free_float`` and
    "profit after tax" is captured as ``income_tax_expense``.
    """
    best_key: str | None = None
    best_score = 0
    for key, needles in table.items():
        for needle in needles:
            if needle in label and len(needle) > best_score:
                best_key, best_score = key, len(needle)
    return best_key


def parse_company_stats(html: str) -> dict[str, float | None]:
    """Best-effort company statistics (market cap, P/E, free float, 52w range)."""
    stats: dict[str, float | None] = {key: None for key in _STAT_LABELS}
    for label, value in _label_value_pairs(html):
        lowered = re.sub(r"[^a-z0-9%. /-]+", " ", label.lower())
        key = _best_label(lowered, _STAT_LABELS)
        if key is None or stats[key] is not None:
            continue
        parsed = to_float(value)
        if parsed is not None:
            stats[key] = parsed
    return stats


def parse_company_financials(html: str, max_years: int = 5) -> list[dict[str, Any]]:
    """Best-effort annual financials from the company page.

    PSX renders a row-per-line-item table with one column per fiscal year. If the
    page does not expose that table (or changed shape), an empty list is returned
    and the raw HTML stays available in ``raw_payloads`` for a later parser.
    """
    table_rows = rows(html)
    for cells in table_rows:
        year_columns: list[tuple[int, int]] = []
        for index, cell in enumerate(cells[1:], start=1):
            match = re.search(r"(?:fy\s*)?(20\d{2})", cell.text, re.IGNORECASE)
            if match:
                year_columns.append((index, int(match.group(1))))
        if len(year_columns) < 2:
            continue
        years: dict[int, dict[str, Any]] = {year: {"fiscal_year": year} for _, year in year_columns}
        for row in table_rows:
            if len(row) <= max(index for index, _ in year_columns):
                continue
            label = re.sub(r"[^a-z0-9 ]+", " ", row[0].text.lower()).strip()
            if not label:
                continue
            key = _best_label(label, _FIN_LABELS)
            if key is None:
                continue
            for index, year in year_columns:
                value = to_float(row[index].text)
                if value is not None and years[year].get(key) is None:
                    years[year][key] = value
        usable = [record for record in years.values() if len(record) > 1]
        if usable:
            usable.sort(key=lambda item: item["fiscal_year"], reverse=True)
            return usable[:max_years]
        break
    return []


# ------------------------------------------------------- historical (monthly)
def parse_historical(html: str) -> list[dict[str, Any]]:
    """Parse ``POST /historical`` into daily OHLC rows (oldest first)."""
    out: list[dict[str, Any]] = []
    for cells in rows(html):
        if len(cells) < 5:
            continue
        texts = [cell.text for cell in cells]
        if texts[0].strip().upper() in {"TIME", "DATE", ""}:
            continue
        trade_date = None
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%d %b %Y", "%d-%m-%Y"):
            try:
                trade_date = datetime.strptime(texts[0].strip(), fmt).date()
                break
            except ValueError:
                continue
        if trade_date is None:
            continue
        close = to_float(texts[4]) if len(texts) > 4 else None
        if close is None:
            continue
        out.append(
            {
                "trade_date": trade_date,
                "open": to_float(texts[1]),
                "high": to_float(texts[2]),
                "low": to_float(texts[3]),
                "close": close,
                "volume": to_float(texts[5]) if len(texts) > 5 else None,
            }
        )
    out.sort(key=lambda item: item["trade_date"])
    return out


def parse_eod_series(payload: Any, symbol: str = "?") -> list[dict[str, Any]]:
    """Convert a ``/timeseries/eod`` JSON payload into bar dicts.

    The portal returns ``[[epoch, close, volume, open], …]`` **newest first** and
    has no high/low on this route (only ``POST /historical`` carries them).
    """
    if isinstance(payload, dict):
        data = payload.get("data")
        status = payload.get("status")
        if status not in (None, 1, "1", "ok"):
            raise ParseError(
                f"eod/{symbol}: portal status {status!r} "
                f"({payload.get('message') or 'no message'})"
            )
    else:
        data = payload
    if not isinstance(data, list):
        raise ParseError(f"eod/{symbol}: expected a list of bars")
    bars: dict[date, dict[str, Any]] = {}
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        try:
            epoch = int(float(row[0]))
            close = float(row[1])
            volume = float(row[2]) if row[2] is not None else None
            open_price = float(row[3]) if len(row) > 3 and row[3] is not None else None
        except (TypeError, ValueError):
            continue
        trade_date = derive_trade_date(epoch)
        if trade_date is None or close <= 0:
            continue
        bars[trade_date] = {
            "trade_date": trade_date,
            "ts": epoch,
            "open": open_price,
            "high": None,
            "low": None,
            "close": close,
            "volume": volume,
        }
    ordered: Iterable[dict[str, Any]] = [bars[key] for key in sorted(bars)]
    return list(ordered)
