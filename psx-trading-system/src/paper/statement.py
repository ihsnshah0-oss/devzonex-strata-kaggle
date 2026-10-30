"""Real broker transaction statement — imported into the Paper Trade tab.

Source: TransactionStatement-021026041055686-W615.pdf (Munir Khanani,
TREC 084), account W615, client ZAIN AHMED, period 01-Aug-2026 to
31-Oct-2026. Every figure below was cross-checked against the statement's
own per-symbol averages and its Client Total (Rs 123,456.40).

Amounts INCLUDE commission + tax, exactly as printed. This is a display
book only — it never touches the simulated paper-trading ledger.
"""
from __future__ import annotations

META = {
    "broker": "Munir Khanani (TREC 084, BRK-084)",
    "account": "W615",
    "client": "ZAIN AHMED",
    "period": "01-Aug-2026 to 31-Oct-2026",
    "statement": "TransactionStatement-021026041055686-W615",
    "cdc_id": "162670",
}

# symbol, side, qty, trade rate, gross amount incl. commission (signed +buy/−sell), date
TRADES = [
    ("PSO",   "buy",  100, 353.16, 35384.75, "2026-08-05"),
    ("EFERT", "buy",  100, 190.80, 19119.45, "2026-08-07"),
    ("PPL",   "buy",   50, 221.49, 11099.49, "2026-08-07"),
    ("PSO",   "sell", 100, 377.50, 37676.84, "2026-08-18"),
    ("SYS",   "buy",  100, 128.00, 12828.11, "2026-08-19"),
    ("PPL",   "sell",  50, 244.00, 12172.97, "2026-08-24"),
    ("PSO",   "buy",  100, 361.00, 36170.17, "2026-09-02"),
    ("NBP",   "buy",  100, 185.10, 18548.42, "2026-09-04"),
    ("AKBL",  "buy",  100, 108.75, 10899.63, "2026-09-08"),
    ("OGDC",  "buy",  100, 320.00, 32062.77, "2026-09-10"),
    ("PSO",   "sell", 100, 344.50, 34382.80, "2026-09-11"),
    ("NBP",   "sell",  50, 172.00,  8579.47, "2026-09-16"),
    ("SYS",   "buy",  100, 119.36, 11962.54, "2026-09-28"),
    ("NBP",   "buy",   50, 165.20,  8277.41, "2026-09-30"),
    ("NBP",   "buy",   50, 165.90,  8312.48, "2026-09-30"),
    ("AKBL",  "buy",  100, 102.00, 10223.42, "2026-10-02"),
    ("PRL",   "buy",   15,  91.49,  1379.83, "2026-10-02"),
]


def build(prices: dict | None = None) -> dict:
    """Assemble positions (with live P&L when `prices` given), realized
    trades and totals. FIFO per symbol, amounts incl. commission."""
    prices = prices or {}
    lots: dict[str, list[list]] = {}
    realized: list[dict] = []
    bought = sold = 0.0

    for sym, side, qty, rate, amt, dt in TRADES:
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
                             "rate": rate, "proceeds": round(amt, 2),
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
    invested = round(bought - sold + tot_real, 2)  # net cash currently at work
    mv_total = round(sum(p["market_value"] for p in positions if p["market_value"]), 2) \
        if all(p["market_value"] for p in positions) else None
    return {"meta": META,
            "positions": positions,
            "realized": realized,
            "trades": [{"symbol": s, "side": sd, "qty": q, "rate": r,
                        "amount": a, "date": d} for s, sd, q, r, a, d in
                       sorted(TRADES, key=lambda t: t[5])],
            "totals": {"bought": round(bought, 2), "sold": round(sold, 2),
                       "net_deployed": round(bought - sold, 2),
                       "realized_pnl": tot_real,
                       "still_invested": invested,
                       "market_value": mv_total,
                       "unrealized_pnl": (round(mv_total - invested, 2)
                                          if mv_total else None),
                       "statement_total": 123456.40}}
