"""HTTP client for the PSX Data Portal (dps.psx.com.pk) — the only data source.

The portal is an unofficial, undocumented set of endpoints behind a bot filter
(DOSarrest). This client therefore:

* sends browser-like headers (a bare ``python-httpx`` request is often blocked),
* treats ``469`` (DOSarrest's "no body" refusal) as a first-class error,
* retries ``429``/``5xx``/timeouts with exponential backoff,
* validates every payload against the expected shape and raises
  :class:`PortalSchemaError` on drift instead of storing silent garbage,
* keeps the raw bytes (and their sha256) for the provenance tables.

Endpoints used (nothing else is ever contacted):

=======================  =====================================================
GET  /symbols            JSON list of listed instruments + sector + flags
GET  /market-watch       HTML table: quotes and index membership for the day
GET  /indices            HTML table of index levels (fallback)
GET  /timeseries/eod/{s} JSON ``[[epoch, close, volume, open], …]`` newest first
GET  /timeseries/int/{s} JSON intraday ticks (unused by the daily mirror)
GET  /company/{symbol}   HTML company page (market cap, P/E, financials)
POST /historical         HTML daily OHLC table for one symbol-month
=======================  =====================================================
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

import httpx

DEFAULT_BASE_URL = "https://dps.psx.com.pk"
RETRYABLE_STATUS = {408, 425, 429, 469, 500, 502, 503, 504, 520, 522, 524}
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": DEFAULT_BASE_URL + "/",
    "Connection": "keep-alive",
}


class PortalError(RuntimeError):
    """The portal could not be reached or returned an unusable response."""

    def __init__(self, message: str, *, status: int | None = None, url: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class PortalSchemaError(PortalError):
    """The portal responded, but the payload did not match the expected shape."""


@dataclass
class PortalResponse:
    endpoint: str
    url: str
    status: int
    body: str
    elapsed_ms: int = 0

    @property
    def size(self) -> int:
        return len(self.body.encode("utf-8", errors="ignore"))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8", errors="ignore")).hexdigest()

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            head = self.body.strip()[:160].replace("\n", " ")
            raise PortalSchemaError(
                f"{self.endpoint}: response was not JSON ({head!r})", status=self.status, url=self.url
            ) from exc


@dataclass
class PsxPortalClient:
    """Thin, polite, validating wrapper over the portal endpoints."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = 25.0
    retries: int = 3
    min_interval: float = 0.20
    headers: dict[str, str] = field(default_factory=lambda: dict(BROWSER_HEADERS))
    requests_made: int = 0
    responses: list[PortalResponse] = field(default_factory=list)
    _client: httpx.Client | None = None
    _last_request: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def __enter__(self) -> "PsxPortalClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={**self.headers, "Origin": self.base_url},
            )
        return self._client

    def _throttle(self) -> None:
        """Space requests out; safe to call from several worker threads."""
        if self.min_interval <= 0:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last_request
            wait = self.min_interval - elapsed
            self._last_request = time.monotonic() + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)

    def _request(
        self,
        endpoint: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        expect: str = "html",
    ) -> PortalResponse:
        url = f"{self.base_url}{path}"
        attempts = max(1, self.retries)
        last_error: PortalError | None = None
        for attempt in range(attempts):
            self._throttle()
            started = time.perf_counter()
            try:
                self.requests_made += 1
                response = self._http().request(
                    method, url, params=params, data=data,
                    headers={"Accept": "application/json"} if expect == "json" else None,
                )
            except httpx.HTTPError as exc:
                last_error = PortalError(
                    f"{endpoint}: transport error talking to {url}: {exc}", url=url
                )
            else:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                text = response.text
                if response.status_code >= 400:
                    last_error = PortalError(
                        f"{endpoint}: HTTP {response.status_code} from {url}",
                        status=response.status_code,
                        url=url,
                    )
                    if response.status_code not in RETRYABLE_STATUS:
                        raise last_error
                else:
                    if expect == "json" and not text.strip():
                        raise PortalSchemaError(
                            f"{endpoint}: empty JSON body", status=response.status_code, url=url
                        )
                    payload = PortalResponse(
                        endpoint=endpoint,
                        url=str(response.url),
                        status=response.status_code,
                        body=text,
                        elapsed_ms=elapsed_ms,
                    )
                    self.responses.append(payload)
                    return payload
            if attempt + 1 < attempts:
                # Jittered exponential backoff: the portal starts refusing
                # politely at roughly 5 requests/second.
                time.sleep(min(8.0, (0.6 * (2 ** attempt)) + random.uniform(0, 0.4)))
        if last_error is not None:
            last_error.args = (
                f"{last_error.args[0]} (after {attempts} attempt(s))",
            )
            raise last_error
        raise PortalError(f"{endpoint}: request failed without a response", url=url)

    # ------------------------------------------------------------- endpoints
    def symbols(self) -> list[dict[str, Any]]:
        """``GET /symbols`` — every listed instrument with sector and flags."""
        payload = self._request("symbols", "GET", "/symbols", expect="json").json()
        if not isinstance(payload, list):
            raise PortalSchemaError(
                f"/symbols: expected a JSON array, got {type(payload).__name__}"
            )
        rows: list[dict[str, Any]] = []
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
            raise PortalSchemaError("/symbols: payload contained no usable symbols")
        return rows

    def market_watch(self) -> PortalResponse:
        """``GET /market-watch`` — quotes for everything trading today."""
        return self._request("market-watch", "GET", "/market-watch")

    def indices_page(self) -> PortalResponse:
        """``GET /indices`` — HTML index table (fallback source for levels)."""
        return self._request("indices", "GET", "/indices")

    def eod(self, symbol: str) -> PortalResponse:
        """``GET /timeseries/eod/{symbol}`` — daily bars, newest first."""
        return self._request(
            f"timeseries/eod/{symbol}", "GET", f"/timeseries/eod/{symbol}", expect="json"
        )

    def intraday(self, symbol: str) -> PortalResponse:
        """``GET /timeseries/int/{symbol}`` — today's ticks, newest first."""
        return self._request(
            f"timeseries/int/{symbol}", "GET", f"/timeseries/int/{symbol}", expect="json"
        )

    def company(self, symbol: str) -> PortalResponse:
        """``GET /company/{symbol}`` — company page (stats, ratios, financials)."""
        return self._request(f"company/{symbol}", "GET", f"/company/{symbol}")

    def historical_month(self, symbol: str, month: int, year: int) -> PortalResponse:
        """``POST /historical`` — daily OHLC table for one symbol-month."""
        return self._request(
            f"historical/{symbol}/{year}-{month:02d}",
            "POST",
            "/historical",
            data={"month": str(month), "year": str(year), "symbol": symbol},
        )

    # --------------------------------------------------------------- helpers
    def eod_series(self, symbol: str) -> list[list[float]]:
        """Parse ``/timeseries/eod`` into ``[[epoch, close, volume, open], …]``.

        Rows are validated (numeric, 3-4 columns) and de-duplicated by epoch.
        """
        payload = self.eod(symbol).json()
        if isinstance(payload, dict):
            data = payload.get("data")
            status = payload.get("status")
            if status not in (None, 1, "1", "ok"):
                raise PortalSchemaError(
                    f"timeseries/eod/{symbol}: status {status!r} "
                    f"({payload.get('message') or 'no message'})"
                )
        else:
            data = payload
        if not isinstance(data, list):
            raise PortalSchemaError(
                f"timeseries/eod/{symbol}: expected a list under 'data'"
            )
        series: dict[int, list[float]] = {}
        for row in data:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            try:
                epoch = int(float(row[0]))
                close = float(row[1])
                volume = float(row[2])
                open_price = float(row[3]) if len(row) > 3 and row[3] is not None else None
            except (TypeError, ValueError):
                continue
            series[epoch] = [epoch, close, volume, open_price]  # type: ignore[list-item]
        if not series:
            raise PortalSchemaError(f"timeseries/eod/{symbol}: no usable bars")
        return [series[key] for key in sorted(series)]


def month_windows(start: date, end: date) -> Iterable[tuple[int, int]]:
    """Yield ``(month, year)`` pairs covering ``start``..``end`` inclusive."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield month, year
        month += 1
        if month > 12:
            month = 1
            year += 1
