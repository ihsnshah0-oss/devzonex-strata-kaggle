"""Capture the exact markup of the PSX Data Portal pages the mirror depends on.

The portal's JSON routes (``/symbols``, ``/market-watch``,
``/timeseries/eod/{symbol}``) return 404 from the current deployment, so the
mirror reads the HTML it does publish:

    /screener                — every listed symbol with sector, index membership,
                               market cap, price, 1-year change, P/E, yield
    /indices                 — index levels (KSE100, KMI30, …)
    /indices/{CODE}          — constituents of one index, with quotes/weights
    /company/{SYMBOL}        — company statistics and announcements
    /historical              — carries the portal's own "latest trading date"

This script saves the raw markup of the rows/blocks those parsers read, so the
parsers can be written against reality instead of guesswork. Snippets go into
``data/probe.json`` (small, committed); full pages go to ``captures/probe/``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

BASE = "https://dps.psx.com.pk"
SYMBOL = "OGDC"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
}


def _first(pattern: str, text: str, size: int = 1400) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(0)[:size] if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
    parser.add_argument("--raw", default="captures/probe")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    raw = Path(args.raw) if args.raw else None
    if raw is not None:
        raw.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
        "pages": {},
    }
    pages: dict[str, object] = report["pages"]  # type: ignore[assignment]

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=HEADERS) as client:
        for path, name in (
            ("/", "home"),
            ("/screener", "screener"),
            ("/indices", "indices"),
            ("/indices/KSE100", "kse100"),
            ("/indices/KMI30", "kmi30"),
            (f"/company/{SYMBOL}", "company"),
            ("/historical", "historical"),
        ):
            url = urljoin(BASE + "/", path.lstrip("/"))
            try:
                response = client.get(url)
            except Exception as exc:
                pages[path] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            body = response.text
            entry: dict[str, object] = {"status": response.status_code, "bytes": len(body)}
            if response.status_code == 200:
                if raw is not None:
                    (raw / f"{name}.html").write_text(body, encoding="utf-8")
                entry["snippets"] = {
                    "thead": _first(r"<thead\b.*?</thead>", body, 2000),
                    "first_row": _first(r"<tbody\b.*?</tr>", body, 1600),
                    "stats_block": _first(r'<div class="stats_label".{0,1200}', body, 1400),
                    "latest_date": _first(r'<[^>]*data-latest[^>]*>', body, 400),
                    "date_picker": _first(r'id="[^"]*[Dd]ate[^"]*".{0,400}', body, 500),
                    "page_header": _first(r'class="[^"]*page__header[^"]*".{0,300}', body, 400),
                }
                entry["columns"] = [
                    " ".join(re.sub(r"<[^>]+>", " ", cell).split())
                    for cell in re.findall(r"<th\b.*?</th>", body, re.IGNORECASE | re.DOTALL)
                ][:24]
                entry["epoch_values"] = sorted(
                    {value for value in re.findall(r'data-[a-z-]+="(1[6-9]\d{8,12})"', body)}
                )[:10]
                entry["tables"] = len(re.findall(r"<table\b", body, re.IGNORECASE))
                entry["stats_labels"] = [
                    " ".join(re.sub(r"<[^>]+>", " ", label).split())
                    for label in re.findall(r'class="stats_label"[^>]*>(.*?)</div>', body, re.DOTALL)
                ][:60]
                # first cell of every row of every financial table: the line items
                label_rows: list[list[str]] = []
                for table in re.findall(r"<table\b.*?</table>", body, re.IGNORECASE | re.DOTALL):
                    labels = [
                        " ".join(re.sub(r"<[^>]+>", " ", cell).split())
                        for cell in re.findall(
                            r"<tr\b[^>]*>\s*<t[dh]\b[^>]*>(.*?)</t[dh]>", table, re.DOTALL
                        )
                    ]
                    if labels:
                        label_rows.append(labels[:30])
                entry["table_row_labels"] = label_rows[:8]
                # symbols the page advertises as its own index membership
                entry["index_tokens"] = sorted(set(re.findall(r"\b(KSE100|KMI30|ALLSHR|KSE30)\b", body)))[:6]
            pages[path] = entry

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:6_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for path, info in pages.items():
        print(f"{path:22s} {info.get('status') or info.get('error')} {info.get('bytes', '')} "
              f"tables={info.get('tables', '')} cols={len(info.get('columns') or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
