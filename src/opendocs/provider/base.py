"""LLM provider abstraction — Protocol + privacy mode per spec §11.1 / FR-012."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class PrivacyMode(str, Enum):
    """Network privacy mode — controls which provider kinds are allowed."""

    LOCAL = "local"
    HYBRID = "hybrid"
    CLOUD = "cloud"


class ProviderKind(str, Enum):
    """Whether a provider makes external network calls."""

    LOCAL = "local"
    REMOTE = "remote"


@dataclass(frozen=True)
class GenerateRequest:
    """Minimal LLM generation request."""

    system_prompt: str
    user_prompt: str
    max_tokens: int = 2048


@dataclass(frozen=True)
class ExternalCallRecord:
    """Audit record for a single outbound provider call (FR-012)."""

    target_model: str
    endpoint: str
    doc_count: int
    char_count: int
    token_count: int
    snippet_summary: str


@dataclass(frozen=True)
class GenerateResponse:
    """LLM generation response, optionally carrying external call audit."""

    text: str
    model: str
    usage: dict[str, int]
    external_call: ExternalCallRecord | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface for all LLM providers."""

    kind: ProviderKind

    def generate(self, request: GenerateRequest) -> GenerateResponse: ...

    def is_available(self) -> bool: ...


# Mode → allowed provider kinds (routing core, zero branching).
ALLOWED_KINDS: dict[PrivacyMode, frozenset[ProviderKind]] = {
    PrivacyMode.LOCAL: frozenset({ProviderKind.LOCAL}),
    PrivacyMode.HYBRID: frozenset({ProviderKind.LOCAL, ProviderKind.REMOTE}),
    PrivacyMode.CLOUD: frozenset({ProviderKind.LOCAL, ProviderKind.REMOTE}),
}
