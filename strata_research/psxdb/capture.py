"""Save and replay raw portal responses.

A *capture* is a directory of the exact bytes the PSX Data Portal returned::

    capture/
      manifest.json
      symbols.json
      market-watch.html
      indices.html
      timeseries_eod/<SYMBOL>.json
      company/<SYMBOL>.html
      historical/<SYMBOL>_<YYYY-MM>.html

Two uses:

* **Air-gapped ingestion** — pull once on a machine that can reach the portal,
  replay many times where it cannot (``psxdb from-capture``).
* **Testing** — the parser tests run against real captured markup, not invented
  HTML.

:class:`CaptureClient` mirrors the subset of :class:`PsxPortalClient` the
ingester needs, so both are interchangeable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import PortalError, PortalResponse


def _endpoint_to_path(endpoint: str) -> Path:
    """Map a client endpoint name to a capture-relative file path."""
    if endpoint == "symbols":
        return Path("symbols.json")
    if endpoint == "market-watch":
        return Path("market-watch.html")
    if endpoint == "indices":
        return Path("indices.html")
    if endpoint.startswith("timeseries/eod/"):
        return Path("timeseries_eod") / f"{endpoint.split('/')[-1]}.json"
    if endpoint.startswith("timeseries/int/"):
        return Path("timeseries_int") / f"{endpoint.split('/')[-1]}.json"
    if endpoint.startswith("company/"):
        return Path("company") / f"{endpoint.split('/')[-1]}.html"
    if endpoint.startswith("historical/"):
        return Path("historical") / f"{endpoint.split('/', 1)[1].replace('/', '_')}.html"
    safe = endpoint.replace("/", "_")
    return Path(f"{safe}.txt")


def save_capture(responses: Iterable[PortalResponse], directory: Path) -> dict[str, Any]:
    """Write recorded responses to ``directory`` and return the manifest."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for response in responses:
        relative = _endpoint_to_path(response.endpoint)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(response.body, encoding="utf-8")
        files.append(
            {
                "endpoint": response.endpoint,
                "path": relative.as_posix(),
                "url": response.url,
                "status": response.status,
                "bytes": response.size,
                "sha256": response.sha256,
            }
        )
    manifest = {
        "format": "psx-portal-capture.v1",
        "source": "https://dps.psx.com.pk",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


@dataclass
class CaptureClient:
    """Reads a capture directory, presenting the portal client interface."""

    directory: Path
    requests_made: int = 0
    responses: list[PortalResponse] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        if not self.directory.is_dir():
            raise PortalError(f"capture directory not found: {self.directory}")
        if self.responses is None:
            self.responses = []

    def __enter__(self) -> "CaptureClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def close(self) -> None:
        return None

    # ------------------------------------------------------------------
    def manifest(self) -> dict[str, Any]:
        path = self.directory / "manifest.json"
        if not path.is_file():
            return {"format": "psx-portal-capture.v1", "files": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def available(self) -> set[str]:
        manifest = self.manifest()
        return {entry["endpoint"] for entry in manifest.get("files", [])}

    def _read(self, endpoint: str) -> PortalResponse:
        relative = _endpoint_to_path(endpoint)
        path = self.directory / relative
        if not path.is_file():
            raise PortalError(
                f"{endpoint}: not present in the capture ({relative.as_posix()})",
                url=f"capture://{relative.as_posix()}",
            )
        body = path.read_text(encoding="utf-8", errors="replace")
        self.requests_made += 1
        response = PortalResponse(
            endpoint=endpoint,
            url=f"capture://{relative.as_posix()}",
            status=200,
            body=body,
        )
        self.responses.append(response)
        return response

    # ------------------------------------------------------- interface parity
    def symbols(self) -> list[dict[str, Any]]:
        payload = self._read("symbols").json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            payload = payload["data"]
        if not isinstance(payload, list):
            raise PortalError("symbols: capture does not contain a JSON array")
        rows = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "name": (item.get("name") or "").strip() or None,
                    "sector": (item.get("sectorName") or "").strip() or None,
                    "is_etf": 1 if item.get("isETF") else 0,
                    "is_debt": 1 if item.get("isDebt") else 0,
                }
            )
        if not rows:
            raise PortalError("symbols: capture contained no usable symbols")
        return rows

    def market_watch(self) -> PortalResponse:
        return self._read("market-watch")

    def indices_page(self) -> PortalResponse:
        return self._read("indices")

    def eod(self, symbol: str) -> PortalResponse:
        return self._read(f"timeseries/eod/{symbol}")

    def intraday(self, symbol: str) -> PortalResponse:
        return self._read(f"timeseries/int/{symbol}")

    def company(self, symbol: str) -> PortalResponse:
        return self._read(f"company/{symbol}")

    def historical_month(self, symbol: str, month: int, year: int) -> PortalResponse:
        return self._read(f"historical/{symbol}/{year}-{month:02d}")

    def eod_series(self, symbol: str) -> list[list[float]]:
        from .parsers import parse_eod_series

        bars = parse_eod_series(self._read(f"timeseries/eod/{symbol}").json(), symbol)
        return [
            [bar["ts"], bar["close"], bar["volume"], bar["open"]]  # type: ignore[list-item]
            for bar in bars
        ]
