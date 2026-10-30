"""Single-stock Trade Plan PDF (Money tab).

Combines, for ONE chosen stock:
  * the full research data (verdict, thesis, technicals, fundamentals, news)
  * the best-fit strategy, found by backtesting all engine strategies
  * a concrete trade plan sized by the user's saved Money plan

Build:  trade_plan_pdf.build("OGDC") -> (pdf_bytes, filename)
"""
import re
from datetime import datetime, timedelta, timezone

from src.app.report_pdf import Rep, cl, _kv, _bullets, _para, _need, _gap

_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2B50]")


def _clean(t) -> str:
    """Drop emojis, then apply the latin-1 cleaner (keeps built-in fonts happy)."""
    return cl(_EMOJI.sub("", str(t)))
from src.analysis import full_report as frep
from src.analysis import money as money_mod
from src.analysis import risk as risk_mod
from src.backtest import engine as bt

PKT = timezone(timedelta(hours=5))
START = "2021-01-01"
MIN_TRADES = 5
GREEN = (22, 163, 74)
RED = (220, 38, 38)
GREY = (110, 110, 115)
DARK = (20, 20, 22)

FAMILY = {
    "pb1": "momentum ride (short EMAs + CCI)",
    "pb2": "trend pullback (EMA cycle + RSI divergence)",
    "pb3": "dip-buying inside a positive weekly stage",
    "pb4": "long-horizon stage/cycle shift (weekly MAs)",
    "pb5": "adaptive: momentum in trends, reversion in ranges",
    "pb6": "counter-trend divergence bounce",
    "sma_cross": "classic trend following",
    "rsi_meanrev": "oversold bounce (mean reversion)",
    "breakout": "donchian breakout on volume",
    "momentum": "quarterly momentum trend",
    "macd": "MACD trend following",
    "stage2_breakout": "weekly stage-2 breakout (Weinstein)",
}


def family_note(sid: str) -> str:
    for k, v in FAMILY.items():
        if sid.startswith(k):
            return v
    if sid.startswith(("l01", "l15")):
        return "trend pullback pattern"
    if sid.startswith(("l02", "l06", "l07", "l08", "l12", "l13", "l14")):
        return "breakout / structure pattern"
    if sid.startswith(("l09", "l10", "l16", "l18", "l20", "l11")):
        return "bottom-picking / reversal pattern"
    if sid.startswith(("l04", "l17")):
        return "candle-momentum burst"
    if sid.startswith(("l03", "l19", "l21")):
        return "range / value-area play"
    return "pattern setup"


def verdict(best_ret, bh):
    if best_ret is None:
        return "no strategy passed the trade gate"
    beats = bh is None or best_ret >= bh
    if beats and best_ret > 50:
        return "STRONG fit (beats buy & hold)"
    if beats:
        return "good fit (beats buy & hold)"
    if best_ret > 20:
        return "usable, but buy & hold did better"
    return "weak fit"


def best_strategies(sym: str) -> tuple[float | None, list[dict]]:
    """Backtest every engine strategy on this one stock."""
    results: list[dict] = []
    bh = None
    for sid, spec in bt.STRATEGIES.items():
        try:
            r = bt.run(sym, sid, start=START)
        except Exception:
            continue
        if "error" in r:
            continue
        m = r["metrics"]
        if bh is None:
            bh = m["buy_hold_pct"]
        if m["trades"] >= MIN_TRADES:
            ot = m.get("open_trade") or {}
            results.append({
                "id": sid, "name": spec["name"], "trades": m["trades"],
                "ret": m["total_return_pct"], "wr": m["win_rate_pct"],
                "dd": m["max_drawdown_pct"], "pf": m["profit_factor"],
                "open": ot.get("unrealized_pct"),
            })
    results.sort(key=lambda x: x["ret"], reverse=True)
    return bh, results


class TP(Rep):
    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, cl(f"PSX Live & Research - Trade Plan PDF - page {self.page_no()}/{{nb}}"), align="C")


