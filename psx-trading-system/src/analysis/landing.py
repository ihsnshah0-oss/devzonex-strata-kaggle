"""Landing-page data engine — assembles the Stalwart-style welcome screen
from the same free, cached data sources used everywhere else.

Output drives: the AI pulse ring state, the natural-language headline,
the bento metric cards (+ sparklines & drivers), the composite trend chart,
the AI alerts feed and the institutional sector heatmap.
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..data import psx_client as psx
from ..data import psx_official as pso
from ..data import investify as invmod
from ..data import appconfig as appcfg

PKT = timezone(timedelta(hours=5), name="PKT")
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"

# Each entry: (quote, author, the learning it carries).
# One is picked fresh on every page load so each visit brings a new lesson.
QUOTES = [
    ("The stock market is a device for transferring money from the impatient to the patient.",
     "Warren Buffett", "Patience is a position — holding a good trade is itself an edge."),
    ("Plan your trade. Trade your plan.",
     "Trading discipline maxim", "Decide entry, stop and target BEFORE you click buy — not after."),
    ("Risk comes from not knowing what you are doing.",
     "Warren Buffett", "Do your homework on the business first; the chart only times the entry."),
    ("The goal of a successful trader is to make the best trades. Money is secondary.",
     "Alexander Elder", "Quality of process beats size of profit — good process repeats, luck doesn't."),
    ("Cut your losses short and let your winners run.",
     "Jesse Livermore", "Your win rate matters less than your win size. Protect the downside."),
    ("The trend is your friend until the end when it bends.",
     "Ed Seykota", "Trade with the trend, but keep an exit plan for when it rolls over."),
    ("It is not the strongest who survive, but those who manage risk.",
     "PSX Live & Research discipline note", "Position sizing keeps you in the game long enough to be right."),
    ("Watch the breadth, respect the stop, and the account takes care of itself.",
     "Swing trader's rule", "Market breadth tells you when to be aggressive and when to sit out."),
    ("Markets reward consistency, not heroics.",
     "PSX Live & Research discipline note", "Small repeatable wins compound; one giant bet can erase them all."),
    ("Never lose more on one idea than your plan allows.",
     "Position-sizing rule", "Risk 1–2% of capital per trade so a string of losses never hurts."),
    ("Price is what you pay; value is what you get.",
     "Warren Buffett", "Compare P/E, payout and growth before paying up for any stock."),
    ("Amateurs think about how much they can make. Professionals think about how much they can lose.",
     "Jack Schwager", "Define your risk in rupees before you define your target."),
    ("The four most expensive words in investing are: 'This time it's different.'",
     "Sir John Templeton", "History repeats on PSX — bubbles and panics both end."),
    ("In the short run the market is a voting machine, in the long run a weighing machine.",
     "Benjamin Graham", "Ignore daily noise; earnings and dividends decide the long-term price."),
    ("Opportunities come infrequently. When it rains gold, put out the bucket, not the thimble.",
     "Warren Buffett", "When a genuinely strong setup appears, size it properly."),
    ("Be fearful when others are greedy, and greedy when others are fearful.",
     "Warren Buffett", "Extreme sentiment is a contrarian signal — check the Fear & Greed mood."),
    ("Know what you own, and know why you own it.",
     "Peter Lynch", "Every position in your book should have a one-line thesis you can say aloud."),
    ("How many millionaires do you know who became rich by investing in savings accounts?",
     "Robert Fulghum", "Inflation eats idle cash — invested capital at work is how wealth grows."),
    ("The biggest risk of all is not taking one.",
     "Mellody Hobson", "Staying in cash forever is also a decision — and it loses to inflation."),
    ("Your economics is not always going to agree with the stock market.",
     "Jim Rogers", "Stocks lead the economy by months — watch earnings turns, not just headlines."),
    ("Dividends are the return you are paid while you wait.",
     "PSX Live & Research income note", "On PSX, high-yield names (fertilizer, banks) pay you to be patient."),
    ("Never average down without a thesis; never average up without momentum.",
     "PSX Live & Research discipline note", "Adding to a loser needs a reason, not just a lower price."),
    ("The elements of good trading are: cut losses, cut losses, cut losses.",
     "William O'Neil", "One rule repeated three times tells you its true importance."),
    ("Volatility is the price you pay for returns.",
     "Howard Marks", "A 2–3% daily swing is normal on PSX — plan around it, don't panic at it."),
    ("Time in the market beats timing the market.",
     "Investing adage", "Missing the ten best days halves your long-run returns."),
    ("A falling knife can still cut you.",
     "Trader's proverb", "Wait for the first higher low before buying a crashing stock."),
    ("Buy when there is blood in the streets.",
     "Baron Rothschild", "The best entries feel uncomfortable — that is why they pay."),
    ("Hope is not a trading strategy.",
     "Market maxim", "If your only plan is 'it will come back', you have no plan."),
    ("The first loss is the best loss.",
     "Paul Tudor Jones", "Take the small stop early instead of negotiating with a bigger one later."),
    ("It's not whether you're right or wrong, but how much you make when you're right and how little you lose when you're wrong.",
     "George Soros", "Asymmetry — big wins, small losses — is the whole game."),
    ("Earnings, earnings, earnings.",
     "Philip Fisher", "In the long run, share prices follow profit growth. Read the results."),
    ("Never ask the barber if you need a haircut.",
     "Warren Buffett", "Beware advice from people who profit when you trade."),
    ("The market can stay irrational longer than you can stay solvent.",
     "John Maynard Keynes", "Right thesis + wrong timing = loss. Size for the wait."),
    ("Sellers make the market liquid, buyers make it rise.",
     "PSX Live & Research tape note", "Watch volume: a rise on heavy volume is the crowd confirming the move."),
    ("If you don't respect the stop-loss, the market will respect your account balance instead.",
     "Risk desk rule", "A stop-loss is a pre-paid insurance policy. Pay it."),
    ("Every candlestick tells you who won the battle between buyers and sellers.",
     "Chart craft", "Read price action: big closes mean conviction, wicks mean rejection."),
    ("The wise man builds his house on the rock.",
     "Proverb", "Balance sheets with low debt and real cash flow survive every cycle."),
    ("Cash is oxygen — you only notice it when it's gone.",
     "Trader's proverb", "Keep a reserve; full-invested accounts are forced sellers at the worst time."),
    ("Fortunes are made in bull markets and kept in risk management.",
     "PSX Live & Research discipline note", "Anyone can make money in a rally; keeping it is the skill."),
    ("You don't need to trade every day. The market pays you for waiting for YOUR setup.",
     "Swing trader's rule", "No position is also a position. Pass on setups that aren't yours."),
    ("A market bottom always looks worse than it feels, and a top always feels better than it is.",
     "Contrarian's note", "Discomfort at the lows and euphoria at the highs are your signals."),
    ("Read the filings. The truth is in the footnotes.",
     "Value investor's rule", "PSX company reports (financials.psx.com.pk) hold the real story."),
    ("Diversification is protection against ignorance.",
     "Warren Buffett", "Own a few names you truly understand rather than many you don't."),
    ("Rule No. 1: never lose money. Rule No. 2: never forget Rule No. 1.",
     "Warren Buffett", "Capital preservation is the first job — compounding needs survivors."),
]


def _now_pkt() -> datetime:
    return datetime.now(PKT)


def _composite(days: int = 60, ttl_min: int = 30) -> dict:
    """Equal-weight composite of the user's watchlist, normalized to 100.
    Built from already-cached EOD files — no network calls."""
    p = CACHE / "landing_composite.json"
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl_min * 60:
            return json.loads(p.read_text())
    except Exception:
        pass
    wl = [str(w.get("symbol", "")).upper() for w in (appcfg.get_watchlist() or [])]
    series: list[float] = []
    dates: list[str] = []
    mats: list[pd.Series] = []
    for sym in wl:
        try:
            h = psx.get_history(sym)
            c = h["close"].astype(float).tail(days)
            if len(c) < 20:
                continue
            mats.append((c / float(c.iloc[0]) * 100).reset_index(drop=True))
            dates = [str(d)[:10] for d in h["date"].tail(len(c))]
        except Exception:
            continue
    if not mats:
        return {"series": [], "dates": [], "members": 0}
    df = pd.concat(mats, axis=1)
    avg = df.mean(axis=1).round(2)
    out = {"series": [None if pd.isna(v) else float(v) for v in avg],
           "dates": dates[-len(avg):], "members": len(mats)}
    try:
        p.write_text(json.dumps(out))
    except Exception:
        pass
    return out


def _spark(vals: list, n: int = 24) -> list:
    vals = [v for v in vals if v is not None]
    if not vals:
        return []
    if len(vals) <= n:
        return [round(float(v), 2) for v in vals]
    step = len(vals) / n
    return [round(float(vals[int(i * step)]), 2) for i in range(n)]


def _conf_from_chg(chg) -> dict:
    """Heuristic 'AI directional confidence' from the day's move + snapshot."""
    try:
        c = float(chg)
    except Exception:
        c = 0.0
    score = max(5, min(95, 50 + c * 14))
    direction = "Long bias" if c > 0.15 else ("Short bias" if c < -0.15 else "Neutral")
    return {"score": int(score), "direction": direction, "chg": round(c, 2)}


