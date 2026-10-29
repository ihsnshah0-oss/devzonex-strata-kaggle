"""Runtime configuration for the research desk.

Everything is environment driven so the same code runs in three places:

* a Kaggle notebook wired to a Strata endpoint,
* a laptop talking to any OpenAI-compatible server,
* CI / offline demos with no credentials at all (template LLM).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

DEFAULT_MODEL = "qwen3.8-flash-next-gyro-gyro-s"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_PSX_BASE_URL = "https://dps.psx.com.pk"

LLMKind = Literal["auto", "openai", "template"]
DataProvider = Literal["auto", "demo", "psx", "json", "yfinance"]

#: Files the notebook / OpenCode setup writes the Strata key into.
KEY_FILE_CANDIDATES = (
    Path.home() / ".config" / "opencode" / "strata-key.txt",
    Path.home() / ".config" / "strata" / "key.txt",
    Path.home() / ".strata" / "key",
)


def _env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _env_float(default: float, *names: str) -> float:
    raw = _env(*names)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(default: int, *names: str) -> int:
    raw = _env(*names)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(default: bool, *names: str) -> bool:
    raw = _env(*names)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _read_key_file(explicit: str | None = None) -> str | None:
    candidates = (Path(explicit).expanduser(),) if explicit else KEY_FILE_CANDIDATES
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None


def mask_secret(value: str | None) -> str:
    """Return a display-safe marker for a secret; never the secret itself."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "<set>"
    return f"{value[:4]}…{value[-2:]} ({len(value)} chars)"


@dataclass(frozen=True)
class Settings:
    """Immutable configuration snapshot."""

    llm_kind: LLMKind = "auto"
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str | None = None
    api_key_source: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1600
    request_timeout: float = 180.0
    max_retries: int = 2
    data_provider: DataProvider = "auto"
    data_dir: Path | None = None
    psx_dir: Path | None = None
    psx_quotes: bool = True
    psx_base_url: str = DEFAULT_PSX_BASE_URL
    psx_quote_timeout: float = 12.0
    allow_deterministic_fallback: bool = True
    max_repair_attempts: int = 1
    report_history: int = 50
    enable_tools: bool = True

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "Settings":
        key = _env("STRATA_API_KEY", "OPENAI_API_KEY")
        key_source = "environment" if key else None
        if not key:
            key = _read_key_file(_env("STRATA_API_KEY_FILE", "STRATA_KEY_FILE"))
            key_source = "key file" if key else None

        kind = (_env("STRATA_RESEARCH_LLM") or "auto").lower()
        if kind in {"openai", "strata", "openai-compatible"}:
            kind = "openai"
        elif kind in {"template", "mock", "offline", "demo"}:
            kind = "template"
        else:
            kind = "auto"

        provider = (_env("STRATA_RESEARCH_PROVIDER") or "auto").lower()
        if provider not in {"auto", "demo", "psx", "json", "yfinance"}:
            provider = "auto"

        data_dir_raw = _env("STRATA_RESEARCH_DATA_DIR")
        psx_dir_raw = _env("STRATA_RESEARCH_PSX_DIR")
        default_psx_dir = Path("data/psx")
        psx_dir = (
            Path(psx_dir_raw).expanduser()
            if psx_dir_raw
            else (default_psx_dir if default_psx_dir.is_dir() else None)
        )
        return cls(
            llm_kind=kind,  # type: ignore[arg-type]
            base_url=_env("STRATA_BASE_URL", "OPENAI_BASE_URL") or DEFAULT_BASE_URL,
            model=_env("STRATA_MODEL", "OPENAI_MODEL") or DEFAULT_MODEL,
            api_key=key,
            api_key_source=key_source,
            temperature=_env_float(0.2, "STRATA_RESEARCH_TEMPERATURE"),
            max_tokens=_env_int(1600, "STRATA_RESEARCH_MAX_TOKENS"),
            request_timeout=_env_float(180.0, "STRATA_RESEARCH_TIMEOUT"),
            max_retries=_env_int(2, "STRATA_RESEARCH_RETRIES"),
            data_provider=provider,  # type: ignore[arg-type]
            data_dir=Path(data_dir_raw).expanduser() if data_dir_raw else None,
            psx_dir=psx_dir,
            psx_quotes=_env_bool(True, "STRATA_RESEARCH_PSX_QUOTES"),
            psx_base_url=_env("STRATA_RESEARCH_PSX_BASE_URL") or DEFAULT_PSX_BASE_URL,
            psx_quote_timeout=_env_float(12.0, "STRATA_RESEARCH_PSX_TIMEOUT"),
            allow_deterministic_fallback=_env_bool(
                True, "STRATA_RESEARCH_ALLOW_FALLBACK"
            ),
            max_repair_attempts=_env_int(1, "STRATA_RESEARCH_REPAIR_ATTEMPTS"),
            report_history=_env_int(50, "STRATA_RESEARCH_REPORT_HISTORY"),
            enable_tools=_env_bool(True, "STRATA_RESEARCH_TOOLS"),
        )

    # ------------------------------------------------------------------
    @property
    def resolved_llm_kind(self) -> Literal["openai", "template"]:
        """Resolve ``auto`` -> real endpoint when a key exists, else demo LLM."""
        if self.llm_kind == "auto":
            return "openai" if self.api_key else "template"
        return self.llm_kind  # type: ignore[return-value]

    @property
    def offline(self) -> bool:
        return self.resolved_llm_kind == "template"

    def with_llm(self, kind: LLMKind) -> "Settings":
        return replace(self, llm_kind=kind)

    def public_dict(self) -> dict[str, object]:
        """Settings safe to expose over HTTP (no secrets)."""
        return {
            "llm_kind": self.resolved_llm_kind,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": mask_secret(self.api_key),
            "api_key_source": self.api_key_source,
            "market": "PSX",
            "data_provider": self.data_provider,
            "data_dir": str(self.data_dir) if self.data_dir else None,
            "psx_dir": str(self.psx_dir) if self.psx_dir else None,
            "psx_quotes": self.psx_quotes,
            "allow_deterministic_fallback": self.allow_deterministic_fallback,
            "enable_tools": self.enable_tools,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
