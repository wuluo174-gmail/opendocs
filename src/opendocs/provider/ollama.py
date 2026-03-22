"""Ollama local LLM adapter — ProviderKind.LOCAL, zero external network."""

from __future__ import annotations

import logging

from opendocs.provider._http import http_get_ok, http_post_json
from opendocs.provider.base import (
    GenerateRequest,
    GenerateResponse,
    ProviderKind,
)

_log = logging.getLogger(__name__)


class OllamaProvider:
    """Ollama REST adapter. Runs on localhost — classified as LOCAL."""

    kind = ProviderKind.LOCAL

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        body = {
            "model": self._model,
            "system": request.system_prompt,
            "prompt": request.user_prompt,
            "stream": False,
            "options": {"num_predict": request.max_tokens},
        }
        resp = http_post_json(f"{self._base_url}/api/generate", body)
        text = resp.get("response", "")
        return GenerateResponse(
            text=text,
            model=self._model,
            usage={
                "prompt_tokens": resp.get("prompt_eval_count", 0),
                "completion_tokens": resp.get("eval_count", 0),
            },
        )

    def is_available(self) -> bool:
        return http_get_ok(f"{self._base_url}/api/tags")