def build() -> dict:
    now = _now_pkt()
    hour = now.hour
    greeting = ("Good morning" if hour < 12 else
                "Good afternoon" if hour < 17 else "Good evening")
    quote_text, quote_author, quote_lesson = random.choice(QUOTES)

    # ── official market internals ──────────────────────────────────────
    ov = {}
    try:
        ov = pso.get_market_overview()
    except Exception:
        pass
    breadth = (ov or {}).get("breadth") or {}
    kse = next((i for i in (ov or {}).get("indices", []) if i["name"] == "KSE-100"), None)
    kse_pct = float(kse["pct"]) if kse else None
    adv, dec = breadth.get("advanced"), breadth.get("declined")

    # ── pulse state: stable (emerald) vs high-volatility (amber) ──────
    dec_ratio = (dec / (adv + dec)) if (adv is not None and dec is not None and (adv + dec)) else None
    volatile = bool((kse_pct is not None and abs(kse_pct) >= 1.2) or
                    (dec_ratio is not None and dec_ratio >= 0.75))
    if volatile:
        pulse = {"state": "volatile",
                 "label": "High volatility — hedging stance",
                 "detail": (f"KSE-100 moved {kse_pct:+.2f}% with broad declines; "
                            "system flags defensive positioning today.")}
    else:
        pulse = {"state": "stable",
                 "label": "Market stable — long bias",
                 "detail": (f"KSE-100 at {kse_pct:+.2f}% on the day with orderly breadth; "
                            "conditions support normal swing activity.") if kse_pct is not None
                 else "Conditions look orderly; normal swing activity supported."}
    if dec_ratio is not None:
        pulse["confidence"] = int(round(100 - dec_ratio * 55 - (abs(kse_pct or 0) * 8)))
    else:
        pulse["confidence"] = 62

    # ── open REAL broker positions ────────────────────────────────────
    positions_n = 0
    real_win = 0
    try:
        from ..broker import ledger as _bk
        _pr: dict = {}
        try:
            _s = psx.get_market_snapshot()
            for _, r in _s.iterrows():
                try:
                    _pr[str(r["symbol"]).upper()] = float(r["price"])
                except Exception:
                    pass
        except Exception:
            _pr = {}
        _b = _bk.brief(_pr)
        positions_n = _b["open_n"]
        real_win = _b["open_win"]
    except Exception:
        pass

    # ── snapshot-based numbers ────────────────────────────────────────
    try:
        snap = psx.get_market_snapshot().copy()
        snap["change_pct"] = pd.to_numeric(snap["change_pct"], errors="coerce")
        snap["market_cap"] = pd.to_numeric(snap.get("market_cap"), errors="coerce")
    except Exception:
        snap = pd.DataFrame()

    wl_syms = {str(w.get("symbol", "")).upper() for w in (appcfg.get_watchlist() or [])}
    wl_rows, top_g, top_l, top_a = [], [], [], []
    turnover = (ov or {}).get("value")
    if len(snap):
        tradable = snap[snap["price"].astype(float) > 0]
        top_g = tradable.sort_values("change_pct", ascending=False).head(4)
        top_l = tradable.sort_values("change_pct").head(4)
        top_a = tradable.sort_values("volume_avg_30d", ascending=False).head(4)
        if wl_syms:
            wl_rows_df = snap[snap["symbol"].astype(str).str.upper().isin(wl_syms)]
            if len(wl_rows_df):
                wl_rows = wl_rows_df.sort_values("change_pct", ascending=False)
    wl_avg = float(wl_rows["change_pct"].mean()) if len(wl_rows) else None

    def drivers(df, n=4):
        out = []
        for r in df.head(n).to_dict(orient="records"):
            try:
                out.append({"symbol": str(r["symbol"]),
                            "chg": round(float(r["change_pct"]), 2),
                            "price": round(float(r["price"]), 2)})
            except Exception:
                continue
        return out

    comp = _composite()
    metrics = [
        {"id": "ksc", "label": "KSE-100", "tone": "up" if (kse_pct or 0) >= 0 else "down",
         "value": f"{(kse or {}).get('change', 0):+,.0f}" if kse else "—",
         "sub": (f"{kse['value']:,.0f} · {kse_pct:+.2f}% today" if kse else "index offline"),
         "spark": _spark(comp["series"]), "drivers": drivers(top_g),
         "driver_label": "Leaders driving the tape"},
        {"id": "turnover", "label": "Value traded", "tone": "flat",
         "value": f"Rs {turnover / 1e9:.2f} bn" if turnover else "—",
         "sub": (f"{int(ov.get('volume', 0)):,} shares · {int(ov.get('trades', 0)):,} trades"
                 if ov.get("volume") else "turnover offline"),
         "spark": [], "drivers": drivers(top_a),
         "driver_label": "Most active by volume"},
        {"id": "breadth", "label": "Breadth", "tone": "up" if (adv or 0) >= (dec or 0) else "down",
         "value": f"▲{adv} · ▼{dec}" if adv is not None else "—",
         "sub": (f"{breadth.get('unchanged', 0)} unchanged of {breadth.get('total', '—')} issues"
                 if adv is not None else "breadth offline"),
         "spark": [], "drivers": drivers(top_l),
         "driver_label": "Laggards to avoid"},
        {"id": "wl", "label": "Watchlist avg", "tone": "up" if (wl_avg or 0) >= 0 else "down",
         "value": f"{wl_avg:+.2f}%" if wl_avg is not None else "—",
         "sub": f"across {len(wl_rows)} tracked names" if len(wl_rows) else "watchlist offline",
         "spark": _spark(comp["series"]),
         "drivers": ([{"symbol": str(r["symbol"]), "chg": round(float(r["change_pct"]), 2),
                       "price": round(float(r["price"]), 2)}
                      for r in wl_rows.head(4).to_dict(orient="records")] if len(wl_rows) else []),
         "driver_label": "Watchlist movers"},
    ]

    # ── AI alerts feed (official filings & announcements) ─────────────
    alerts = []
    try:
        for a in invmod.fetch_announcements()[:8]:
            alerts.append({"time": a.get("when", ""), "symbol": a.get("symbol", ""),
                           "title": (a.get("title") or "")[:110],
                           "kind": a.get("category") or "Filing",
                           "link": a.get("link", "")})
    except Exception:
        pass

    # ── sector heatmap: ALL sectors, every ALLSHR + watchlist stock ───
    heatmap: list[dict] = []
    if len(snap):
        try:
            universe = set(psx.get_allshr()) | {psx._norm(s) for s in wl_syms}
            snames: dict[str, str] = {}
            try:
                for r in psx.get_sectors().itertuples():
                    snames[str(int(float(r.sector_code)))] = str(r.sector_name).title()
            except Exception:
                pass
            s2 = snap[snap["symbol"].astype(str).str.upper().map(
                lambda x: psx._norm(x) in universe)].copy()
            s2["sec"] = s2["sector"].map(
                lambda c: snames.get(str(int(float(c))), "Other") if pd.notna(c) else "Other")
            # every sector, largest first; every stock inside, largest first
            all_sectors = (s2.groupby("sec")["market_cap"].sum()
                           .sort_values(ascending=False).index.tolist())
            for sec in all_sectors:
                rows = s2[s2["sec"] == sec].sort_values("market_cap", ascending=False)
                tiles = []
                for r in rows.to_dict(orient="records"):
                    c = _conf_from_chg(r.get("change_pct"))
                    tiles.append({"symbol": str(r["symbol"]),
                                  "wl": psx._norm(str(r["symbol"])) in
                                  {psx._norm(s) for s in wl_syms}, **c})
                chg = float(rows["change_pct"].mean()) if len(rows) else 0.0
                heatmap.append({"name": sec, "change": round(chg, 2), "tiles": tiles})
        except Exception:
            heatmap = []

    # ── headline ──────────────────────────────────────────────────────
    sent = ("firmly bullish" if (adv or 0) > (dec or 0) * 1.4 else
            "constructive" if (adv or 0) > (dec or 0) else
            "cautious" if (adv or 0) > (dec or 0) * 0.55 else "defensive")
    if positions_n:
        headline = (f"{greeting}. Your real broker account holds {positions_n} open position"
                    f"{'s' if positions_n != 1 else ''} ({real_win} in profit) and the system "
                    f"tracks {len(wl_syms)} watchlist names. Market sentiment is {sent}; "
                    f"{'volatility is elevated — tighten stops' if volatile else 'no manual actions are required today'}.")
    else:
        headline = (f"{greeting}. No open real-account positions; the system is scanning "
                    f"{len(wl_syms)} watchlist names. Market sentiment is {sent}; "
                    f"{'volatility is elevated — wait for calmer tape' if volatile else 'no manual actions are required today'}.")

    return {"generated_at": now.isoformat(timespec="seconds"),
            "market_status": (ov or {}).get("status"),
            "pulse": pulse, "headline": headline,
            "quote": {"text": quote_text, "author": quote_author,
                      "lesson": quote_lesson},
            "positions": positions_n,
            "metrics": metrics,
            "trend": {"label": f"PSX Live & Research Composite · equal-weight of {comp['members']} watchlist names (normalized to 100)",
                      "dates": comp["dates"], "series": comp["series"]},
            "alerts": alerts, "heatmap": heatmap}
