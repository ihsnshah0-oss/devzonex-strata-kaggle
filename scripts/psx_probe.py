"""Read the exact label/value pairs, routes and units the PSX Data Portal publishes.

The mirror's parsers must match reality, not guesses: this probe dumps the
(label, value) pairs from a company page, the sector filter options from
/screener, the financial table headers, and — crucially — whether the
``X-Req-Id`` request token unlocks the data routes (``POST /historical``,
``/symbols``). Output goes to ``data/probe.json``.
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

#: ``window.__ps = {"_k": "..."};`` — the portal's request token.
TOKEN_PATTERN = re.compile(r"window\.__ps\s*=\s*(\{.*?\})\s*(?:;|</script>)", re.DOTALL)


def text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_module.unescape(TAG.sub(" ", raw)).replace("\xa0", " ")).strip()


def extract_token(page: str) -> str | None:
    match = TOKEN_PATTERN.search(page)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    token = payload.get("_k") if isinstance(payload, dict) else None
    return token if isinstance(token, str) and len(token) >= 16 else None


def table_summary(page: str) -> dict[str, object]:
    """Header names plus the first data row, so a parser can match real markup."""
    tables = re.findall(r"<table\b.*?</table>", page, re.IGNORECASE | re.DOTALL)
    if not tables:
        return {"tables": 0, "headers": [], "first_row": [], "rows": 0}
    table = tables[0]
    header_cells = [
        text(cell)
        for row in re.findall(r"<tr\b.*?</tr>", table, re.DOTALL)[:1]
        for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.DOTALL)
    ]
    table_rows = re.findall(r"<tr\b.*?</tr>", table, re.DOTALL)
    first_data = [
        text(cell) for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", table_rows[1] if len(table_rows) > 1 else "", re.DOTALL)
    ]
    return {
        "tables": len(tables),
        "headers": header_cells[:10],
        "first_row": first_data[:10],
        "rows": len(table_rows),
        "raw_first_row": (table_rows[1][:600] if len(table_rows) > 1 else ""),
    }


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
        home = client.get(f"{BASE}/")  # session cookie, like a browser
        token = extract_token(home.text)
        report["token"] = {
            "found": token is not None,
            "length": len(token) if token else 0,
            "home_bytes": len(home.text),
            "home_has_window_ps": "window.__ps" in home.text,
        }

        # The data routes: without the token the portal answers 404, which is what
        # made POST /historical look withdrawn for weeks.
        auth = {"X-Req-Id": token} if token else {}
        probes: dict[str, object] = {}
        for label, method, path, data in (
            ("history_without_token", "POST", "/historical", {"symbol": SYMBOL}),
            ("history_with_token", "POST", "/historical", {"symbol": SYMBOL}),
            ("symbols_with_token", "GET", "/symbols", None),
            ("symbols_json_with_token", "GET", "/symbols", None),
        ):
            headers = dict(HEADERS)
            if label.endswith("_with_token"):
                headers.update(auth)
                if label == "symbols_json_with_token":
                    headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
                    headers["X-Requested-With"] = "XMLHttpRequest"
            response = client.request(method, f"{BASE}{path}", data=data, headers=headers)
            entry: dict[str, object] = {
                "method": method,
                "path": path,
                "status": response.status_code,
                "bytes": len(response.text),
                "content_type": response.headers.get("content-type"),
            }
            if response.status_code == 200:
                if "json" in (response.headers.get("content-type") or ""):
                    entry["json_head"] = response.text[:400]
                else:
                    entry["table"] = table_summary(response.text)
            probes[label] = entry
        report["data_routes"] = probes

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
    print("token:", report["token"])
    for label, entry in report["data_routes"].items():
        print(f"   {label:24s} {entry['status']} bytes={entry['bytes']}"
              f" tables={entry.get('table', {}).get('tables')}"
              f" rows={entry.get('table', {}).get('rows')}")
        if entry.get("table", {}).get("headers"):
            print("      headers:", entry["table"]["headers"])
            print("      first:  ", entry["table"]["first_row"])
    print("screener selects:", report["screener"]["select_count"], "options:", len(options))
    for option in options[:10]:
        print("   option", option)
    return 0


if __name__ == "__main__":
    sys.exit(main())
