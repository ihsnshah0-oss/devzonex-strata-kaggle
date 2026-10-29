"""Read the exact label/value pairs and units the PSX Data Portal publishes.

The mirror's parsers must match reality, not guesses: this probe dumps the
(label, value) pairs from a company page, the sector filter options from
/screener, and the financial table headers, so units ("market cap in millions")
and label spellings are visible. Output goes to ``data/probe.json``.
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

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
TAG = re.compile(r"<[^>]+>")


def text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_module.unescape(TAG.sub(" ", raw)).replace("\xa0", " ")).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
    parser.add_argument("--raw", default="captures/probe")
    args = parser.parse_args()

    raw = Path(args.raw) if args.raw else None
    if raw is not None:
        raw.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
    }

    with httpx.Client(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
        client.get(f"{BASE}/")  # session cookie, like a browser

        company = client.get(f"{BASE}/company/{SYMBOL}")
        body = company.text
        if raw is not None:
            (raw / f"company_{SYMBOL}.html").write_text(body, encoding="utf-8")
        pairs = [
            {"label": text(label), "value": text(value)}
            for label, value in re.findall(
                r'class="[^"]*stats_label[^"]*"[^>]*>(.*?)</(?:div|span|p)>\s*'
                r'<(?:div|span|p)[^>]*class="[^"]*stats_value[^"]*"[^>]*>(.*?)</(?:div|span|p)>',
                body,
                re.DOTALL,
            )
        ]
        report["company"] = {"status": company.status_code, "pairs": pairs[:60]}

        financial_tables = []
        for table in re.findall(r"<table\b.*?</table>", body, re.IGNORECASE | re.DOTALL)[:8]:
            head = [
                text(cell) for cell in re.findall(r"<thead\b.*?</thead>", table, re.DOTALL)
                for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", cell)
            ]
            first_rows = [
                [text(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row)]
                for row in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.DOTALL)[:4]
            ]
            financial_tables.append({"head_row": head[:10], "sample": [r[:8] for r in first_rows]})
        report["financial_tables"] = financial_tables

        screener = client.get(f"{BASE}/screener")
        options = [
            {"value": value, "text": text(label)}
            for value, label in re.findall(
                r"<option[^>]*value=\"([^\"]*)\"[^>]*>(.*?)</option>", screener.text, re.DOTALL
            )
        ]
        report["screener"] = {
            "status": screener.status_code,
            "select_count": len(re.findall(r"<select", screener.text)),
            "options": options[:80],
            "sector_cell_samples": re.findall(
                r'<td[^>]*data-name="sector"[^>]*>.*?</td>|<td>0\d{3}</td>', screener.text
            )[:5],
        }

        kse = client.get(f"{BASE}/indices/KSE100")
        report["kse100_first_rows"] = [
            row[:900] for row in re.findall(r"<tr\b.*?</tr>", kse.text, re.DOTALL)[1:3]
        ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:4_000_000], encoding="utf-8")
    print(f"wrote {out}")
    print("company pairs:", len(report["company"]["pairs"]))
    for pair in report["company"]["pairs"][:25]:
        print(f"   {pair['label']!r:32s} -> {pair['value']!r}")
    print("screener selects:", report["screener"]["select_count"], "options:", len(options))
    for option in options[:10]:
        print("   option", option)
    return 0


if __name__ == "__main__":
    sys.exit(main())
