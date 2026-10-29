"""HTTP client for the PSX Data Portal (``https://dps.psx.com.pk``).

Only the endpoints this project actually reads are wrapped, and each docstring
says what the portal publishes there so the mirror's scope is auditable:

===================  =========================================================
route                what it returns
===================  =========================================================
``/``                portal shell
``/screener``        every listed symbol: sector code, index membership,
                     market cap, price, change %, 1-year change %, P/E (TTM),
                     dividend yield, free float, 30-day average volume
``/indices``         level, day high/low, change per published index
``/indices/{CODE}``  constituents of one index with LDCP, current price,
                     change, weight, index points, volume, free float, market cap
``/company/{SYM}``   company page: quote stats, ranges, ratios, announcements,
                     published financial line items
``/historical``      the portal's own "latest trading date" stamp (GET) and, as a
                     ``POST`` with ``symbol=``, the **full OHLCV history** of that
                     symbol
``/symbols``         every listed symbol as JSON (needs the request token)
===================  =========================================================

**The request token.** Since 2026-09-24 the portal answers ``404``/``403`` to data
requests that do not carry an ``X-Req-Id`` header matching ``window.__ps._k`` —
a short-lived token embedded in every HTML page (rotated roughly every five
minutes). That is why ``POST /historical`` looked withdrawn. This client now reads
the token out of any page it fetches, sends it on every request, and refreshes it
once when a data route answers 403/404.

The client is polite: one connection pool, a minimum interval between requests,
jittered backoff on 408/425/429/469/5xx and browser-shaped headers (the portal's
WAF rejects obviously automated clients).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://dps.psx.com.pk"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{DEFAULT_BASE_URL}/",
    "Upgrade-Insecure-Requests": "1",
}

#: The header the portal expects on data requests since 2026-09-24.
TOKEN_HEADER = "X-Req-Id"

#: ``window.__ps = {"_k": "..."};`` — the token lives in that JSON blob.
TOKEN_PATTERN = re.compile(r"window\.__ps\s*=\s*(\{.*?\})\s*(?:;|</script>)", re.DOTALL)

#: The portal rotates the token every few minutes; refetch a little before that.
TOKEN_TTL_SECONDS = 240.0

#: Data routes answer only to XMLHttpRequests: without this the portal returns 404.
XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, application/xhtml+xml, */*; q=0.01",
    "Referer": f"{DEFAULT_BASE_URL}/",
}

#: JSON data routes (``/symbols``, ``/timeseries/*``) want JSON in ``Accept``.
JSON_XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": f"{DEFAULT_BASE_URL}/",
}

#: Statuses worth another attempt (429/469 are the portal's rate-limit answers).
RETRY_STATUSES = frozenset({408, 425, 429, 469, 500, 502, 503, 504})


def extract_portal_token(html: str) -> str | None:
    """Return ``window.__ps._k`` from a portal page, or ``None``.

    The token is a short opaque string; anything that does not look like one is
    treated as absent so a markup change degrades to "no token" instead of
    sending garbage.
    """
    match = TOKEN_PATTERN.search(html)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    token = payload.get("_k") if isinstance(payload, dict) else None
    if isinstance(token, str) and len(token) >= 16 and re.fullmatch(r"[A-Za-z0-9_\-]+", token):
        return token
    return None


class PortalError(RuntimeError):
    """A request to the portal failed."""

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status = status


class PortalSchemaError(PortalError):
    """The portal answered, but not with the shape this project expects."""


@dataclass
class PortalResponse:
    """A fetched portal page, with enough metadata to prove where it came from."""

    endpoint: str
    url: str
    status: int
    body: str
    elapsed_s: float = 0.0

    @property
    def size(self) -> int:
        return len(self.body.encode("utf-8"))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise PortalSchemaError(
                f"{self.endpoint}: expected JSON from {self.url}", url=self.url
            ) from exc

    def text(self) -> str:
        return self.body


@dataclass
class PsxPortalClient:
    """Thin, polite, validating wrapper over the portal's pages."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = 30.0
    retries: int = 3
    min_interval: float = 0.25
    headers: dict[str, str] = field(default_factory=lambda: dict(BROWSER_HEADERS))
    requests_made: int = 0
    responses: list[PortalResponse] = field(default_factory=list)
    token_ttl: float = TOKEN_TTL_SECONDS
    use_token: bool = True
    #: An externally supplied httpx client (tests, or a shared pool).
    client: httpx.Client | None = None
    _client: httpx.Client | None = None
    _last_request: float = 0.0
    _token: str | None = None
    _token_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        #: Never close a client we did not create (tests, or a shared pool).
        self._owns_client = self.client is None

    def __enter__(self) -> "PsxPortalClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
        self._client = None

    # ------------------------------------------------------------------ plumbing
    def _http(self) -> httpx.Client:
        if self._client is None:
            if self.client is not None:
                self._client = self.client
                return self._client
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers=dict(self.headers),
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

    def _remember_token(self, body: str) -> None:
        token = extract_portal_token(body)
        if token:
            with self._lock:
                self._token, self._token_at = token, time.monotonic()

    def _current_token(self) -> str | None:
        if not self.use_token:
            return None
        with self._lock:
            fresh = (
                self._token is not None
                and time.monotonic() - self._token_at < self.token_ttl
            )
            token = self._token
        return token if fresh else None

    def _refresh_token(self) -> str | None:
        """Fetch ``/`` and read the request token out of it."""
        try:
            self._request("home", "/", token=False, attempts=1, record=False)
        except PortalError:
            return None
        return self._current_token()

    def _request(
        self,
        endpoint: str,
        path: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
        token: bool = True,
        xhr: bool = False,
        accept_json: bool = False,
        attempts: int | None = None,
        record: bool = True,
    ) -> PortalResponse:
        url = f"{self.base_url}{path}"
        tries = max(1, self.retries if attempts is None else attempts)
        last_error: PortalError | None = None
        can_retry_token = token and self.use_token
        attempt = 0
        while attempt < tries:
            attempt += 1
            self._throttle()
            headers: dict[str, str] = {}
            if xhr:
                headers.update(JSON_XHR_HEADERS if accept_json else XHR_HEADERS)
            if token:
                value = self._current_token()
                if value:
                    headers[TOKEN_HEADER] = value
            started = time.perf_counter()
            try:
                with self._lock:
                    self.requests_made += 1
                response = self._http().request(
                    method, url, data=data, headers=headers or None
                )
            except httpx.HTTPError as exc:
                last_error = PortalError(
                    f"{endpoint}: {type(exc).__name__}: {exc}", url=url
                )
                # The portal closes idle keep-alive sockets, and httpx will happily
                # hand back the dead one: drop the pool so the retry dials afresh.
                self.close()
            else:
                elapsed = time.perf_counter() - started
                if response.status_code == 200:
                    body = response.text
                    self._remember_token(body)
                    payload = PortalResponse(
                        endpoint=endpoint,
                        url=url,
                        status=response.status_code,
                        body=body,
                        elapsed_s=elapsed,
                    )
                    if record:
                        with self._lock:
                            self.responses.append(payload)
                    return payload
                last_error = PortalError(
                    f"{endpoint}: HTTP {response.status_code} from {url}",
                    url=url,
                    status=response.status_code,
                )
                if response.status_code in {401, 403, 404}:
                    # Most likely a stale request token: refresh it once and retry.
                    if can_retry_token:
                        can_retry_token = False
                        with self._lock:
                            self._token, self._token_at = None, 0.0
                        if self._refresh_token() is not None:
                            attempt -= 1  # the retry is on the token, not the route
                            continue
                    break  # no token, or the route is genuinely gone: do not hammer it
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt < tries:
                backoff = min(15.0, 1.5 * (2**attempt)) + random.uniform(0, 0.5)
                time.sleep(backoff)
        if last_error is not None:
            raise last_error
        raise PortalError(f"{endpoint}: request failed without a response", url=url)

    # ---------------------------------------------------------------- endpoints
    def warmup(self) -> PortalResponse | None:
        """Fetch ``/`` once so the portal's session cookie is in place.

        Failure is not fatal: every later request reports its own error.
        """
        try:
            return self.home()
        except PortalError:
            return None

    def home(self) -> PortalResponse:
        """``GET /`` — the portal home page."""
        return self._request("home", "/")

    def screener(self) -> PortalResponse:
        """``GET /screener`` — the whole listed market in one page."""
        return self._request("screener", "/screener")

    def indices_page(self) -> PortalResponse:
        """``GET /indices`` — levels for every published index."""
        return self._request("indices", "/indices")

    def index_constituents(self, index_code: str) -> PortalResponse:
        """``GET /indices/{CODE}`` — the constituents of one index."""
        code = index_code.strip().upper()
        return self._request(f"indices/{code}", f"/indices/{code}")

    def company(self, symbol: str) -> PortalResponse:
        """``GET /company/{SYMBOL}`` — company statistics and announcements."""
        code = symbol.strip().upper()
        return self._request(f"company/{code}", f"/company/{code}")

    def historical_page(self) -> PortalResponse:
        """``GET /historical`` — carries the portal's latest trading date."""
        return self._request("historical", "/historical")

    def history(self, symbol: str) -> PortalResponse:
        """``POST /historical`` — every published daily bar for one symbol.

        The form body is just ``symbol=<TICKER>``; the portal returns an HTML table
        of Date / Open / High / Low / Close / Volume rows, oldest first, covering
        the symbol's whole listing history.
        """
        code = symbol.strip().upper()
        return self._request(
            f"history/{code}",
            "/historical",
            method="POST",
            data={"symbol": code},
            xhr=True,
        )

    def symbols_json(self) -> PortalResponse:
        """``GET /symbols`` — the portal's JSON symbol directory (1052 entries)."""
        return self._request("symbols", "/symbols", xhr=True, accept_json=True)

    def timeseries_eod(self, symbol: str) -> PortalResponse:
        """``GET /timeseries/eod/{SYM}`` — the chart's own JSON feed."""
        code = symbol.strip().upper()
        return self._request(
            f"timeseries/eod/{code}", f"/timeseries/eod/{code}", xhr=True, accept_json=True
        )

    def trading_board(self, market: str = "REG", board: str = "MAIN") -> PortalResponse:
        """``GET /trading-board/{MARKET}/{BOARD}`` — live bid/offer board."""
        return self._request(
            f"trading-board/{market}/{board}",
            f"/trading-board/{market}/{board}",
            xhr=True,
        )

    def sector_summary(self) -> PortalResponse:
        """``GET /sector-summary/sectorwise`` — advance/decline and cap per sector."""
        return self._request("sector-summary", "/sector-summary/sectorwise", xhr=True)


def request_summary(client: Any) -> dict[str, Any]:
    """Best-effort counters for the ingest report."""
    return {
        "requests": int(getattr(client, "requests_made", 0)),
        "responses": len(getattr(client, "responses", []) or []),
    }


__all__ = [
    "BROWSER_HEADERS",
    "DEFAULT_BASE_URL",
    "TOKEN_HEADER",
    "TOKEN_PATTERN",
    "TOKEN_TTL_SECONDS",
    "extract_portal_token",
    "PortalError",
    "PortalResponse",
    "PortalSchemaError",
    "PsxPortalClient",
    "RETRY_STATUSES",
    "request_summary",
]
