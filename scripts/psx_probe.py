"""Probe the PSX Data Portal for reachable data routes (fingerprint + route matrix).

Why this exists: the portal exposes JSON under ``/timeseries/{type}/{symbol}`` and
HTML fragments under ``/indices/{code}``, ``/performers``, ``/daily-downloads``,
etc. From a datacentre IP some of those answer 404/403 while ordinary pages work,
which usually means the WAF is fingerprinting the client. This script compares
clients (curl HTTP/1.1, curl HTTP/2, httpx HTTP/1.1, httpx HTTP/2), prints the
exact status/headers, and reports what each reachable route contains.

It writes ``data/probe.json`` (committed) plus raw bodies in ``captures/probe/``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx

BASE = "https://dps.psx.com.pk"
SYMBOL = "OGDC"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
}

#: routes worth testing, with the HTTP method the portal itself uses
TARGETS = [
    ("GET", "/timeseries/eod/{symbol}", None),
    ("GET", "/timeseries/int/{symbol}", None),
    ("GET", "/symbols", None),
    ("GET", "/market-watch", None),
    ("GET", "/indices/{symbol_index}", None),
    ("GET", "/indices/KSE100", None),
    ("GET", "/indices/KMI30", None),
    ("GET", "/performers", None),
    ("GET", "/listings-table/all", None),
    ("GET", "/trading-board/{symbol}", None),
    ("POST", "/daily-downloads", {"date": "2026-10-29"}),
    ("POST", "/daily-downloads", {"date": "29/10/2026"}),
    ("POST", "/historical-downloads", {}),
    ("GET", "/other-downloads", None),
    ("GET", "/data/top-10-symbols", None),
]


def curl(url: str, method: str, data: dict[str, str] | None, http2: bool) -> dict[str, object]:
    """Ask curl for the status line and headers."""
    command = [
        "curl", "-sS", "-D", "-", "-o", "/dev/null", "--max-time", "30",
        "--compressed", "-X", method, "-A", UA,
        "-H", f"Referer: {BASE}/", "-H", "Accept: */*",
    ]
    command.append("--http2" if http2 else "--http1.1")
    for key, value in (data or {}).items():
        command += ["--data-urlencode", f"{key}={value}"]
    command.append(url)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    head = completed.stdout.split("\r\n\r\n")[0]
    status = None
    match = re.search(r"HTTP/[\d.]+\s+(\d{3})", head)
    if match:
        status = int(match.group(1))
    server = re.search(r"(?im)^server:\s*(.+)$", head)
    return {
        "status": status,
        "server": server.group(1).strip() if server else None,
        "stderr": completed.stderr.strip()[:200] or None,
    }


def _shape(html: str, limit: int = 3) -> list[dict[str, object]]:
    out = []
    for index, table in enumerate(re.findall(r"<table\b.*?</table>", html, re.IGNORECASE | re.DOTALL)):
        headers = [
            " ".join(re.sub(r"<[^>]+>", " ", cell).split())
            for cell in re.findall(r"<th\b.*?</th>", table, re.IGNORECASE | re.DOTALL)
        ]
        rows = re.findall(r"<tr\b.*?</tr>", table, re.IGNORECASE | re.DOTALL)
        sample = [
            [" ".join(re.sub(r"<[^>]+>", " ", cell).split()) for cell in re.findall(
                r"<t[dh]\b.*?</t[dh]>", row, re.IGNORECASE | re.DOTALL)][:14]
            for row in rows[1:3]
        ]
        out.append({"table": index, "rows": len(rows), "headers": headers[:18], "sample_rows": sample})
        if index + 1 >= limit:
            break
    return out


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
        "clients": {},
        "targets": {},
    }
    clients: dict[str, object] = report["clients"]  # type: ignore[assignment]
    targets: dict[str, object] = report["targets"]  # type: ignore[assignment]

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=HEADERS) as h1:
        home = h1.get(f"{BASE}/")
        clients["httpx-http1.1 /"] = {
            "status": home.status_code,
            "headers": dict(home.headers),
            "cookies": dict(h1.cookies),
        }

    for path_spec, data in (("/timeseries/eod/{symbol}", None), ("/symbols", None), ("/indices/KSE100", None)):
        url = urljoin(BASE + "/", path_spec.replace("{symbol}", SYMBOL).lstrip("/"))
        for label, http2 in (("curl-http1.1", False), ("curl-http2", True)):
            clients[f"{label} {path_spec}"] = curl(url, "GET", data, http2)

    # httpx over HTTP/2, if the h2 extra is installed
    try:
        with httpx.Client(http2=True, timeout=args.timeout, follow_redirects=True, headers=HEADERS) as h2:
            for path_spec in ("/timeseries/eod/{symbol}", "/symbols"):
                url = urljoin(BASE + "/", path_spec.replace("{symbol}", SYMBOL).lstrip("/"))
                try:
                    response = h2.get(url)
                    clients[f"httpx-http2 {path_spec}"] = {
                        "status": response.status_code,
                        "http_version": response.http_version,
                        "bytes": len(response.text),
                    }
                except Exception as exc:
                    clients[f"httpx-http2 {path_spec}"] = {"error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        clients["httpx-http2"] = {"error": f"{type(exc).__name__}: {exc}"}

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=HEADERS) as client:
        for method, path_spec, data in TARGETS:
            path = path_spec.replace("{symbol}", SYMBOL).replace("{symbol_index}", "KSE100")
            url = urljoin(BASE + "/", path.lstrip("/"))
            key = f"{method} {path}" + (f" {sorted(data)}" if data else "")
            try:
                if method == "GET":
                    response = client.get(url)
                else:
                    response = client.post(url, data=data or {})
            except Exception as exc:
                targets[key] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            entry: dict[str, object] = {
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.text),
                "snippet": " ".join(response.text[:300].split()),
            }
            if response.status_code == 200:
                entry["tables"] = _shape(response.text)
                if raw is not None:
                    (raw / f"ok_{method}_{re.sub(r'[^A-Za-z0-9]+', '_', path)}.txt").write_text(
                        response.text, encoding="utf-8"
                    )
            targets[key] = entry

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)[:6_000_000], encoding="utf-8")
    print(f"wrote {out}")
    for key, value in targets.items():
        print(f"{value.get('status') or value.get('error')}  {key}  ({value.get('bytes', '')} bytes)")
    for key, value in clients.items():
        if "status" in value:
            print(f"client {key}: {value.get('status')} {value.get('server') or ''}")
        else:
            print(f"client {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
