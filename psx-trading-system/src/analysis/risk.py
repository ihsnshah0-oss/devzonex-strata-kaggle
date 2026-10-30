"""Risk Management — position sizing, circuit-breaker guard, portfolio heat.

PSX has no retail shorting infrastructure for most accounts, so the
framework is long-first with strict stops.
"""
from ..data import appconfig as appcfg


def _settings() -> dict:
    return appcfg.get_settings()


def position_size(capital: float, risk_pct: float, entry: float, stop: float,
                  max_position_pct: float = 20.0) -> dict:
    risk_rs = capital * risk_pct / 100
    per_share = max(entry - stop, 0.01)
    qty_risk = int(risk_rs // per_share)
    qty_cap = int((capital * max_position_pct / 100) // max(entry, 0.01))
    qty = max(min(qty_risk, qty_cap), 0)
    return {"qty": qty, "risk_rs": round(qty * per_share, 2),
            "cost_rs": round(qty * entry, 2),
            "position_pct": round(qty * entry / capital * 100, 2) if capital else 0,
            "capped_by": "max-position" if qty_cap < qty_risk else "risk-budget"}


def check_trade(symbol: str, entry: float, stop: float, target: float,
                qty: int, capital: float, ldcp: float | None = None) -> dict:
    s = _settings()
    cb = float(s.get("circuit_breaker_pct", 7.5))
    warnings: list[str] = []
    risk = max(entry - stop, 0)
    reward = max(target - entry, 0)
    rr = round(reward / risk, 2) if risk > 0 else 0
    if rr < 1.0:
        warnings.append(f"R:R {rr}:1 below 1.0 — negative expectancy setup, skip or resize.")
    elif rr < 1.5:
        warnings.append(f"R:R {rr}:1 is thin — consider waiting for a better entry.")
    cost = qty * entry
    if capital and cost / capital > 0.25:
        warnings.append(f"Position is {cost / capital * 100:.1f}% of capital — concentration risk.")
    if capital and risk * qty / capital > 0.03:
        warnings.append("Single-trade risk above 3% of capital — reduce size.")
    if stop >= entry:
        warnings.append("Stop must be below entry for a long trade.")
    if ldcp:
        band = ldcp * cb / 100
        if abs(entry - ldcp) > band:
            warnings.append(f"Entry outside today's ±{cb}% circuit band ({ldcp} ± {band:.2f}).")
    ok = not any("below 1.0" in w or "must be below" in w for w in warnings)
    return {"symbol": symbol, "ok": ok, "warnings": warnings,
            "risk_per_share": round(risk, 2), "total_risk_rs": round(risk * qty, 2),
            "reward_risk": rr, "cost_rs": round(cost, 2)}


def portfolio_heat(positions: list[dict], capital: float) -> dict:
    """Sum of open risk across positions vs capital."""
    total_risk = sum(max(p.get("entry", 0) - p.get("stop", 0), 0) * p.get("qty", 0)
                     for p in positions)
    heat = round(total_risk / capital * 100, 2) if capital else 0
    return {"open_risk_rs": round(total_risk, 2), "heat_pct": heat,
            "status": "OK" if heat <= 6 else "HIGH — reduce exposure" if heat <= 10
            else "DANGER — cut risk immediately"}
