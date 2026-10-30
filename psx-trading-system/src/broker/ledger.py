"""Live ledger for the REAL broker account (W615).

The account starts from the imported statement W615 trades and then grows:
new trades can be added and open positions closed from the dashboard.
Everything is persisted in data/broker_account.json.

This is the user's actual trading book — kept strictly separate from the
practice (paper) ledger in data/psx.db.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..paper import statement as stmt

PKT = timezone(timedelta(hours=5), name="PKT")
STORE = Path(__file__).resolve().parents[2] / "data" / "broker_account.json"


def _seed_trades() -> list[dict]:
    """The W615 statement trades as the opening book."""
    return [{"symbol": s, "side": sd, "qty": q, "rate": r,
             "amount": a, "date": d, "source": "statement-W615"}
            for s, sd, q, r, a, d in stmt.TRADES]


def load_trades() -> list[dict]:
    if not STORE.exists():
        trades = _seed_trades()
        _save(trades)
        return trades
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return _seed_trades()


def _save(trades: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(trades, indent=1))


def add_trade(symbol: str, side: str, qty: float, rate: float,
              date: str | None = None, amount: float | None = None,
              source: str = "manual") -> dict:
    symbol = str(symbol).upper().strip()
    side = str(side).lower().strip()
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    qty, rate = float(qty), float(rate)
    if qty <= 0 or rate <= 0:
        raise ValueError("qty and rate must be positive")
    if side == "sell":
        pos = {p["symbol"]: p["qty"] for p in build({})["positions"]}
        have = pos.get(symbol, 0)
        if qty > have:
            raise ValueError(f"cannot sell {qty:,.0f} {symbol} — you hold {have:,.0f}")
    trades = load_trades()
    t = {"symbol": symbol, "side": side, "qty": qty, "rate": rate,
         "amount": round(float(amount) if amount else qty * rate, 2),
         "date": date or datetime.now(PKT).strftime("%Y-%m-%d"),
         "source": source}
    trades.append(t)
    _save(trades)
    return t


def close_position(symbol: str, qty: float | None = None,
                   rate: float | None = None, prices: dict | None = None) -> dict:
    """Sell part or all of an open position. Price defaults to live market."""
    symbol = str(symbol).upper().strip()
    pos = next((p for p in build({})["positions"] if p["symbol"] == symbol), None)
    if not pos:
        raise ValueError(f"no open position in {symbol}")
    qty = float(qty or pos["qty"])
    if qty <= 0 or qty > pos["qty"]:
        raise ValueError(f"qty must be between 1 and {pos['qty']:,.0f}")
    if not rate:
        rate = (prices or {}).get(symbol) or pos.get("last")
        if not rate:
            raise ValueError("no live price available — enter a rate manually")
    return add_trade(symbol, "sell", qty, float(rate), source="close")


def reset() -> dict:
    """Restore the book to the original W615 statement trades."""
    _save(_seed_trades())
    return {"ok": True, "trades": len(stmt.TRADES)}


def import_book(rows: list[dict], date: str | None = None) -> dict:
    """Replace the whole book with positions read from an uploaded broker
    statement (each row becomes one opening BUY at its average cost)."""
    d = date or datetime.now(PKT).strftime("%Y-%m-%d")
    trades = []
    for r in rows:
        qty, rate = float(r["qty"]), float(r["rate"])
        if qty <= 0 or rate <= 0:
            continue
        trades.append({"symbol": str(r["symbol"]).upper().strip(),
                       "side": "buy", "qty": qty, "rate": rate,
                       "amount": round(qty * rate, 2), "date": d,
                       "source": "statement-upload"})
    if not trades:
        raise ValueError("no valid rows to import")
    _save(trades)
    return {"ok": True, "positions": len(trades), "date": d}


def brief(prices: dict | None = None) -> dict:
    """Compact win/loss picture of the live book for the dashboard hero."""
    d = build(prices)
    pos = d["positions"]
    real = d["realized"]
    open_win = sum(1 for p in pos if (p["unrealized"] or 0) >= 0)
    open_loss = len(pos) - open_win
    closed_win = sum(1 for r in real if r["pnl"] >= 0)
    closed_loss = len(real) - closed_win
    last = d["trades"][-1] if d["trades"] else None
    top = pos[:3]
    return {"open_n": len(pos), "open_win": open_win, "open_loss": open_loss,
            "closed_n": len(real), "closed_win": closed_win,
            "closed_loss": closed_loss,
            "success_rate": round(closed_win / len(real) * 100) if real else None,
            "totals": d["totals"], "top": top, "last_trade": last,
            "book_trades": len(d["trades"]), "meta": d["meta"],
            "open_rows": [{"symbol": p["symbol"], "pct": p["unrealized_pct"],
                           "rs": p["unrealized"]} for p in pos],
            "closed_rows": [{"symbol": r["symbol"], "rs": r["pnl"],
                             "date": r["date"]} for r in real]}


def build(prices: dict | None = None) -> dict:
    """Positions, realized P&L and totals — same FIFO math as the
    statement, but running on the live, editable ledger."""
    prices = prices or {}
    trades = load_trades()
    lots: dict[str, list[list]] = {}
    realized: list[dict] = []
    bought = sold = 0.0

    for t in trades:
        sym, side, qty = t["symbol"], t["side"], float(t["qty"])
        amt, dt = float(t["amount"]), t.get("date", "")
        if side == "buy":
            bought += amt
            lots.setdefault(sym, []).append([qty, amt])
        else:
            sold += amt
            need, cost = qty, 0.0
            while need > 0 and lots.get(sym):
                q, a = lots[sym][0]
                take = min(need, q)
                cost += a * take / q
                need -= take
                if take >= q:
                    lots[sym].pop(0)
                else:
                    lots[sym][0] = [q - take, a - a * take / q]
            realized.append({"symbol": sym, "qty": qty, "date": dt,
                             "rate": float(t["rate"]), "proceeds": round(amt, 2),
                             "cost": round(cost, 2),
                             "pnl": round(amt - cost, 2)})

    positions = []
    for sym, ls in lots.items():
        qty = sum(l[0] for l in ls)
        if qty <= 0:
            continue
        cost = sum(l[1] for l in ls)
        avg = cost / qty
        last = prices.get(sym)
        mv = round(float(last) * qty, 2) if last else None
        positions.append({"symbol": sym, "qty": qty,
                          "avg_cost": round(avg, 2), "invested": round(cost, 2),
                          "last": (round(float(last), 2) if last else None),
                          "market_value": mv,
                          "unrealized": (round(mv - cost, 2) if mv else None),
                          "unrealized_pct": (round((mv / cost - 1) * 100, 2)
                                             if mv else None)})
    positions.sort(key=lambda p: -(p["invested"]))
    realized.sort(key=lambda r: r["date"])

    tot_real = round(sum(r["pnl"] for r in realized), 2)
    invested = round(bought - sold + tot_real, 2)
    mv_total = (round(sum(p["market_value"] for p in positions if p["market_value"]), 2)
                if all(p["market_value"] for p in positions) else None)
    return {"meta": {**stmt.META, "book": "live", "store": str(STORE.name)},
            "positions": positions,
            "realized": realized,
            "trades": sorted(trades, key=lambda t: t.get("date", "")),
            "totals": {"bought": round(bought, 2), "sold": round(sold, 2),
                       "net_deployed": round(bought - sold, 2),
                       "realized_pnl": tot_real,
                       "still_invested": invested,
                       "market_value": mv_total,
                       "unrealized_pnl": (round(mv_total - invested, 2)
                                          if mv_total else None)}}