def _h(pdf, num, title):
    _need(pdf, 22)
    _gap(pdf, 5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 7, cl(f"{num}. {title}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(20, 60, 120)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    _gap(pdf, 2)
    pdf.set_text_color(*DARK)


def _num(v, suffix="%", signed=True):
    if v is None:
        return "-"
    return f"{v:+.1f}{suffix}" if signed else f"{v:.1f}{suffix}"


def build(symbol: str) -> tuple[bytes, str]:
    sym = symbol.upper().strip()
    rep = frep.build_full_report(sym)
    if rep.get("error"):
        raise RuntimeError(rep["error"])
    bh, best = best_strategies(sym)
    plan = money_mod.get_plan()
    prop = (rep.get("trade_plan") or {}).get("proposal") or {}

    pdf = TP("P", "mm", "A4")
    pdf.normalize_text = _clean  # emojis stripped, latin-1 safe for every cell
    pdf.alias_nb_pages("{nb}")
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()

    # ── title block ──
    pdf.set_fill_color(20, 60, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 11, cl(f"{sym} - Trade Plan"), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.cell(0, 6.5, cl(f"{rep.get('company', '')} | sector: {rep.get('sector') or '-'} | "
                         f"generated {datetime.now(PKT).strftime('%d %b %Y %H:%M PKT')} | data as of {rep.get('as_of', '?')}"),
             new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(*DARK)
    _gap(pdf, 3)

    # ── 1. verdict ──
    ex = rep.get("executive") or {}
    thesis = ex.get("thesis", "-")
    if isinstance(thesis, (list, tuple)):
        thesis = "\n".join(str(x) for x in thesis)
    _h(pdf, 1, "Today's verdict")
    _kv(pdf, [("Verdict", f"{ex.get('verdict', '?')} (confidence: {ex.get('confidence', '?')})"),
              ("Trader action", ex.get("action", "-")),
              ("Thesis", thesis)])

    # ── 2. key stats ──
    _h(pdf, 2, "Key stats")
    _kv(pdf, rep.get("key_stats", []))

    # ── 3. market & technicals ──
    _h(pdf, 3, "Price, trend & technicals")
    _kv(pdf, rep.get("price_trend", []) + rep.get("technicals", []))

    # ── 4. best strategy (all 33 backtested) ──
    _h(pdf, 4, f"Best strategy for {sym} (all {len(bt.STRATEGIES)} engine strategies backtested, {START} -> today)")
    _para(pdf, f"Buy & hold over the same window: {_num(bh)}. "
               f"Costs included (0.15% commission + 0.1% slippage per side), 2xATR stops, "
               f"only strategies with >= {MIN_TRADES} trades are ranked.")
    if not best:
        _para(pdf, f"No strategy produced >= {MIN_TRADES} trades on {sym} - not enough signal history to prefer any.")
    else:
        top = best[:3]
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(20, 20, 22)
        pdf.set_text_color(255, 255, 255)
        widths = [62, 14, 22, 15, 20, 15, 32]
        for label, w in zip(["Strategy", "Tr", "Net ret", "Win", "Max DD", "PF", "Open pos"], widths):
            pdf.cell(w, 6.5, label, border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for row in top:
            pdf.set_text_color(*DARK)
            pdf.cell(62, 6, _clean(row["name"])[:40], border=1)
            pdf.cell(14, 6, str(row["trades"]), border=1, align="C")
            pdf.set_text_color(*(GREEN if row["ret"] > 0 else RED))
            star = "*" if row.get("open") is not None else ""
            pdf.cell(22, 6, f"{row['ret']:+.0f}%{star}", border=1, align="C")
            pdf.set_text_color(*DARK)
            pdf.cell(15, 6, f"{row['wr']:.0f}%", border=1, align="C")
            pdf.set_text_color(*RED)
            pdf.cell(20, 6, f"-{row['dd']:.0f}%", border=1, align="C")
            pdf.set_text_color(*DARK)
            pdf.cell(15, 6, f"{row['pf']:.2f}" if row["pf"] is not None else "-", border=1, align="C")
            pdf.cell(32, 6, cl(family_note(row["id"]))[:24], border=1)
            pdf.ln()
        pdf.set_text_color(*GREY)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.multi_cell(0, 4, _clean(f"* return still includes an open position (unrealized "
                                    f"{_num(top[0].get('open'))}) - not counted in win rate. "
                                    f"Preferred strategy: {top[0]['name']} ({family_note(top[0]['id'])})."))
        pdf.set_text_color(*DARK)
        _para(pdf, f"Fit verdict: {verdict(top[0]['ret'], bh)}.")

    # ── 5. trade plan (sized by your Money plan) ──
    _h(pdf, 5, "Trade plan (sized by your saved Money plan)")
    _kv(pdf, [("Money plan", f"capital Rs {plan['capital']:,.0f} | risk {plan['risk_per_trade_pct']}% per swing | "
                             f"target {plan['target_per_trade_pct']}% / stop {plan['stop_per_trade_pct']}% | "
                             f"max hold {plan['max_hold_days']} days | weekly loss limit {plan['weekly_loss_limit_pct']}%")])
    if prop:
        lo, hi = prop.get("entry_range") or [None, None]
        entry_mid = round(((lo or 0) + (hi or 0)) / 2, 2) if lo and hi else None
        stop = prop.get("stop_loss"); t1 = prop.get("target_1"); t2 = prop.get("target_2")
        _kv(pdf, [("Action", prop.get("action", "-")),
                  ("Entry range", f"Rs {lo} - Rs {hi}" if lo and hi else "-"),
                  ("Stop-loss", f"Rs {stop}" if stop else "-"),
                  ("Targets", f"T1 Rs {t1} | T2 Rs {t2}"),
                  ("Reward : risk", f"{prop.get('reward_risk_t1', '-')} (T1) | {prop.get('reward_risk_t2', '-')} (T2)"),
                  ("Timeframe", prop.get("timeframe", "-")),
                  ("Valid until", prop.get("valid_until", "-"))])
        if entry_mid and stop and stop < entry_mid:
            sz = risk_mod.position_size(plan["capital"], plan["risk_per_trade_pct"], entry_mid, stop)
            chk = risk_mod.check_trade(sym, entry_mid, stop, t1 or entry_mid, sz["qty"], plan["capital"])
            _kv(pdf, [("Buy (your risk rule)", f"{sz['qty']} shares for Rs {sz['cost_rs']:,.0f} "
                                               f"({sz['position_pct']}% of capital, capped by {sz['capped_by']})"),
                      ("Rs at risk at stop", f"Rs {sz['risk_rs']:,.0f}"),
                      ("Rule check", "passes" if chk["ok"] else "fails a hard rule - see warnings")])
            if chk["warnings"]:
                _bullets(pdf, chk["warnings"])
    else:
        _para(pdf, "No trade proposal available for this stock right now.")

    # ── 6. bull vs bear ──
    deb = rep.get("debate") or {}

    def _fmt_factor(f):
        if isinstance(f, dict):
            det = str(f.get("detail") or "").strip()
            base = str(f.get("factor") or "")
            return f"{base} - {det}" if det else base
        return str(f)

    _h(pdf, 6, "The debate: bull case vs bear case")
    _kv(pdf, [("Scores", f"bull {deb.get('bull_score', '-')} | bear {deb.get('bear_score', '-')} | "
                         f"net {deb.get('net', '-')} -> {deb.get('verdict', '?')}")])
    _bullets(pdf, [f"BULL: {_fmt_factor(f)}" for f in (deb.get("bull_factors") or [])[:5]])
    _bullets(pdf, [f"BEAR: {_fmt_factor(f)}" for f in (deb.get("bear_factors") or [])[:5]])

    # ── 7. fundamentals ──
    _h(pdf, 7, "Fundamentals")
    _kv(pdf, rep.get("fundamentals", []))

    # ── 8. recent news ──
    news = rep.get("news") or []
    if news:
        _h(pdf, 8, "Recent news & mood")
        _bullets(pdf, [f"[{n.get('sentiment', '?')}] {cl(n.get('title', ''))[:110]} "
                       f"({n.get('source', '')} {n.get('published', '')})" for n in news[:6]])

    # ── disclaimer ──
    _gap(pdf, 4)
    pdf.set_text_color(*GREY)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4, cl(f"Backtests use past data and never guarantee future results. "
                            f"{rep.get('disclaimer', 'For education, not financial advice.')}"))

    return bytes(pdf.output()), f"trade_plan_{sym}.pdf"
