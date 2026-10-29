"""Probe the PSX Data Portal and report how to reach its data.

The portal is the only permitted source, so when a documented route 404s the
answer is to **re-discover the route**, never to switch providers. This script
reads the portal's own JavaScript (which is what the browser runs) to find how
its URLs are built, tries the interesting routes with several method/header
combinations, and describes the table structure of every page that answers.

It writes ``data/probe.json`` (small, committed) and stashes raw responses under
``captures/probe/`` (artifact only, not committed).
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
    "browser-no-origin": {k: v for k, v in BROWSER.items() if k not in {"Origin", "Referer"}},
    "json-accept": {**BROWSER, "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest"},
}

PAGES = ["/", "/indices", "/historical", "/screener", "/downloads", "/daily-downloads"]
ROUTES = [
    "/symbols",
    "/market-watch",
    "/timeseries/eod/{symbol}",
    "/timeseries/int/{symbol}",
    "/historical",
    "/company/{symbol}",
    "/data/timeseries/eod/{symbol}",
]

JS_NEEDLES = ("getUrl", "prefix", "addRoute", "timeseries", "Historical", "Screener", "pagination")


def _raw_save(raw: Path | None, name: str, body: str) -> None:
    if raw is None:
        return
    raw.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:140]
    (raw / safe).write_text(body, encoding="utf-8")


def _shape(html: str, limit: int = 6) -> list[dict[str, object]]:
    out = []
    for index, table in enumerate(re.findall(r"<table\b.*?</table>", html, re.IGNORECASE | re.DOTALL)):
        headers = [
            " ".join(re.sub(r"<[^>]+>", " ", cell).split())
            for cell in re.findall(r"<th\b.*?</th>", table, re.IGNORECASE | re.DOTALL)
        ]
        first_rows = [
            [" ".join(re.sub(r"<[^>]+>", " ", cell).split()) for cell in re.findall(
                r"<t[dh]\b.*?</t[dh]>", row, re.IGNORECASE | re.DOTALL)]
            for row in re.findall(r"<tr\b.*?</tr>", table, re.IGNORECASE | re.DOTALL)[1:3]
        ]
        out.append(
            {
                "table": index,
                "rows": len(re.findall(r"<tr\b", table, re.IGNORECASE)),
                "headers": headers[:16],
                "sample_rows": [row[:10] for row in first_rows],
                "kse100_mentions": len(re.findall(r"KSE100", table)),
                "kmi30_mentions": len(re.findall(r"KMI30", table)),
            }
        )
        if index + 1 >= limit:
            break
    return out


def _needle_contexts(script: str) -> dict[str, list[str]]:
    contexts: dict[str, list[str]] = {}
    for needle in JS_NEEDLES:
        found = []
        for match in re.finditer(re.escape(needle), script):
            found.append(" ".join(script[max(0, match.start() - 160) : match.start() + 240].split()))
            if len(found) >= 4:
                break
        if found:
            contexts[needle] = found
    return contexts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
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
        "notes": [],
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
                entry["psxPortal_var"] = re.findall(
                    r"window\.psxPortal\s*=\s*(\{[^}]*\})", response.text
                )[:1]
                _raw_save(raw, f"page{path.replace('/', '_') or '_'}.html", response.text)
            pages[path] = entry

        script_url = urljoin(BASE + "/", "static/script.js")
        try:
            response = client.get(script_url, headers=BROWSER)
            script = response.text if response.status_code == 200 else ""
            report["js"] = {
                "status": response.status_code,
                "bytes": len(script),
                "contexts": _needle_contexts(script) if script else {},
                "timeseries_literals": sorted(
                    {"".join(m) for m in re.findall(r"""["']([^"']*timeseries[^"']*)["']""", script, re.I)}
                )[:40],
            }
            _raw_save(raw, "script.js", script)
        except Exception as exc:
            report["js"] = {"error": f"{type(exc).__name__}: {exc}"}

        # method/header matrix on the routes the ingester needs
        for route in ROUTES:
            path = route.format(symbol=SAMPLE) if "{symbol}" in route else route
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
                        "content_type": response.headers.get("content-type", ""),
                        "bytes": len(response.text),
                    }
                    if response.status_code == 200:
                        entry["snippet"] = " ".join(response.text[:240].split())
                        entry["tables"] = _shape(response.text, limit=3)
                        _raw_save(raw, f"ok_{method}_{path}_{name}.txt", response.text)
                    elif response.status_code >= 400:
                        body = " ".join(response.text[:400].split())
                        entry["snippet"] = body
                        _raw_save(raw, f"err_{response.status_code}_{method}_{path}_{name}.txt", response.text)
                    routes[key] = entry

        # the historical page's own POST, with the parameters its form uses
        for payload in (
            {"symbol": SAMPLE, "month": "09", "year": "2026"},
            {"symbol": SAMPLE, "month": "9", "year": "2026", "type": "html"},
        ):
            key = f"POST /historical {sorted(payload)}"
            try:
                response = client.post(f"{BASE}/historical", data=payload, headers=BROWSER)
                entry = {"status": response.status_code, "bytes": len(response.text)}
                if response.status_code == 200:
                    entry["tables"] = _shape(response.text, limit=2)
                routes[key] = entry
            except Exception as exc:
                routes[key] = {"error": f"{type(exc).__name__}: {exc}"}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:6_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for path, info in pages.items():
        print(f"{path:20s} {info.get('status') or info.get('error')} {info.get('bytes', '')}")
    ok = {k: v for k, v in routes.items() if v.get("status") == 200}
    print(f"routes: {len(routes)} tried, {len(ok)} answered 200")
    for key in ok:
        print("   200", key)
    for key, value in routes.items():
        if value.get("status") not in (200, None):
            print(f"   {value['status']} {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
