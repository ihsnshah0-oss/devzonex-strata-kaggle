"""LLM transport: OpenAI-compatible chat completions plus an offline client.

The desk talks to *any* OpenAI-compatible endpoint. That includes the Strata
server the Kaggle notebook starts, a local llama.cpp/Ollama server, and hosted
providers. Only the base URL, key and model name change.

No SDK is required: requests are plain ``httpx`` calls so the backend stays easy
to deploy on a free tier.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .config import Settings
from .heuristics import rule_based_analysis
from .prompts import DRAFT_MARKER_END, DRAFT_MARKER_START
from .schemas import CompanyFundamentals, QualityScore, RatioSet

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
SECRET_RE = re.compile(r"(?:sk|pk)-[A-Za-z0-9._~-]{4,}")


class LLMError(RuntimeError):
    """Raised when the model endpoint cannot produce a usable response."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""


@dataclass
class ChatMessage:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = "unknown"
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""
    latency_ms: int = 0


class ChatClient(Protocol):
    kind: str
    model_name: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatMessage:  # pragma: no cover - protocol
        ...

    def close(self) -> None:  # pragma: no cover - protocol
        ...


class OpenAIChatClient:
    """Minimal OpenAI-compatible client with bounded retries."""

    kind = "openai"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.model_name = settings.model
        self._client = client
        self._owns_client = client is None

    # ------------------------------------------------------------------
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.settings.request_timeout, connect=15.0)
            )
            self._owns_client = True
        return self._client

    def _endpoint(self) -> str:
        base = self.settings.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatMessage:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": self.settings.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        attempts = max(1, self.settings.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = self._http().post(
                    self._endpoint(), json=payload, headers=self._headers()
                )
            except httpx.TimeoutException as exc:
                last_error = LLMError(
                    f"Timed out after {self.settings.request_timeout:.0f}s talking to "
                    f"{self._endpoint()}",
                    retryable=True,
                )
                last_error.__cause__ = exc
            except httpx.HTTPError as exc:
                last_error = LLMError(
                    "Transport error talking to the model endpoint: "
                    + redact_secrets(str(exc), self.settings.api_key)
                )
                last_error.__cause__ = exc
            else:
                latency_ms = int((time.perf_counter() - started) * 1000)
                if response.status_code >= 400:
                    detail = redact_secrets(_safe_detail(response), self.settings.api_key)
                    error = LLMError(
                        f"Model endpoint returned HTTP {response.status_code}: {detail}",
                        status=response.status_code,
                        retryable=response.status_code in RETRYABLE_STATUS,
                    )
                    last_error = error
                else:
                    return self._parse(response.json(), latency_ms)

            if attempt + 1 < attempts and isinstance(last_error, LLMError) and last_error.retryable:
                time.sleep(min(4.0, 0.5 * (2 ** attempt)))
                continue
            break
        raise last_error or LLMError("Model endpoint failed without a specific error")

    def _parse(self, payload: dict[str, Any], latency_ms: int) -> ChatMessage:
        choices = payload.get("choices") or []
        if not choices:
            raise LLMError("Model response contained no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        tool_calls = [
            ToolCall(
                id=str(item.get("id") or f"call_{index}"),
                name=str((item.get("function") or {}).get("name") or ""),
                arguments=(item.get("function") or {}).get("arguments") or "",
            )
            for index, item in enumerate(message.get("tool_calls") or [])
            if (item.get("function") or {}).get("name")
        ]
        return ChatMessage(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            model=str(payload.get("model") or self.model_name),
            usage=dict(payload.get("usage") or {}),
            finish_reason=str(choice.get("finish_reason") or ""),
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None


def redact_secrets(text: str, secret: str | None = None) -> str:
    """Strip anything that looks like a credential from an error string."""
    cleaned = text or ""
    if secret:
        cleaned = cleaned.replace(secret, "<redacted>")
    return SECRET_RE.sub("<redacted>", cleaned)


def _safe_detail(response: httpx.Response) -> str:
    """Extract a short, secret-free error detail from an error response."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        text = (response.text or "").strip()
        return text[:300] if text else response.reason_phrase
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("type") or ""
        else:
            message = str(error or payload.get("detail") or "")
        message = message.strip()
    else:
        message = str(payload)[:300]
    for marker in ("Authorization", "Bearer "):
        if marker in message:
            message = message.split(marker)[0].strip()
    return redact_secrets(message)[:300] or response.reason_phrase


class DeterministicLLM:
    """Offline 'LLM' that echoes the rule-based draft embedded in the prompt.

    It exists so the whole pipeline - prompt building, JSON validation, grounding,
    reporting - runs without credentials and inside CI.
    """

    kind = "deterministic"
    model_name = "deterministic-rules-v1"

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatMessage:
        prompt = messages[-1].get("content", "") if messages else ""
        draft = extract_draft(prompt)
        if draft is None:
            draft = {
                "verdict": "INSUFFICIENT_DATA",
                "summary": "No deterministic draft was supplied to the offline model.",
            }
        content = json.dumps(draft, ensure_ascii=False)
        return ChatMessage(
            content=content,
            model=self.model_name,
            usage={
                "prompt_tokens": max(1, len(prompt) // 4),
                "completion_tokens": max(1, len(content) // 4),
                "total_tokens": (len(prompt) + len(content)) // 4,
                "note": "estimated offline token counts",
            },
            finish_reason="stop",
        )

    def close(self) -> None:
        return None


def extract_draft(prompt: str) -> dict[str, Any] | None:
    if DRAFT_MARKER_START not in prompt or DRAFT_MARKER_END not in prompt:
        return None
    start = prompt.index(DRAFT_MARKER_START) + len(DRAFT_MARKER_START)
    end = prompt.index(DRAFT_MARKER_END, start)
    try:
        payload = json.loads(prompt[start:end])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_llm(settings: Settings) -> ChatClient:
    """Pick the real client or the offline one based on settings."""
    if settings.offline:
        return DeterministicLLM()
    if not settings.api_key:
        raise LLMError(
            "No API key configured. Set STRATA_API_KEY (or OPENAI_API_KEY), or use "
            "STRATA_RESEARCH_LLM=template for the offline desk."
        )
    return OpenAIChatClient(settings)


def draft_for(
    company: CompanyFundamentals,
    ratios: RatioSet,
    scores: QualityScore,
    focus: str,
) -> dict[str, Any]:
    """Build the deterministic draft injected into the prompt."""
    return rule_based_analysis(company, ratios, scores, focus=focus).model_dump()
