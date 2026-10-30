"""Render the side-by-side stock comparison as a landscape A4 PDF (fpdf2)."""
from fpdf import FPDF

from .report_pdf import cl


def _bn(v):
    try:
        return f"Rs {float(v) / 1e9:,.1f} bn"
    except Exception:
        return "—"


def _pct(v, nd=2):
    try:
        return f"{float(v):+{nd}f}%"
    except Exception:
        return "—"


def _x(v, nd=2):
    try:
        return f"{float(v):{nd}f}"
    except Exception:
        return "—"


def _rs(v):
    try:
        return f"Rs {float(v):,.2f}"
    except Exception:
        return "—"


def _pos(v):
    try:
        return f"{float(v):.0f}% of range"
    except Exception:
        return "—"


def build_pdf(data: dict) -> bytes:
    stocks = data.get("stocks") or []
    n = len(stocks)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, 12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(20, 20, 22)
    pdf.cell(0, 8, cl("PSX Live & Research — Side-by-Side Comparison (A to Z)"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(110, 110, 115)
    pdf.cell(0, 5, cl("Sources: DPS snapshot & EOD history (psxdata) · Yahoo Finance statements · "
                      "financials.psx.com.pk filings · generated " + str(data.get("as_of", ""))), ln=True)
    pdf.ln(2)

    F = [s.get("fund") or {} for s in stocks]
    T = [s.get("tech") or {} for s in stocks]
    SE = [s.get("session") or {} for s in stocks]

    W = 277
    lab = 62
    colw = (W - lab) / max(1, n)

    def head():
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(20, 20, 22)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, pdf.get_y())
        pdf.cell(lab, 7, cl("Metric"), border=1, fill=True)
        for i, s in enumerate(stocks):
            pdf.cell(colw, 7, cl(s.get("symbol", "")), border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(25, 25, 28)

    def section(title):
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(235, 235, 245)
        pdf.set_xy(10, pdf.get_y())
        pdf.cell(W, 6.5, cl(title.upper()), border=1, fill=True)
        pdf.ln()

    def row(label, vals):
        pdf.set_font("Helvetica", "B", 8)
        y0 = pdf.get_y()
        pdf.set_xy(10, y0)
        pdf.multi_cell(lab, 5, cl(label), border=1)
        y1 = pdf.get_y()
        pdf.set_font("Helvetica", "", 8)
        for i, v in enumerate(vals):
            pdf.set_xy(10 + lab + i * colw, y0)
            pdf.multi_cell(colw, 5, cl(v), border=1, align="C")
            y1 = max(y1, pdf.get_y())
        pdf.set_y(y1)

    def above(v):
        return "above" if v else ("below" if v is not None else "—")

    head()
    section("Market")
    row("Company", [f.get("name") or "—" for f in F])
    row("Sector", [f.get("sector") or "—" for f in F])
    row("Price", [_rs(f.get("price")) for f in F])
    row("Day change", [_pct(f.get("change_pct")) for f in F])
    row("Today: open / high / low",
        [f"{_rs(se.get('open'))} / {_rs(se.get('high'))} / {_rs(se.get('low'))}" for se in SE])
    row("Volume today", [f"{se.get('volume', 0):,.0f}" for se in SE])
    row("Who is winning today", [se.get("direction", "—") for se in SE])
    row("Market cap", [_bn(f.get("market_cap")) for f in F])
    row("Avg volume (30d)", [f"{float(f.get('avg_vol_30d') or 0):,.0f}" for f in F])
    row("Index membership", [f.get("indices") or "—" for f in F])
    row("Last official filing", [str(s.get("last_filing") or "—") for s in stocks])

    section("Performance")
    row("1 month", [_pct(f.get("perf_1m")) for f in F])
    row("3 months", [_pct(f.get("perf_3m")) for f in F])
    row("6 months", [_pct(f.get("perf_6m")) for f in F])
    row("1 year", [_pct(f.get("perf_1y")) for f in F])
    row("Price CAGR (full history)", [_pct(s.get("price_cagr")) for s in stocks])
    row("52-week high / low", [f"{_rs(f.get('high_52w'))} / {_rs(f.get('low_52w'))}" for f in F])
    row("Position in 52-week range", [_pos(f.get("wk52_pos")) for f in F])
    row("Off 52-week high", [_pct(f.get("off_high_pct")) for f in F])

    section("Valuation")
    row("P/E (trailing)", [_x(f.get("pe_ratio")) for f in F])
    row("P/E (forward)", [_x(f.get("forward_pe")) for f in F])
    row("Price / book", [_x(f.get("price_to_book")) for f in F])
    row("Dividend yield", [_pct(f.get("dividend_yield"), 2) for f in F])
    row("Payout ratio", [_pct(f.get("payout_ratio"), 1) for f in F])
    row("EPS (ttm)", [_rs(f.get("eps")) for f in F])

    section("FY financial snapshot (statements)")
    row("Total revenue", [_bn(f.get("revenue")) for f in F])
    row("Net profit", [_bn(f.get("net_income")) for f in F])
    row("Revenue growth YoY", [_pct(f.get("revenue_growth_y")) for f in F])
    row("Net profit growth YoY", [_pct(f.get("net_income_growth")) for f in F])
    row("EPS growth YoY", [_pct(f.get("eps_growth")) for f in F])
    row("Total assets", [_bn(f.get("total_assets")) for f in F])
    row("Total equity", [_bn(f.get("total_equity")) for f in F])
    row("Total liabilities", [_bn(f.get("total_liabilities")) for f in F])
    row("Total debt", [_bn(f.get("total_debt")) for f in F])

    section("Profitability & financial health")
    row("ROE", [_pct(f.get("roe")) for f in F])
    row("ROA", [_pct(f.get("roa")) for f in F])
    row("Net profit margin", [_pct(f.get("profit_margin")) for f in F])
    row("Debt / equity", [_x(f.get("debt_equity")) for f in F])
    row("Current ratio", [_x(f.get("current_ratio")) for f in F])
    row("Free cash flow", [_bn(f.get("free_cashflow")) for f in F])
    row("Book value / share", [_rs(f.get("book_value")) for f in F])
    row("Beta", [_x(f.get("beta")) for f in F])

    section("Technicals")
    row("RSI (14)", [_x(t.get("rsi14"), 0) for t in T])
    row("vs 20-day average", [above(t.get("close") is not None and t.get("sma20") is not None
                                    and t["close"] >= t["sma20"]) for t in T])
    row("vs 50-day average", [above(t.get("above_sma50")) for t in T])
    row("vs 200-day average", [above(t.get("above_sma200")) for t in T])
    row("MACD", [("bullish" if t.get("macd_bull") else "bearish")
                 if t.get("macd_bull") is not None else "—" for t in T])
    row("ATR (daily swing)", [_pct(t.get("atr_pct"), 1) for t in T])
    row("Volume vs average", [_x(t.get("vol_ratio")) + "x" for t in T])
    row("20-day breakout", [("Breakout" if t.get("breakout_20d") else
                            "Breakdown" if t.get("breakdown_20d") else "Inside range") for t in T])

    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(120, 120, 125)
    pdf.ln(3)
    pdf.multi_cell(0, 4, cl("For education, not financial advice. Data may be delayed. "
                            "Generated by PSX Live & Research (free & open-source)."))
    return bytes(pdf.output())
