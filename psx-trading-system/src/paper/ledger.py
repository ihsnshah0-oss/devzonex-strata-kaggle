"""Paper-trading ledger (SQLite) — Decision & Execution layer.

No retail broker in Pakistan offers a public order API, so live
auto-execution is impossible; this ledger simulates fills at real market
prices so every proposal can be tracked honestly.
"""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "psx.db"
DB.parent.mkdir(parents=True, exist_ok=True)


def _con():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, symbol TEXT,
        side TEXT, qty INTEGER, price REAL, note TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS account(
        id INTEGER PRIMARY KEY CHECK(id=1), cash REAL)""")
    return c


def _default_cash() -> float:
    try:
        from ..data import appconfig as appcfg
        return float(appcfg.get_settings().get("paper_cash", 1000000))
    except Exception:
        return 1000000.0


def _cash(c) -> float:
    row = c.execute("SELECT cash FROM account WHERE id=1").fetchone()
    return float(row[0]) if row else _default_cash()


def get_cash() -> float:
    c = _con()
    try:
        return _cash(c)
    finally:
        c.close()


def set_cash(amount: float) -> float:
    c = _con()
    try:
        c.execute("INSERT INTO account(id,cash) VALUES(1,?) "
                  "ON CONFLICT(id) DO UPDATE SET cash=?", (amount, amount))
        c.commit()
        return amount
    finally:
        c.close()


def place_order(symbol: str, side: str, qty: int, price: float | None = None,
                note: str = "") -> dict:
    symbol, side = symbol.upper().strip(), side.lower().strip()
    if side not in ("buy", "sell") or qty <= 0:
        return {"error": "side must be buy/sell and qty positive"}
    if price is None:
        try:
            from ..data import psx_client as psx
            q = psx.get_quote(symbol)
            price = float(q.get("price") or q.get("close") or 0)
        except Exception as e:
            return {"error": f"no price available: {e}"}
    if not price:
        return {"error": "no price available"}
    c = _con()
    try:
        cash = _cash(c)
        if side == "buy":
            cost = qty * price
            if cost > cash:
                return {"error": f"insufficient paper cash (need Rs{cost:,.0f}, have Rs{cash:,.0f})"}
            cash -= cost
        else:
            pos = positions(live_prices={}).get("positions", [])
            held = next((p["qty"] for p in pos if p["symbol"] == symbol), 0)
            if qty > held:
                return {"error": f"insufficient holdings (have {held}, tried {qty})"}
            cash += qty * price
        c.execute("INSERT INTO orders(ts,symbol,side,qty,price,note) VALUES(?,?,?,?,?,?)",
                  (int(time.time()), symbol, side, qty, price, note))
        c.execute("INSERT INTO account(id,cash) VALUES(1,?) "
                  "ON CONFLICT(id) DO UPDATE SET cash=?", (cash, cash))
        c.commit()
        return {"ok": True, "symbol": symbol, "side": side, "qty": qty,
                "price": price, "cash": round(cash, 2)}
    finally:
        c.close()


def _fills():
    c = _con()
    try:
        return c.execute("SELECT symbol,side,qty,price,ts,note FROM orders ORDER BY id").fetchall()
    finally:
        c.close()


def positions(live_prices: dict | None = None) -> dict:
    fills = _fills()
    lots: dict[str, list] = {}
    realized = 0.0
    for sym, side, qty, px, ts, note in fills:
        lots.setdefault(sym, [])
        if side == "buy":
            lots[sym].append([qty, px])
        else:
            need = qty
            while need > 0 and lots[sym]:
                q, p = lots[sym][0]
                take = min(q, need)
                realized += take * (px - p)
                q -= take
                need -= take
                if q == 0:
                    lots[sym].pop(0)
                else:
                    lots[sym][0][0] = q
    if live_prices is None:
        live_prices = {}
        try:
            from ..data import psx_client as psx
            for sym in lots:
                try:
                    q = psx.get_quote(sym)
                    live_prices[sym] = float(q.get("price") or q.get("close") or 0)
                except Exception:
                    live_prices[sym] = 0.0
        except Exception:
            pass
    out, mv = [], 0.0
    for sym, ls in lots.items():
        q = sum(x[0] for x in ls)
        if q <= 0:
            continue
        avg = sum(x[0] * x[1] for x in ls) / q
        last = live_prices.get(sym, 0) or avg
        pnl = (last - avg) * q
        mv += last * q
        out.append({"symbol": sym, "qty": q, "avg_price": round(avg, 2),
                    "last": round(last, 2), "market_value": round(last * q, 2),
                    "unrealized_rs": round(pnl, 2),
                    "unrealized_pct": round(pnl / (avg * q) * 100, 2)})
    cash = get_cash()
    equity = cash + mv
    return {"positions": out, "cash": round(cash, 2),
            "market_value": round(mv, 2), "equity": round(equity, 2),
            "realized_pnl": round(realized, 2)}


def history(limit: int = 100) -> list[dict]:
    return [{"symbol": s, "side": sd, "qty": q, "price": p, "ts": t, "note": n}
            for s, sd, q, p, t, n in _fills()][-limit:][::-1]


def reset(cash: float | None = None) -> dict:
    cash = cash if (cash and cash > 0) else _default_cash()
    c = _con()
    try:
        c.execute("DELETE FROM orders")
        c.execute("INSERT INTO account(id,cash) VALUES(1,?) "
                  "ON CONFLICT(id) DO UPDATE SET cash=?", (cash, cash))
        c.commit()
        return {"ok": True, "cash": cash}
    finally:
        c.close()
