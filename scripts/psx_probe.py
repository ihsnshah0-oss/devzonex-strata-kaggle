"""Probe the PSX Data Portal and report how to reach its data.

The portal is the only permitted source, so when a documented route 404s the
answer is to **re-discover the route**, never to switch providers. This script
reads the portal's own JavaScript (exactly what a browser runs), lists every
AJAX call site it contains, and tries the interesting routes with several
method/header/prefix combinations.

Outputs:
    data/probe.json   — compact machine-readable report (committed)
    data/api-calls.txt — every AJAX call site found in the portal's JS (committed)
    captures/probe/   — raw responses (artifact only)
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
SAMPLE = "OGDC"

BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Upgrade-Insecure-Requests": "1",
}

VARIANTS = {
    "browser": BROWSER,
    "plain": {k: v for k, v in BROWSER.items() if k not in {"Origin", "Referer"}},
    "xhr": {**BROWSER, "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01"},
}

PAGES = ["/", "/indices", "/screener", "/historical", "/downloads"]

#: paths to try, with {symbol} substituted; prefix variants cover the portal's
#: own "/shariah" | "/sukuk" prefixes and a possible "/dps" mount point.
ROUTES = [
    "/symbols",
    "/market-watch",
    "/timeseries/eod/{symbol}",
    "/historical?symbol={symbol}&month=09&year=2026",
    "/historical?symbol={symbol}",
    "/company/{symbol}",
    "/dps/timeseries/eod/{symbol}",
    "/portal/timeseries/eod/{symbol}",
    "/symbols/all",
    "/market-watch/all",
]

AJAX_RE = re.compile(r"\$\.(?:ajax|get|post|getJSON)\s*\(|\bfetch\s*\(|XMLHttpRequest")


def _save(raw: Path | None, name: str, body: str) -> None:
    if raw is None:
        return
    raw.mkdir(parents=True, exist_ok=True)
    (raw / re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:140]).write_text(body, encoding="utf-8")


def _shape(html: str, limit: int = 4) -> list[dict[str, object]]:
    out = []
    for index, table in enumerate(re.findall(r"<table\b.*?</table>", html, re.IGNORECASE | re.DOTALL)):
        headers = [
            " ".join(re.sub(r"<[^>]+>", " ", cell).split())
            for cell in re.findall(r"<th\b.*?</th>", table, re.IGNORECASE | re.DOTALL)
        ]
        rows = re.findall(r"<tr\b.*?</tr>", table, re.IGNORECASE | re.DOTALL)
        sample = [
            [" ".join(re.sub(r"<[^>]+>", " ", cell).split()) for cell in re.findall(
                r"<t[dh]\b.*?</t[dh]>", row, re.IGNORECASE | re.DOTALL)][:12]
            for row in rows[1:3]
        ]
        out.append(
            {
                "table": index,
                "rows": len(rows),
                "headers": headers[:18],
                "sample_rows": sample,
                "kse100_mentions": len(re.findall(r"KSE100", table)),
                "kmi30_mentions": len(re.findall(r"KMI30", table)),
            }
        )
        if index + 1 >= limit:
            break
    return out


def _ajax_calls(script: str) -> list[str]:
    """Every AJAX call site, with enough context to see the URL and the verb."""
    calls = []
    for match in AJAX_RE.finditer(script):
        chunk = " ".join(script[match.start() : match.start() + 420].split())
        calls.append(chunk)
    return calls


def _functions_named(script: str, needle: str, window: int = 700) -> list[str]:
    out = []
    for match in re.finditer(re.escape(needle), script):
        start = max(0, match.start() - 120)
        out.append(" ".join(script[start : start + window].split()))
        if len(out) >= 3:
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
    parser.add_argument("--calls", default="data/api-calls.txt")
    parser.add_argument("--raw", default="captures/probe")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    raw = Path(args.raw) if args.raw else None
    report: dict[str, object] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
        "pages": {},
        "routes": {},
        "js": {},
    }
    pages: dict[str, object] = report["pages"]  # type: ignore[assignment]
    routes: dict[str, object] = report["routes"]  # type: ignore[assignment]

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=BROWSER) as client:
        for path in PAGES:
            url = urljoin(BASE + "/", path.lstrip("/"))
            try:
                response = client.get(url, headers=BROWSER)
            except Exception as exc:
                pages[path] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            entry: dict[str, object] = {"status": response.status_code, "bytes": len(response.text)}
            if response.status_code == 200:
                entry["tables"] = _shape(response.text)
                _save(raw, f"page{path.replace('/', '_') or '_'}.html", response.text)
            pages[path] = entry

        # POST endpoints the pages use: downloads (data files) and history
        for path, payload in (
            ("/daily-downloads", {"date": "2026-10-29"}),
            ("/daily-downloads", {}),
            ("/historical-downloads", {}),
            ("/historical", {"symbol": SAMPLE, "month": "09", "year": "2026"}),
        ):
            key = f"POST {path} {sorted(payload)}"
            try:
                response = client.post(urljoin(BASE + "/", path.lstrip("/")), data=payload, headers=BROWSER)
                entry = {"status": response.status_code, "bytes": len(response.text)}
                if response.status_code == 200:
                    entry["tables"] = _shape(response.text, limit=2)
                    entry["snippet"] = " ".join(response.text[:200].split())
                    _save(raw, f"ok_POST_{path}_{len(payload)}.txt", response.text)
                routes[key] = entry
            except Exception as exc:
                routes[key] = {"error": f"{type(exc).__name__}: {exc}"}

        script = ""
        try:
            response = client.get(urljoin(BASE + "/", "static/script.js"), headers=BROWSER)
            script = response.text if response.status_code == 200 else ""
            _save(raw, "script.js", script)
        except Exception as exc:
            report["js"] = {"error": f"{type(exc).__name__}: {exc}"}

        if script:
            calls = _ajax_calls(script)
            Path(args.calls).parent.mkdir(parents=True, exist_ok=True)
            Path(args.calls).write_text("\n\n".join(calls), encoding="utf-8")
            report["js"] = {
                "bytes": len(script),
                "ajax_calls": len(calls),
                "getUrl_def": _functions_named(script, "getUrl:"),
                "prefix_logic": _functions_named(script, "psxPortal.prefix"),
                "timeseries_fn": _functions_named(script, "/timeseries/"),
                "historical_fn": _functions_named(script, "psx.page.Historical"),
            }

        for route in ROUTES:
            path = route.replace("{symbol}", SAMPLE)
            url = urljoin(BASE + "/", path.lstrip("/"))
            for name, headers in VARIANTS.items():
                for method in ("GET", "POST"):
                    key = f"{method} {path} [{name}]"
                    try:
                        if method == "GET":
                            response = client.get(url, headers=headers)
                        else:
                            response = client.post(url, headers=headers, data={"symbol": SAMPLE})
                    except Exception as exc:
                        routes[key] = {"error": f"{type(exc).__name__}: {exc}"}
                        continue
                    entry = {
                        "status": response.status_code,
                        "bytes": len(response.text),
                        "content_type": response.headers.get("content-type", ""),
                    }
                    if response.status_code == 200:
                        entry["snippet"] = " ".join(response.text[:200].split())
                        entry["tables"] = _shape(response.text, limit=2)
                        _save(raw, f"ok_{method}_{path}_{name}.txt", response.text)
                    routes[key] = entry

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:6_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for path, info in pages.items():
        print(f"page {path:18s} {info.get('status') or info.get('error')} {info.get('bytes', '')}")
    ok = {k: v for k, v in routes.items() if v.get("status") == 200}
    print(f"routes: {len(routes)} tried, {len(ok)} answered 200")
    for key in ok:
        print("   200", key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
