#!/usr/bin/env python3
"""Pre-download lite histories for the most liquid PSX symbols.

Run once (e.g. overnight or while having chai) so all screener presets
answer instantly afterwards:

    python3 scripts/warm_cache.py [N]

N = how many of the most-liquid symbols to warm (default 150).
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import psx_client as psx  # noqa: E402


def main(n: int = 150):
    snap = psx.get_market_snapshot()
    syms = (snap.sort_values("volume_avg_30d", ascending=False, na_position="last")
            ["symbol"].astype(str).str.upper().tolist()[:n])

    def one(s):
        try:
            h = psx.get_history(s, max_age_hours=24, lite=True)
            return s, len(h), ""
        except Exception as e:
            return s, 0, str(e)[:80]

    ok = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (s, rows, err) in enumerate(ex.map(one, syms), 1):
            ok += rows > 0
            print(f"[{i}/{len(syms)}] {s}: {rows} rows {err}")
    print(f"done — {ok}/{len(syms)} warmed. Presets will now be instant.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
