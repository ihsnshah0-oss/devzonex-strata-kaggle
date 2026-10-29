"""Probe the PSX Data Portal from a networked machine and report what it answers.

The portal is the only permitted data source, so when a documented route starts
returning 404 the correct response is to **re-discover the route** — never to
fall back to another provider. This script:

1. hits the documented routes (several header variants),
2. downloads the portal's own JavaScript and extracts the endpoint strings it
   builds, so the real API surface can be read instead of guessed,
3. probes every discovered API-looking path with a sample symbol substituted,
4. reports the table structure of each page that answers 200.

It writes ``data/probe.json`` (committed: small and reviewable) and stashes the
raw pages under ``captures/probe/`` (uploaded as an artifact, not committed).

Usage::

    python scripts/psx_probe.py --out data/probe.json --raw captures/probe
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Connection": "keep-alive",
}

AJAX = {
    **BROWSER,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

PAGES = ["/", "/indices", "/historical", "/screener", "/companies", "/market-watch", "/symbols"]

#: Routes the ingester currently uses; each is probed with and without a symbol.
ROUTES = [
    "/symbols",
    "/market-watch",
    "/timeseries/eod/{symbol}",
    "/timeseries/eod/{symbol}/1",
    "/timeseries/int/{symbol}",
    "/company/{symbol}",
    "/historical",
    "/api/symbols",
    "/api/market-watch",
    "/api/timeseries/eod/{symbol}",
]

KEYWORDS = ("timeseries", "market-watch", "marketWatch", "symbols", "eod", "historical", "company")


def _digest(response: httpx.Response, raw: Path | None, name: str, limit: int = 500) -> dict[str, object]:
    body = response.text or ""
    if raw is not None:
        raw.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:120]
        (raw / safe).write_text(body, encoding="utf-8")
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "server", "location", "set-cookie", "x-cache", "via"}
    }
    return {
        "status": response.status_code,
        "headers": headers,
        "bytes": len(body),
        "snippet": " ".join(body[:limit].split()),
    }


def _table_shape(html: str) -> list[dict[str, object]]:
    """Describe each table on a page: row count and header text."""
    shape = []
    for index, table in enumerate(re.findall(r"<table\b.*?</table>", html, re.IGNORECASE | re.DOTALL)):
        headers = [
            " ".join(re.sub(r"<[^>]+>", " ", cell).split())
            for cell in re.findall(r"<th\b.*?</th>", table, re.IGNORECASE | re.DOTALL)
        ]
        row_count = len(re.findall(r"<tr\b", table, re.IGNORECASE))
        shape.append({"table": index, "rows": row_count, "headers": headers[:14]})
    return shape


def _js_endpoints(script: str) -> dict[str, object]:
    """Pull endpoint-ish strings and keyword contexts out of the portal's JS."""
    literals = {
        match.group(1)
        for match in re.finditer(r"""["'`](/?[a-z0-9][a-z0-9/_.{}$-]{2,80})["'`]""", script, re.IGNORECASE)
        if "/" in match.group(1)
    }
    contexts: dict[str, list[str]] = {}
    for keyword in KEYWORDS:
        found = []
        for match in re.finditer(re.escape(keyword), script):
            found.append(" ".join(script[max(0, match.start() - 120) : match.start() + 160].split()))
            if len(found) >= 6:
                break
        if found:
            contexts[keyword] = found
    return {
        "literals": sorted(literals)[:400],
        "contexts": contexts,
        "has_prefix_var": "psxPortal" in script,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
    parser.add_argument("--raw", default="captures/probe")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()

    raw = Path(args.raw) if args.raw else None
    report: dict[str, object] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
        "checks": {},
        "pages": {},
        "js": {},
        "discovered_api": [],
        "api_probes": {},
        "notes": [],
    }
    checks: dict[str, object] = report["checks"]  # type: ignore[assignment]
    pages: dict[str, object] = report["pages"]  # type: ignore[assignment]
    api_probes: dict[str, object] = report["api_probes"]  # type: ignore[assignment]

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=BROWSER) as client:
        for path in PAGES:
            url = urljoin(BASE + "/", path.lstrip("/"))
            try:
                response = client.get(url, headers=BROWSER)
            except Exception as exc:
                checks[f"GET {path}"] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            checks[f"GET {path}"] = {"status": response.status_code}
            if response.status_code == 200:
                pages[path] = {
                    "bytes": len(response.text),
                    "tables": _table_shape(response.text),
                    "has_js_hook": "psxPortal" in response.text,
                }
                if raw is not None:
                    _digest(response, raw, f"page{path.replace('/', '_')}.html", limit=200)

        # the portal's own script: where today's routes actually come from
        script_url = urljoin(BASE + "/", "static/script.js")
        try:
            response = client.get(script_url, headers=BROWSER)
            checks["GET /static/script.js"] = {"status": response.status_code, "bytes": len(response.text)}
            if response.status_code == 200:
                js = _js_endpoints(response.text)
                report["js"] = js
                if raw is not None:
                    _digest(response, raw, "script.js", limit=200)
                # keep only API-looking literals for the probe list
                api = [
                    literal
                    for literal in js["literals"]  # type: ignore[index]
                    if re.search(r"(timeseries|market|symbol|company|indices|historical|api)", literal, re.I)
                ]
                report["discovered_api"] = api[:80]
        except Exception as exc:
            checks["GET /static/script.js"] = {"error": f"{type(exc).__name__}: {exc}"}

        # probe the routes the ingester needs, plus anything the JS revealed
        targets: list[str] = []
        for route in ROUTES:
            targets.append(route.format(symbol=SAMPLE) if "{symbol}" in route else route)
        for literal in report["discovered_api"]:  # type: ignore[union-attr]
            path = literal if literal.startswith("/") else "/" + literal
            if "timeseries" in path.lower() and "{symbol}" not in path and SAMPLE not in path:
                path = path.rstrip("/") + f"/{SAMPLE}"
            if path.count("/") >= 1 and path not in targets:
                targets.append(path)

        for path in targets[:40]:
            url = urljoin(BASE + "/", path.lstrip("/"))
            for label, headers in (("browser", BROWSER), ("ajax", AJAX)):
                try:
                    response = client.get(url, headers=headers)
                except Exception as exc:
                    api_probes[f"GET {path} [{label}]"] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                entry = {"status": response.status_code, "content_type": response.headers.get("content-type", "")}
                if response.status_code == 200:
                    entry["bytes"] = len(response.text)
                    entry["snippet"] = " ".join(response.text[:220].split())
                    if raw is not None:
                        _digest(response, raw, f"api_{path.strip('/')}_{label}.txt", limit=200)
                api_probes[f"GET {path} [{label}]"] = entry

        # form-based history endpoint, as the site's own page uses it
        for label, headers in (("browser", BROWSER), ("ajax", AJAX)):
            try:
                response = client.post(
                    f"{BASE}/historical",
                    data={"symbol": SAMPLE, "month": "09", "year": "2026"},
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                )
                entry = {"status": response.status_code, "bytes": len(response.text)}
                if response.status_code == 200:
                    entry["tables"] = _table_shape(response.text)[:3]
                api_probes[f"POST /historical [{label}]"] = entry
            except Exception as exc:
                api_probes[f"POST /historical [{label}]"] = {"error": f"{type(exc).__name__}: {exc}"}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:6_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for name, result in checks.items():
        print(f"{name:34s} {result.get('status') or result.get('error')}")
    working = {k: v for k, v in api_probes.items() if v.get("status") == 200}
    print(f"api probes: {len(api_probes)} tried, {len(working)} answered 200")
    for name in working:
        print("  200", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
