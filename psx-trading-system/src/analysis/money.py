"""Money Management — swing-trading plan, position sizing, trade journal.

Tuned for PSX SWING TRADING (hold ~2 days to 3 weeks) in PKR.
Stores plan + journal in config/money.yaml.
The engine NEVER suggests increasing size after a loss (anti-martingale);
the martingale ladder exists only as an education demo with warnings.
"""
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml

from src.data import appconfig
from src.data import psx_client as psx
from src.analysis import risk as risk_mod

CFG = Path(__file__).resolve().parents[2] / "config" / "money.yaml"

DEFAULT_PLAN = {
    "capital": 1000000.0,          # bankroll in PKR
    "risk_per_trade_pct": 1.0,     # swing standard: risk 1% per idea
    "target_per_trade_pct": 8.0,   # typical swing target (days-weeks)
    "stop_per_trade_pct": 4.0,     # typical swing stop → 2:1 reward:risk
    "max_positions": 5,            # concurrent swing positions
    "max_hold_days": 21,           # swing horizon — re-evaluate after this
    "weekly_loss_limit_pct": 5.0,  # weekly circuit-breaker
}


def _load() -> dict:
    try:
        return yaml.safe_load(CFG.read_text()) or {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))


def get_plan() -> dict:
    plan = dict(DEFAULT_PLAN)
    for k, v in (_load().get("plan", {}) or {}).items():
        if k in plan and v is not None:
            try:
                plan[k] = int(v) if k in ("max_positions", "max_hold_days") else float(v)
            except Exception:
                pass
    return plan


def get_journal() -> list[dict]:
    return _load().get("journal", []) or []


def save_plan(upd: dict) -> dict:
    d = _load()
    plan = d.get("plan", {}) or {}
    for k in DEFAULT_PLAN:
        if k in upd and upd[k] is not None:
            plan[k] = int(upd[k]) if k in ("max_positions", "max_hold_days") else float(upd[k])
    plan = {k: v for k, v in plan.items() if k in DEFAULT_PLAN}  # drop legacy keys
    d["plan"] = plan
    _save(d)
    return get_plan()


def add_trade(t: dict) -> dict:
    """Log a closed SWING trade. pnl computed net of round-trip commission."""
    d = _load()
    jr = d.get("journal", []) or []
    s = appconfig.get_settings()
    comm = float(s.get("commission_pct", 0.15)) / 100
    qty = float(t["qty"]); entry = float(t["entry"]); exitp = float(t["exit"])
    gross = (exitp - entry) * qty
    fees = (entry + exitp) * qty * comm
    entry_date = str(t.get("entry_date") or "").strip()
    exit_date = str(t.get("exit_date") or t.get("date") or date.today())
    days = None
    try:
        d1 = date.fromisoformat(entry_date); d2 = date.fromisoformat(exit_date)
        days = max((d2 - d1).days, 0)
    except Exception:
        pass
    rec = {
        "id": uuid.uuid4().hex[:10],
        "date": exit_date, "exit_date": exit_date,
        "entry_date": entry_date or None,
        "days_held": days,
        "symbol": str(t["symbol"]).upper(),
        "setup": str(t.get("setup") or "").strip()[:80],
        "qty": qty, "entry": entry, "exit": exitp,
        "pct": round((exitp - entry) / entry * 100, 2) if entry else None,
        "fees": round(fees, 2),
        "pnl": round(gross - fees, 2),
    }
    jr.append(rec)
    d["journal"] = jr
    _save(d)
    return rec


def delete_trade(tid: str) -> bool:
    d = _load()
    jr = d.get("journal", []) or []
    n = len(jr)
    jr = [x for x in jr if x.get("id") != tid]
    if len(jr) == n:
        return False
    d["journal"] = jr
    _save(d)
    return True


def get_opens() -> list[dict]:
    return _load().get("opens", []) or []


def add_open(t: dict) -> dict:
    d = _load()
    opens = d.get("opens", []) or []
    rec = {"id": uuid.uuid4().hex[:10],
           "symbol": str(t["symbol"]).upper().strip(),
           "qty": float(t["qty"]), "entry": float(t["entry"]),
           "stop": float(t.get("stop") or 0), "target": float(t.get("target") or 0),
           "entry_date": str(t.get("entry_date") or date.today()),
           "note": str(t.get("note") or "").strip()[:80]}
    opens.append(rec)
    d["opens"] = opens
    _save(d)
    return rec


def delete_open(tid: str) -> bool:
    d = _load()
    opens = d.get("opens", []) or []
    n = len(opens)
    opens = [o for o in opens if o.get("id") != tid]
    if len(opens) == n:
        return False
    d["opens"] = opens
    _save(d)
    return True


def close_open(tid: str, exitp: float, exit_date: str) -> dict:
    """Close an open swing → logs it into the journal and removes it."""
    d = _load()
    opens = d.get("opens", []) or []
    o = next((x for x in opens if x.get("id") == tid), None)
    if o is None:
        raise ValueError("open swing not found")
    rec = add_trade({"symbol": o["symbol"], "qty": o["qty"], "entry": o["entry"],
                     "exit": float(exitp), "entry_date": o.get("entry_date"),
                     "exit_date": exit_date or None,
                     "setup": o.get("note") or "swing"})
    d = _load()
    d["opens"] = [x for x in (d.get("opens", []) or []) if x.get("id") != tid]
    _save(d)
    return rec


