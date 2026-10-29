"""Probe the PSX Data Portal from a networked machine and report what it answers.

The portal is the only permitted data source, so when an endpoint starts
returning 404 the correct response is to re-discover the endpoint — not to fall
back to another provider. This script tries the documented routes plus a few
header/format variants, fetches the portal home page and extracts the URLs it
actually references, then writes everything to a JSON report.

Usage::

    python scripts/psx_probe.py --out data/probe.json
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

AJAX = {**BROWSER, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/javascript, */*; q=0.01"}

PATHS = [
    "/",
    "/symbols",
    "/symbols/",
    "/market-watch",
    "/market-watch/",
    "/indices",
    "/timeseries/eod/OGDC",
    "/timeseries/eod/OGDC/",
    "/timeseries/int/OGDC",
    "/company/OGDC",
    "/company/OGDC/",
    "/historical/OGDC",
]


def _summary(response: httpx.Response, limit: int = 400) -> dict[str, object]:
    body = response.text or ""
    interesting = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "server", "location", "set-cookie", "x-cache", "via"}
    }
    return {
        "status": response.status_code,
        "headers": interesting,
        "bytes": len(body),
        "snippet": body[:limit].replace("\n", " ")[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/probe.json")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args()

    report: dict[str, object] = {
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base": BASE,
        "checks": {},
        "discovered_urls": [],
        "notes": [],
    }
    checks: dict[str, object] = report["checks"]  # type: ignore[assignment]

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=BROWSER) as client:
        home_html = ""
        for path in PATHS:
            url = urljoin(BASE + "/", path.lstrip("/"))
            for label, headers in (("browser", BROWSER), ("ajax", AJAX)):
                try:
                    response = client.get(url, headers=headers)
                except Exception as exc:  # network failure
                    checks[f"GET {path} [{label}]"] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                checks[f"GET {path} [{label}]"] = _summary(response)
                if path == "/" and label == "browser" and response.status_code == 200:
                    home_html = response.text

        # what shape does the portal expect for the form-based history route?
        try:
            response = client.post(
                f"{BASE}/historical",
                data={"symbol": "OGDC", "month": "09", "year": "2026"},
                headers={**BROWSER, "Content-Type": "application/x-www-form-urlencoded"},
            )
            checks["POST /historical"] = _summary(response)
        except Exception as exc:
            checks["POST /historical"] = {"error": f"{type(exc).__name__}: {exc}"}

        # plain httpx defaults, to see whether the UA matters at all
        try:
            with httpx.Client(timeout=args.timeout, follow_redirects=True) as plain:
                response = plain.get(f"{BASE}/symbols")
            checks["GET /symbols [no browser headers]"] = _summary(response)
        except Exception as exc:
            checks["GET /symbols [no browser headers]"] = {"error": f"{type(exc).__name__}: {exc}"}

    if home_html:
        found: set[str] = set()
        for match in re.finditer(r"""(?:href|src|action)\s*=\s*["']([^"']+)["']""", home_html):
            found.add(urljoin(BASE + "/", match.group(1)))
        for match in re.finditer(r"""["'](/[a-z0-9][a-z0-9/_.-]{2,60})["']""", home_html):
            found.add(urljoin(BASE + "/", match.group(1)))
        for match in re.finditer(r"""data-url\s*=\s*["']([^"']+)["']""", home_html):
            found.add(urljoin(BASE + "/", match.group(1)))
        report["discovered_urls"] = sorted(found)
        # inline JS often builds the API paths; keep any of those strings too
        script_urls = [url for url in found if url.endswith(".js")]
        report["script_urls"] = script_urls
        snippets = []
        for keyword in ("timeseries", "market-watch", "symbols", "/api", "historical", "company"):
            for match in re.finditer(keyword, home_html):
                snippets.append(home_html[max(0, match.start() - 90) : match.start() + 90])
                if len(snippets) > 40:
                    break
        report["keyword_snippets"] = snippets[:60]
    else:
        report["notes"].append("portal home page was not retrievable")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:4_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for name, result in checks.items():  # type: ignore[union-attr]
        status = result.get("status") or result.get("error")
        print(f"{name:42s} {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
