#!/usr/bin/env python3
"""Pre-flight check: is this installation actually able to serve the desk?

Run it after installing requirements and before starting the server:

    .venv/bin/python scripts/verify_build.py

It answers four questions — can the app import, is there market data to serve,
does every module compile, and is the paper-trading ledger where it should be —
then prints BUILD OK or the exact list of problems.
"""
from __future__ import annotations

import compileall
import importlib
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.environ.setdefault("PSX_OFFLINE", "1")

OK, FAIL = "  ok   ", "  FAIL "
problems: list[str] = []


def check(label: str, fn) -> None:
    try:
        detail = fn()
        print(f"{OK}{label}" + (f" — {detail}" if detail else ""))
    except Exception as exc:                      # noqa: BLE001 - report everything
        problems.append(f"{label}: {exc}")
        print(f"{FAIL}{label} — {type(exc).__name__}: {exc}")


def imports():
    mods = ["src.data.mirror", "src.data.psx_client", "src.data.fundamentals",
            "src.data.news", "src.screener.engine", "src.agents.analysis",
            "src.backtest.engine", "src.app.server"]
    for m in mods:
        importlib.import_module(m)
    return f"{len(mods)} modules"


def mirror_ready():
    from src.data import mirror
    if not mirror.available():
        raise RuntimeError(f"portal mirror not found ({mirror.error()})")
    cov = mirror.coverage()
    return (f"{cov['symbols']:,} symbols · {cov['bars']:,} bars · "
            f"as of {cov['as_of'][:10]}")


def snapshot_serves():
    from src.data import psx_client
    snap = psx_client.get_market_snapshot()
    if snap.empty:
        raise RuntimeError("market snapshot is empty")
    if "price" not in snap or snap["price"].notna().sum() < 50:
        raise RuntimeError("snapshot has too few prices")
    return f"{len(snap):,} rows, {int(snap['price'].notna().sum()):,} priced"


def history_serves():
    from src.data import psx_client
    df = psx_client.get_history("OGDC")
    if len(df) < 250:
        raise RuntimeError(f"only {len(df)} bars for OGDC")
    return f"OGDC {len(df):,} bars"


def indexes_ok():
    from src.data import mirror
    codes = {i["code"] for i in mirror.indices()}
    for need in ("KSE100", "KMI30"):
        if need not in codes:
            raise RuntimeError(f"{need} missing from the mirror")
    return "KSE100 + KMI30"


def ledgers_separate():
    from src.data import mirror
    mp = mirror.path()
    ledger = BASE / "data" / "psx.db"
    if mp and mp.name.startswith("psx.db") and mp == ledger:
        raise RuntimeError("mirror and paper ledger are the same file")
    return "portal.db ≠ psx.db"


def compiles():
    if not compileall.compile_dir(str(BASE / "src"), quiet=2, force=True):
        raise RuntimeError("syntax errors under src/")
    return "src/ compiles"


def config_present():
    for name in ("watchlist.yaml", "money.yaml"):
        p = BASE / "config" / name
        if not p.exists():
            raise RuntimeError(f"missing config/{name}")
    import yaml
    wl = yaml.safe_load((BASE / "config" / "watchlist.yaml").read_text()) or {}
    syms = wl.get("watchlist") or wl.get("symbols") or []
    if len(syms) < 1:
        raise RuntimeError("watchlist.yaml is empty")
    return f"{len(syms)} watchlist symbols"


def main() -> int:
    print("PSX Live & Research — build verification")
    print(f"  python {sys.version.split()[0]} · {BASE}\n")
    check("app imports", imports)
    check("portal mirror", mirror_ready)
    check("market snapshot", snapshot_serves)
    check("price history", history_serves)
    check("index levels", indexes_ok)
    check("files are separate", ledgers_separate)
    check("sources compile", compiles)
    check("configuration", config_present)
    print()
    if problems:
        print(f"BUILD FAILED — {len(problems)} problem(s)")
        for p in problems:
            print(f"  · {p}")
        return 1
    print("BUILD OK — ready to serve the desk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