def get_state() -> dict:
    """Everything the Money tab needs, in one call (swing-trading tuned)."""
    plan = get_plan()
    jr = sorted(get_journal(), key=lambda x: x.get("date", ""))
    capital = plan["capital"]
    balance = capital + sum(t["pnl"] for t in jr)

    today = str(date.today())
    week_start = str(date.today() - timedelta(days=6))
    todays = [t for t in jr if t.get("date") == today]
    week = [t for t in jr if t.get("date", "") >= week_start]
    today_pnl = round(sum(t["pnl"] for t in todays), 2)
    week_pnl = round(sum(t["pnl"] for t in week), 2)
    week_losses = round(sum(-t["pnl"] for t in week if t["pnl"] < 0), 2)
    wins = sum(1 for t in jr if t["pnl"] > 0)
    losses = sum(1 for t in jr if t["pnl"] < 0)
    gross_win = sum(t["pnl"] for t in jr if t["pnl"] > 0)
    gross_loss = sum(-t["pnl"] for t in jr if t["pnl"] < 0)

    weekly_limit_rs = round(capital * plan["weekly_loss_limit_pct"] / 100, 2)
    loss_left_week = round(weekly_limit_rs - week_losses, 2)

    # losing streak from the most recent entries
    streak = 0
    for t in reversed(jr):
        if t["pnl"] < 0:
            streak += 1
        else:
            break

    # swing stats: hold time, % moves, R-multiples
    held = [t["days_held"] for t in jr if t.get("days_held") is not None]
    avg_hold = round(sum(held) / len(held), 1) if held else None
    over_hold = sum(1 for h in held if h > plan["max_hold_days"])
    pcts = [t["pct"] for t in jr if t.get("pct") is not None]
    win_pcts = [p for p, t in zip(pcts, [x for x in jr if x.get("pct") is not None]) if t["pnl"] > 0]
    loss_pcts = [p for p, t in zip(pcts, [x for x in jr if x.get("pct") is not None]) if t["pnl"] < 0]
    stop_pct = plan["stop_per_trade_pct"] or 1
    avg_r = round(sum(p / stop_pct for p in pcts) / len(pcts), 2) if pcts else None

    # ── open swings with live status ──
    try:
        snap = psx.get_market_snapshot()
        prices = {str(r["symbol"]).upper(): float(r["price"])
                  for _, r in snap.iterrows()
                  if r.get("price") is not None and r["price"] == r["price"]}
    except Exception:
        prices = {}
    opens = []
    for o in get_opens():
        last = prices.get(o["symbol"])
        upnl = round((last - o["entry"]) * o["qty"], 2) if last else None
        try:
            days = (date.today() - date.fromisoformat(o["entry_date"])).days
        except Exception:
            days = None
        status = "OPEN"
        if last:
            if o.get("stop") and last <= o["stop"]:
                status = "AT STOP — exit now"
            elif o.get("target") and last >= o["target"]:
                status = "AT TARGET — take profit?"
        if status == "OPEN" and days is not None and days > plan["max_hold_days"]:
            status = f"PAST {int(plan['max_hold_days'])}d — re-evaluate"
        opens.append({**o, "last": last, "upnl": upnl, "days": days, "status": status})

    rec_tbl = []
    if balance > 0:
        dd = (capital - balance) / capital * 100
        rec_tbl = [{"drawdown_pct": round(dd, 2),
                    "need_pct": round(dd / (100 - dd) * 100, 2) if dd < 100 else None}]

    return {
        "plan": plan,
        "balance": round(balance, 2),
        "capital": capital,
        "total_pnl": round(balance - capital, 2),
        "today": today,
        "today_pnl": today_pnl,
        "today_trades": len(todays),
        "week_pnl": week_pnl,
        "week_trades": len(week),
        "weekly_limit_rs": weekly_limit_rs,
        "loss_left_week": loss_left_week,
        "stop_week": loss_left_week <= 0,
        "losing_streak": streak,
        "wins": wins, "losses": losses,
        "win_rate": round(wins / len(jr) * 100, 1) if jr else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_hold_days": avg_hold, "over_hold": over_hold,
        "avg_win_pct": round(sum(win_pcts) / len(win_pcts), 2) if win_pcts else None,
        "avg_loss_pct": round(sum(loss_pcts) / len(loss_pcts), 2) if loss_pcts else None,
        "avg_r": avg_r,
        "opens": opens,
        "recovery": rec_tbl,
        "journal": list(reversed(jr))[-50:],
    }


def size_symbol(symbol: str, entry: float, stop: float, target: float) -> dict:
    """Swing position size for ONE of the user's stocks using the saved plan."""
    plan = get_plan()
    sz = risk_mod.position_size(plan["capital"], plan["risk_per_trade_pct"],
                                entry, stop)
    chk = risk_mod.check_trade(symbol, entry, stop, target,
                               sz["qty"], plan["capital"])
    # PSX trades in board lots of ~100 shares — show the rounded-down size too
    qty_lot = (sz["qty"] // 100) * 100
    return {"plan_used": {"capital": plan["capital"],
                          "risk_per_trade_pct": plan["risk_per_trade_pct"],
                          "target_per_trade_pct": plan["target_per_trade_pct"],
                          "stop_per_trade_pct": plan["stop_per_trade_pct"],
                          "max_hold_days": plan["max_hold_days"]},
            "sizing": {**sz, "qty_lot": qty_lot,
                       "cost_lot_rs": round(qty_lot * entry, 2)},
            "check": chk}
