"""Save and replay raw portal pages.

A capture is just the portal's own bytes, written to a directory with a manifest:

    market-watch.html      was: /market-watch (withdrawn; kept for old captures)
    screener.html          /screener
    indices.html           /indices
    indices/KSE100.html    /indices/KSE100
    company/OGDC.html      /company/OGDC
    historical.html        /historical
    home.html              /
    manifest.json          endpoint, url, status, sha256 per file

Replaying a capture through :class:`CaptureClient` runs the exact same parsers
and store as a live ingest, with no network access — which is how the parser
tests and ``python -m strata_research.psxdb from-capture`` work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import PortalError, PortalResponse


def _endpoint_to_path(endpoint: str) -> Path:
    """Map an endpoint name to its file inside a capture directory."""
    if endpoint == "home":
        return Path("home.html")
    if endpoint == "screener":
        return Path("screener.html")
    if endpoint == "indices":
        return Path("indices.html")
    if endpoint == "historical":
        return Path("historical.html")
    if endpoint.startswith("indices/"):
        return Path("indices") / f"{endpoint.split('/', 1)[1]}.html"
    if endpoint.startswith("company/"):
        return Path("company") / f"{endpoint.split('/', 1)[1]}.html"
    return Path(f"{endpoint.replace('/', '_')}.html")


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
    """Reads a capture directory, presenting the portal client's interface."""

    directory: Path
    requests_made: int = 0
    responses: list[PortalResponse] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        if not self.directory.is_dir():
            raise PortalError(f"capture directory not found: {self.directory}")

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
        return {entry["endpoint"] for entry in self.manifest().get("files", [])}

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
    def home(self) -> PortalResponse:
        return self._read("home")

    def screener(self) -> PortalResponse:
        return self._read("screener")

    def indices_page(self) -> PortalResponse:
        return self._read("indices")

    def index_constituents(self, index_code: str) -> PortalResponse:
        return self._read(f"indices/{index_code.strip().upper()}")

    def company(self, symbol: str) -> PortalResponse:
        return self._read(f"company/{symbol.strip().upper()}")

    def historical_page(self) -> PortalResponse:
        return self._read("historical")


__all__ = ["CaptureClient", "save_capture"]
