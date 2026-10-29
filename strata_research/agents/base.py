"""Agent scaffolding shared by every specialist on the desk."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..config import Settings
from ..llm import ChatClient, build_llm

AgentStatus = Literal["available", "planned"]


@dataclass(frozen=True)
class AgentCard:
    """Describes an agent to the API, the UI and the orchestrator."""

    key: str
    name: str
    title: str
    status: AgentStatus
    description: str
    tools: tuple[str, ...] = ()
    techniques: tuple[str, ...] = ()
    inputs: str = ""
    outputs: str = ""
    order: int = 99

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "title": self.title,
            "status": self.status,
            "description": self.description,
            "tools": list(self.tools),
            "techniques": list(self.techniques),
            "inputs": self.inputs,
            "outputs": self.outputs,
            "order": self.order,
        }


@dataclass
class BaseAgent:
    """Owns the LLM client lifecycle; subclasses implement ``run``."""

    settings: Settings
    card: AgentCard
    llm: ChatClient | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.llm is None:
            self.llm = build_llm(self.settings)

    @property
    def model_name(self) -> str:
        return getattr(self.llm, "model_name", "unknown")

    def close(self) -> None:
        if self.llm is not None:
            try:
                self.llm.close()
            except Exception:  # pragma: no cover - close must not raise
                pass


class ResponseParseError(ValueError):
    """Raised when the model did not return a usable JSON object."""


_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Handles markdown fences, leading prose and trailing commentary, which local
    models emit often. Raises :class:`ResponseParseError` with the reason.
    """
    if not text or not text.strip():
        raise ResponseParseError("model returned an empty response")
    candidate = _FENCE.sub("", text.strip())
    try:
        loaded = json.loads(candidate)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(candidate)):
            char = candidate[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    block = candidate[start:index + 1]
                    for attempt in (block, _strip_trailing_commas(block)):
                        try:
                            loaded = json.loads(attempt)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(loaded, dict):
                            return loaded
                    break
        start = candidate.find("{", start + 1)
    snippet = candidate.strip().replace("\n", " ")[:200]
    raise ResponseParseError(f"no parseable JSON object in response: {snippet!r}")


def _strip_trailing_commas(block: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", block)
