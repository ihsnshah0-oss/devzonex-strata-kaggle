"""One-page Master Watchlist PDF — landscape A4, printable before market open."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fpdf import FPDF

from .report_pdf import cl

PKT = ZoneInfo("Asia/Karachi")


def _signal(s: dict) -> str:
    if not s or s.get("error"):
        return "—"
    p = 0
    p += 1 if s.get("above_ema50") else -1
    p += 1 if s.get("above_ema200") else -1
    p += 1 if s.get("macd_bull") else -1
    r = s.get("rsi14")
    if r is not None:
        p += -1 if r > 70 else (1 if r < 30 else (1 if r >= 50 else -1))
    if s.get("breakout_20d"):
        p += 1
    if s.get("breakdown_20d"):
        p -= 1
    return ("STRONG BUY" if p >= 3 else "BUY" if p >= 1 else
            "STRONG SELL" if p <= -3 else "SELL" if p <= -1 else "HOLD")


def _trend(s: dict) -> str:
    out = []
    for lvl in (5, 10, 20, 50, 100, 200):
        v = s.get(f"above_ema{lvl}")
        out.append(f"{lvl}:{'A' if v else 'B' if v is False else '-'}")
    return " ".join(out)   # A = above, B = below


def build(rows: list[dict]) -> bytes:
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    now = datetime.now(PKT)

    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(20, 20, 30)
    pdf.cell(0, 9, cl("PSX Live & Research — Master Watchlist"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 6, cl(f"One-page pre-market sheet · {now:%a %d %b %Y, %H:%M PKT} · "
                      f"trend: EMA 5/10/20/50/100/200-day, A = price above, B = below"), ln=True)
    pdf.ln(3)

    cols = [("Sym", 16), ("Company", 54), ("Sector", 40), ("Price Rs", 22), ("Day%", 14),
            ("5d%", 14), ("21d%", 14), ("RSI", 11), ("Trend EMA 5-200", 52),
            ("P/E", 12), ("Yld%", 12), ("Signal", 26)]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(235, 238, 245)
    pdf.set_text_color(30, 30, 40)
    for name, w in cols:
        pdf.cell(w, 7, cl(name), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for r in rows:
        s = r.get("snapshot") or {}
        sig = _signal(s)
        if "SELL" in sig:
            pdf.set_text_color(160, 30, 40)
        elif "BUY" in sig:
            pdf.set_text_color(20, 120, 70)
        else:
            pdf.set_text_color(60, 60, 60)
        vals = [
            (r.get("symbol", ""), 16, "L"),
            (cl((r.get("name") or "")[:34]), 62, "L"),
            (cl((r.get("sector") or "")[:24]), 40, "L"),
            (f"{s.get('close'):,.2f}" if s.get("close") is not None else "-", 22, "R"),
            (f"{r.get('day_chg'):+.2f}" if r.get("day_chg") is not None else "-", 14, "R"),
            (f"{r.get('chg5'):+.1f}" if r.get("chg5") is not None else "-", 14, "R"),
            (f"{r.get('chg21'):+.1f}" if r.get("chg21") is not None else "-", 14, "R"),
            (f"{s.get('rsi14'):.0f}" if s.get("rsi14") is not None else "-", 11, "C"),
            (cl(_trend(s)), 44, "C"),
            (f"{r.get('pe'):.1f}" if r.get("pe") is not None else "-", 12, "R"),
            (f"{r.get('yield'):.1f}" if r.get("yield") is not None else "-", 12, "R"),
            (cl(sig), 26, "C"),
        ]
        # day% cell coloured by direction
        for txt, w, al in vals:
            pdf.cell(w, 6.2, txt, border=1, align=al)
        pdf.ln()
    pdf.set_text_color(120, 120, 120)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.ln(2)
    pdf.cell(0, 5, cl("Signal rule: trend + momentum score (SMA 50/200, MACD, RSI, 20-day breakouts). "
                      "Free data via PSX/DPS — for personal research, not investment advice."), ln=True)
    return bytes(pdf.output())
