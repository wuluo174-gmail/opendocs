"""LLM provider abstraction — minimal ABC per spec §11.1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerateRequest:
    """Minimal LLM generation request."""

    system_prompt: str
    user_prompt: str
    max_tokens: int = 2048


@dataclass(frozen=True)
class GenerateResponse:
    """Minimal LLM generation response."""

    text: str
    model: str
    usage: dict[str, int]
