"""Strategy Fit Guide — which strategy is preferred for which stock.

Backtests EVERY strategy in the engine on every watchlist stock
(2021-01-01 -> today, daily bars, commission+slippage, 2xATR stops),
keeps strategies that produced >= MIN_TRADES trades, ranks them by net
return, and renders a landscape-A4 PDF:

  * one-line summary per stock (preferred strategy + key numbers)
  * top-3 detail per stock
  * methodology + disclaimer

Run:  python scripts/make_strategy_fit_pdf.py
Out:  strategy_fit_guide.pdf  (workspace root)
Takes about 1-2 minutes.
"""
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fpdf import FPDF  # noqa: E402

from src.app.report_pdf import cl  # noqa: E402  (latin-1 text cleaner)
from src.backtest import engine as bt  # noqa: E402
from src.data import appconfig as appcfg  # noqa: E402

PKT = timezone(timedelta(hours=5))
START = "2021-01-01"
MIN_TRADES = 5
GREEN = (22, 163, 74)
RED = (220, 38, 38)
GREY = (110, 110, 115)
DARK = (20, 20, 22)

FAMILY = {  # short style note per strategy id prefix / id
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


def verdict(best_ret: float | None, bh: float | None) -> str:
    if best_ret is None:
        return "no strategy passed the trade gate"
    beats = bh is None or best_ret >= bh
    if beats and best_ret > 50:
        return "STRONG fit (beats B&H)"
    if beats:
        return "good fit (beats B&H)"
    if best_ret > 20:
        return "decent, but B&H won"
    return "weak — B&H won here"


def main() -> None:
    wl = appcfg.get_watchlist()
    rows: list[dict] = []
    t0 = time.time()
    for w in wl:
        sym = str(w["symbol"]).upper()
        results = []
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
                    "bh": m["buy_hold_pct"], "open": ot.get("unrealized_pct"),
                })
        results.sort(key=lambda x: x["ret"], reverse=True)
        rows.append({"symbol": sym, "company": w.get("name", sym),
                     "bh": bh, "results": results})
        print(f"  {sym}: {len(results)} strategies passed gate "
              f"(best: {results[0]['id'] if results else '—'})")

    # ── render PDF ──────────────────────────────────────────────────
    def _clean(t):
        s = re.sub(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]", "", str(t))  # drop emojis
        return cl(s)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.normalize_text = _clean   # keep built-in fonts happy (—, ·, no emoji)
    pdf.set_auto_page_break(True, 12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 8, "PSX Live & Research — Strategy Fit Guide", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4.5, (
        "Which strategy is preferred for which stock — every engine strategy backtested on every "
        f"watchlist stock from {START} to today (daily bars, 0.15% commission + 0.1% slippage per "
        f"side, 2xATR stop, entry at next open). Only strategies with >= {MIN_TRADES} trades are "
        "ranked; ranking is by NET total return. Generated "
        + datetime.now(PKT).strftime("%d %b %Y, %H:%M PKT") + "."))
    pdf.ln(3)

    W = 277
    cols = [("Stock", 16), ("Company", 40), ("Preferred strategy", 84), ("Tr", 10),
            ("Net ret", 24), ("Win", 13), ("Max DD", 22), ("Buy&hold", 24), ("Verdict", 44)]

    def head():
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(20, 20, 22)
        pdf.set_text_color(255, 255, 255)
        for label, wdt in cols:
            pdf.cell(wdt, 6.5, label, border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(*DARK)

    def num(v, suffix="%"):
        return "—" if v is None else f"{v:+.0f}{suffix}" if suffix == "%" and v == v else f"{v:.0f}{suffix}"

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 7, "1. One-line summary per stock", ln=True)
    head()
    pdf.set_font("Helvetica", "", 7.6)
    for r in rows:
        best = r["results"][0] if r["results"] else None
        v = verdict(best["ret"] if best else None, r["bh"])
        pdf.set_font("Helvetica", "B", 7.6)
        pdf.cell(16, 6, r["symbol"], border=1)
        pdf.set_font("Helvetica", "", 7.6)
        pdf.cell(40, 6, (r["company"] or "")[:26], border=1)
        pdf.cell(84, 6, (best["name"] if best else "—")[:58], border=1)
        pdf.cell(10, 6, str(best["trades"]) if best else "—", border=1, align="C")
        pdf.set_text_color(*(GREEN if best and best["ret"] > 0 else RED))
        best_txt = num(best["ret"]) + ("*" if best and best.get("open") is not None else "") if best else "—"
        pdf.cell(24, 6, best_txt, border=1, align="C")
        pdf.set_text_color(*DARK)
        pdf.cell(13, 6, f"{best['wr']:.0f}%" if best else "—", border=1, align="C")
        pdf.set_text_color(*RED)
        pdf.cell(22, 6, num(best["dd"]) if best else "—", border=1, align="C")
        pdf.set_text_color(*GREY)
        pdf.cell(24, 6, num(r["bh"]), border=1, align="C")
        pdf.set_text_color(*DARK)
        pdf.cell(44, 6, v, border=1)
        pdf.ln()

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. Top-3 strategies per stock (net return, costs & stops included)", ln=True)
    pdf.ln(1)
    for r in rows:
        if pdf.get_y() > 170:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 6, f"{r['symbol']} — {r['company']}", ln=True)
        pdf.set_font("Helvetica", "", 7.4)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 5, f"buy & hold over the same window: {num(r['bh'])}", ln=True)
        pdf.set_text_color(*DARK)
        if not r["results"]:
            pdf.set_text_color(*GREY)
            pdf.cell(0, 5, f"No strategy produced >= {MIN_TRADES} trades — not enough signal history to prefer any.", ln=True)
            pdf.ln(3)
            continue
        for i, x in enumerate(r["results"][:3]):
            star = "* " if i == 0 else "   "
            pdf.set_font("Helvetica", "B", 7.6)
            pdf.cell(6, 5.2, star)
            pdf.set_font("Helvetica", "", 7.6)
            pdf.cell(86, 5.2, x["name"][:56])
            pdf.cell(12, 5.2, f"{x['trades']} tr", align="C")
            pdf.set_text_color(*(GREEN if x["ret"] > 0 else RED))
            pdf.cell(22, 5.2, num(x["ret"]) + ("*" if x.get("open") is not None else ""), align="C")
            pdf.set_text_color(*DARK)
            pdf.cell(14, 5.2, f"{x['wr']:.0f}% wr", align="C")
            pdf.set_text_color(*RED)
            pdf.cell(22, 5.2, num(x["dd"]), align="C")
            pdf.set_text_color(*GREY)
            pdf.cell(0, 5.2, "  · " + family_note(x["id"]))
            pdf.ln(5.2)
            pdf.set_text_color(*DARK)
        pdf.ln(2.5)

    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*GREY)
    pdf.ln(2)
    pdf.multi_cell(0, 4, (
        "Method: signals close on the bar, fills at next open; costs 0.15% commission + 0.1% "
        "slippage each side; protective stop at 2xATR; strategies with fewer than "
        f"{MIN_TRADES} trades excluded from ranking. (*) = the strategy was still holding an "
        "open position at the end of the window: its unrealized gain/loss is included in net "
        "return but NOT in the win-rate (win-rate counts closed trades only). Past results do "
        "not guarantee future returns. For education only — not financial advice. Generated by "
        "PSX Live & Research (free & open-source)."))
    out = ROOT / "strategy_fit_guide.pdf"
    pdf.output(str(out))
    import json as _json
    side = ROOT / "strategy_fit_data.json"
    side.write_text(_json.dumps(
        [{"symbol": r["symbol"], "company": r["company"], "buy_hold": r["bh"],
          "top3": r["results"][:3]} for r in rows], indent=1))
    print(f"\nPDF written: {out}  ({time.time()-t0:.0f}s)")
    print(f"JSON sidecar: {side}")


if __name__ == "__main__":
    main()
