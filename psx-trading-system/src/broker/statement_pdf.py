"""Broker statement PDF parser — finds your open positions in a statement.

Broker statements differ (AKD, Arif Habib, KASB, NextTrade, ...) so this is a
heuristic reader: it scans every text line for an ALL-CAPS symbol followed by
numbers, then decides which numbers are quantity / average cost / market value.
The strongest signal is the arithmetic one:  value ≈ qty × avg-cost.

Nothing is applied automatically — the dashboard always shows a preview first.
"""
import io
import re

NUM_RE = re.compile(r"-?\d[\d,]*\.\d{1,4}|-?\d[\d,]+")
SYM_RE = re.compile(r"\b[A-Z][A-Z0-9&.\-]{1,11}\b")
SKIP_WORDS = {
    "TOTAL", "VALUE", "MARKET", "COST", "AVG", "AVERAGE", "QTY", "QUANTITY",
    "SYMBOL", "SECURITY", "SHARES", "SHARE", "PRICE", "LAST", "PORTFOLIO",
    "HOLDINGS", "POSITIONS", "POSITION", "INVESTED", "AMOUNT", "PURCHASE",
    "BOOK", "GAIN", "LOSS", "UNREALIZED", "REALIZED", "PNL", "P", "L",
    "CASH", "BALANCE", "ACCOUNT", "STATEMENT", "PERIOD", "DATE", "RATE",
    "COMMISSION", "CDC", "NCC", "AVAILABLE", "LEDGER", "EQUITY", "NET",
    "ASSETS", "LIABILITIES", "DEPOSIT", "WITHDRAWAL", "BUY", "SELL", "TRADE",
    "TRADES", "ORDER", "REPORT", "PAGE", "OF", "THE", "AND", "FOR", "RS",
    "PKR", "PSX", "LTD", "LIMITED", "PLC", "CO", "CORP", "PK",
}
SYM_OK = re.compile(r"^[A-Z]")


def _nums(line: str) -> list[float]:
    out = []
    for t in NUM_RE.findall(line):
        try:
            out.append(float(t.replace(",", "")))
        except ValueError:
            pass
    return out


def _symbols(line: str) -> list[str]:
    syms = []
    for t in SYM_RE.findall(line):
        if t in SKIP_WORDS or not SYM_OK.match(t):
            continue
        # skip tokens that are clearly part of a company name ("OIL", "BANK"...)
        syms.append(t)
    return syms


def _pick(numbers: list[float]) -> tuple[float | None, float | None, str]:
    """Choose (qty, avg_cost, how) from the numbers found on a line."""
    pos = [abs(n) for n in numbers]
    # 1) arithmetic match: value ≈ qty × avg
    for i, q in enumerate(pos):
        for j, a in enumerate(pos):
            if i == j or a <= 0 or q <= 0:
                continue
            v = q * a
            for k, c in enumerate(pos):
                if k in (i, j):
                    continue
                if v and abs(c - v) / v < 0.03:
                    return q, a, "qty x avg = value matched"
    # 2) fallback: first integer-looking = qty, first decimal = avg cost
    ints = [n for n in pos if n == int(n) and n >= 1]
    decs = [n for n in pos if n != int(n) and 0.5 < n < 100000]
    if ints and decs:
        return max(ints), decs[0], "qty + avg guess (check it)"
    return None, None, ""


def parse_pdf(data: bytes) -> dict:
    """Return {rows:[{symbol,qty,rate,value,how}], notes:[...]}."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        return {"rows": [], "notes": [f"Could not read this file as a PDF: {e}"]}

    rows: dict[str, dict] = {}
    notes: list[str] = []
    scanned = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 6:
                continue
            scanned += 1
            syms = _symbols(line)
            if not syms:
                continue
            nums = _nums(line)
            if len(nums) < 2:
                continue
            qty, avg, how = _pick(nums)
            if not qty or not avg or avg <= 0 or avg >= 100000:
                continue
            sym = syms[0]
            value = round(qty * avg, 2)
            rows[sym] = {"symbol": sym, "qty": qty, "rate": avg,
                         "value": value, "how": how,
                         "source_line": line[:110]}

    out = sorted(rows.values(), key=lambda r: r["symbol"])
    if not out:
        notes.append("No positions could be detected. If this statement lists "
                     "holdings as an image (scanned PDF), it cannot be read "
                     "automatically — add the positions with 'Add a trade' instead.")
    notes.append(f"Scanned {len(reader.pages)} page(s), {scanned} lines; "
                 f"{len(out)} position(s) detected. CHECK every row before applying.")
    return {"rows": out, "notes": notes}
