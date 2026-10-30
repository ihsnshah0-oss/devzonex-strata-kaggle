"""Render a full_report dict as a clean, simple-text A4 PDF (fpdf2)."""
from fpdf import FPDF

_CLEAN = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'",
          "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u2192": "->",
          "\u2190": "<-", "\u2191": "(up) ", "\u2193": "(down) ",
          "\u2714": "[ok]", "\u2705": "[YES]", "\u274c": "[NO]",
          "\u26a0": "!", "\u00d7": "x", "\u2026": "...", "\u00b7": "-",
          "\u2795": "+", "\u2796": "-", "\u00a0": " "}


def cl(t) -> str:
    s = "" if t is None else str(t)
    for k, v in _CLEAN.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


class Rep(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, cl(f"PSX Live & Research Executive Report — page {self.page_no()}/{{nb}}"), align="C")


def _gap(pdf, h=3):
    pdf.ln(h)


def _need(pdf, h=30):
    if pdf.get_y() + h > 277:
        pdf.add_page()


def _h(pdf, num, title):
    _need(pdf, 22)
    _gap(pdf, 5)
    pdf.set_x(pdf.l_margin)  # fpdf2 can leave the cursor at the right margin
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 7, cl(f"{num}. {title}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(20, 60, 120)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    _gap(pdf, 2)
    pdf.set_text_color(0, 0, 0)


def _kv(pdf, rows):
    pdf.set_font("Helvetica", "", 10)
    for label, val in rows:
        _need(pdf, 12)
        y0 = pdf.get_y()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_xy(15, y0)
        pdf.multi_cell(58, 5.5, cl(label))
        y1 = pdf.get_y()
        pdf.set_font("Helvetica", "", 10)
        pdf.set_xy(73, y0)
        pdf.multi_cell(122, 5.5, cl(val))
        pdf.set_y(max(y1, pdf.get_y()) + 0.5)


def _bullets(pdf, items):
    pdf.set_font("Helvetica", "", 10)
    for it in items:
        _need(pdf, 16)
        pdf.set_x(18)
        pdf.multi_cell(177, 5.5, cl(f"- {it}"))
        _gap(pdf, 1)


def _para(pdf, text):
    pdf.set_font("Helvetica", "", 10)
    _need(pdf, 16)
    pdf.set_x(pdf.l_margin)  # fpdf2 can leave the cursor at the right margin
    pdf.multi_cell(0, 5.5, cl(text))
    _gap(pdf, 1)


def build_pdf(rep: dict) -> bytes:
    pdf = Rep("P", "mm", "A4")
    pdf.alias_nb_pages("{nb}")
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()

    # Title block
    pdf.set_fill_color(20, 60, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 11, cl(f"{rep.get('symbol', '?')} — {rep.get('company', '')}"), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, cl("PSX Executive Stock Report (A-to-Z analysis)"), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 7, cl(f"Sector: {rep.get('sector') or '—'}   |   Data as of: {rep.get('as_of') or '—'}   |   "
                      f"Generated: {(rep.get('generated_at') or '')[:16]} PKT"), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(0, 0, 0)
    _gap(pdf, 2)

    ex = rep.get("executive", {}) or {}
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, cl(f"Verdict: {ex.get('verdict', '?')}   |   Action: {ex.get('action', '?')}   |   "
                      f"Confidence: {ex.get('confidence', '?')}"), new_x="LMARGIN", new_y="NEXT")
    _h(pdf, 1, "Executive summary")
    _bullets(pdf, ex.get("thesis", []))

    _h(pdf, 2, "Key stats at a glance")
    _kv(pdf, rep.get("key_stats", []))

    _h(pdf, 3, "Price & trend")
    _kv(pdf, rep.get("price_trend", []))

    _h(pdf, 4, "Technical signals")
    _kv(pdf, rep.get("technicals", []))

    _h(pdf, 5, "Quant scorecard (rule votes)")
    q = rep.get("quant", {}) or {}
    t = q.get("trader", {}) or {}
    _para(pdf, f"Trader action: {t.get('action', '?')} (score {t.get('score', '?')}). One line per strategy:")
    _bullets(pdf, [f"{v.get('strategy', '?')}: {str(v.get('signal', '?')).upper()} — {v.get('note', '')}"
                   for v in (q.get("votes", []) or [])])

    _h(pdf, 6, "Bull vs bear debate")
    d = rep.get("debate", {}) or {}
    _para(pdf, f"Bulls {d.get('bull_score', '?')} vs bears {d.get('bear_score', '?')} → net {d.get('net', '?')} "
               f"({d.get('verdict', '?')}).")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Bull case (why it can rise):", new_x="LMARGIN", new_y="NEXT")
    _bullets(pdf, [f"{f.get('factor', '')}: {f.get('detail', '')}" for f in (d.get("bull_factors", []) or [])])
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Bear case (why it can fall):", new_x="LMARGIN", new_y="NEXT")
    _bullets(pdf, [f"{f.get('factor', '')}: {f.get('detail', '')}" for f in (d.get("bear_factors", []) or [])])

    _h(pdf, 7, "Trade plan (swing 2-8 weeks)")
    tp = rep.get("trade_plan", {}) or {}
    p = tp.get("proposal", {}) or {}
    er = p.get("entry_range") or ["--", "--"]
    _kv(pdf, [("Action", p.get("action", "?")),
              ("Buy zone", f"Rs{er[0]} - Rs{er[1]}"),
              ("Stop loss", f"Rs{p.get('stop_loss', '--')} (exit if this breaks — idea is wrong)"),
              ("Target 1 / 2", f"Rs{p.get('target_1', '--')} / Rs{p.get('target_2', '--')}"),
              ("Reward : risk", f"{p.get('reward_risk_t1', '?')} / {p.get('reward_risk_t2', '?')}"),
              ("Suggested size", f"{p.get('suggested_qty', 0):,} shares = Rs{p.get('est_cost_rs', '--')}"),
              ("Money at risk", f"Rs{p.get('risk_rs', '--')} ({p.get('risk_pct', '?')}% of Rs{p.get('capital_assumed', '--')})"),
              ("Valid until", str(p.get("valid_until", "?"))),
              ("Supports", f"Rs{tp.get('supports', ['--','--'])[0]} / Rs{tp.get('supports', ['--','--'])[1]}"),
              ("Resistances", f"Rs{tp.get('resistances', ['--','--'])[0]} / Rs{tp.get('resistances', ['--','--'])[1]}"),
              ("Assessment", tp.get("assessment", "") or "--")])

    _h(pdf, 8, "Fundamentals")
    _kv(pdf, rep.get("fundamentals", []))

    _h(pdf, 9, "News & sentiment")
    news = rep.get("news", []) or []
    if news:
        _bullets(pdf, [f"{n.get('title', '')} ({n.get('source', '?')}, {n.get('published', '?')}) "
                       f"[{n.get('sentiment', 'neutral')}]" + (f" — {n.get('summary', '')}" if n.get("summary") else "")
                       for n in news[:6]])
    else:
        _para(pdf, "No fresh company-specific headlines in the last feeds — market-level news only.")

    _h(pdf, 10, "Strategy check (3-year backtest)")
    b = rep.get("backtest", {}) or {}
    if "error" in b:
        _para(pdf, f"Backtest unavailable: {b['error']}")
    else:
        _para(pdf, b.get("line", ""))
        m = b.get("metrics", {}) or {}
        _kv(pdf, [("Total return", f"{m.get('total_return_pct', '?')}% (buy-hold {m.get('buy_hold_pct', '?')}%)"),
                  ("CAGR", f"{m.get('cagr_pct', '?')}%"), ("Sharpe", str(m.get("sharpe", "?"))),
                  ("Max fall", f"{m.get('max_drawdown_pct', '?')}%"), ("Trades", str(m.get("trades", "?"))),
                  ("Win rate", f"{m.get('win_rate_pct', '?')}%"), ("Profit factor", str(m.get("profit_factor", "?")))])

    _h(pdf, 11, "Deep thinking checklist")
    dt = rep.get("deep_thinking", {}) or {}
    _bullets(pdf, dt.get("steps", []) or ["n/a"])
    if dt.get("llm_narrative"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Local-AI analyst note (bonus opinion):", new_x="LMARGIN", new_y="NEXT")
        _para(pdf, dt["llm_narrative"])

    deep = rep.get("deep") or {}
    if deep:
        _deep_sections(pdf, deep)

    _gap(pdf, 4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 0, 0)
    pdf.multi_cell(0, 5, cl(f"Disclaimer: {rep.get('disclaimer', '')}"))
    return bytes(pdf.output())


def _fb(v, nd=1):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    a = abs(v)
    if a >= 1e12:
        return f"{v/1e12:,.{nd}f}T"
    if a >= 1e9:
        return f"{v/1e9:,.{nd}f}B"
    if a >= 1e6:
        return f"{v/1e6:,.{nd}f}M"
    return f"{v:,.{nd}f}"


def _pct(v):
    return "—" if v is None else f"{v:,.1f}%"


def _deep_sections(pdf, deep):
    pr, st, ra, va, pe_, it = (deep.get(k) or {} for k in
                              ("profile", "statements", "ratios",
                               "valuation", "peers", "intel"))
    pdf.add_page()
    _h(pdf, "A", "COMPANY INTELLIGENCE (business model · moat · assets)")
    _kv(pdf, [("Company", f"{pr.get('company','')} — {pr.get('sector','')}"),
              ("Business model", cl(pr.get("business") or "—")),
              ("Customers", cl(pr.get("customers") or "—")),
              ("Economic moat", cl(pr.get("moat") or "—")),
              ("Total assets", _fb(pr.get("assets", {}).get("total_assets"))),
              ("Equity / Liabilities", f"{_fb(pr.get('assets', {}).get('total_equity'))} / "
               f"{_fb(pr.get('assets', {}).get('total_liabilities'))}"),
              ("Market cap", _fb(pr.get("assets", {}).get("market_cap")))])
    _h(pdf, "B", "INDUSTRY TRENDS & MANAGEMENT QUALITY")
    sp = it.get("sector_perf") or {}
    _para(pdf, f"Industry direction: {it.get('industry_trend','—')}" +
          (f" (sector 1Y {sp.get('y1')}%, 3M {sp.get('m3')}% mcap-weighted)."
           if sp else "."))
    _bullets(pdf, it.get("management", []) or ["—"])
    _h(pdf, "C", "FINANCIAL STATEMENTS (last reported years, PKR)")
    yrs = st.get("years") or []
    hdr = "Metric".ljust(24) + "".join(y.ljust(12) for y in yrs)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5.5, cl(hdr), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for label, key in [("Revenue", "revenue"), ("Net income", "net_income"),
                       ("Free cash flow", "fcf"), ("Total assets", "assets"),
                       ("Total liabilities", "liabilities"), ("Equity", "equity")]:
        row = label.ljust(24) + "".join(
            _fb(v).ljust(12) for v in (st.get(key) or [None] * 4)[:4])
        pdf.cell(0, 5.5, cl(row), new_x="LMARGIN", new_y="NEXT")
    _kv(pdf, [("Revenue 3Y CAGR", _pct(st.get("revenue_cagr_3y"))),
              ("Net income 3Y CAGR", _pct(st.get("ni_cagr_3y"))),
              ("Net margin", _pct(st.get("net_margin_pct"))),
              ("Debt / Equity", "—" if st.get("de_ratio") is None else f"{st['de_ratio']:.2f}")])
    _h(pdf, "D", "KEY RATIOS")
    _kv(pdf, [("P/E", "—" if ra.get("pe") is None else f"{ra['pe']:,.1f}"),
              ("P/B", "—" if ra.get("pb") is None else f"{ra['pb']:,.2f}"),
              ("ROE / ROA", f"{_pct(ra.get('roe'))} / {_pct(ra.get('roa'))}"),
              ("Dividend yield", _pct(ra.get("dividend_yield_pct"))),
              ("Payout ratio", _pct(ra.get("payout_ratio_pct")) +
               (" (sustainable)" if ra.get("dividend_sustainable") else " (stretched)")),
              ("FCF yield", _pct(ra.get("fcf_yield_pct")))])
    _h(pdf, "E", "VALUATION (DCF · DDM · Graham · relative)")
    for m, v in (va.get("models") or {}).items():
        _kv(pdf, [(m, f"Rs {v:,.2f}")])
    _kv(pdf, [("Fair value (blend)", "—" if va.get("fair_value") is None
               else f"Rs {va['fair_value']:,.2f}"),
              ("Price", f"Rs {(va.get('price') or 0):,.2f}"),
              ("Margin of safety", _pct(va.get("margin_of_safety_pct"))),
              ("Verdict", va.get("verdict", "—"))])
    _bullets(pdf, va.get("notes", []) or [])
    if pe_.get("peers"):
        _h(pdf, "F", f"PEER COMPARISON — {pe_.get('sector','')}")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5.5, cl("Symbol".ljust(12) + "Mcap".ljust(12) + "P/E".ljust(10) + "DivYld"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for p_ in pe_["peers"][:8]:
            pdf.cell(0, 5.5, cl((p_["s"] or "").ljust(12) +
                                _fb(p_.get("mcap"), 0).ljust(12) +
                                (f"{p_['pe']:,.1f}" if p_.get("pe") else "—").ljust(10) +
                                (_pct(p_.get("dy")) if p_.get("dy") else "—")),
                     new_x="LMARGIN", new_y="NEXT")
        if pe_.get("sector_pe_median"):
            _para(pdf, f"Sector median P/E {pe_['sector_pe_median']:,.1f}" +
                  (f" — target ranks {pe_.get('target_rank')} of listed peers on P/E."
                   if pe_.get("target_rank") else "."))
    _h(pdf, "G", "PROS & CONS BEFORE INVESTING")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "PROs:", new_x="LMARGIN", new_y="NEXT")
    _bullets(pdf, it.get("pros", []) or ["—"])
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "CONs:", new_x="LMARGIN", new_y="NEXT")
    _bullets(pdf, it.get("cons", []) or ["—"])

