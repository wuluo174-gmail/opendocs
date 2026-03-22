"""Anthropic Messages API adapter — separate from OpenAI-compat due to different format."""

from __future__ import annotations

import logging

from opendocs.provider._http import http_post_json
from opendocs.provider.base import (
    ExternalCallRecord,
    GenerateRequest,
    GenerateResponse,
    ProviderKind,
)
from opendocs.provider.keystore import KeyStore, mask_key

_log = logging.getLogger(__name__)

ANTHROPIC_DEFAULTS = {
    "base_url": "https://api.anthropic.com",
    "model": "claude-sonnet-4-20250514",
    "key_name": "anthropic",
}


class AnthropicProvider:
    """Anthropic Messages API adapter."""

    kind = ProviderKind.REMOTE

    def __init__(
        self,
        base_url: str = ANTHROPIC_DEFAULTS["base_url"],
        model: str = ANTHROPIC_DEFAULTS["model"],
        key_name: str = ANTHROPIC_DEFAULTS["key_name"],
        key_store: KeyStore | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._key_name = key_name
        self._key_store = key_store or KeyStore()

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        api_key = self._require_key()
        body = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        endpoint = f"{self._base_url}/v1/messages"
        resp = http_post_json(
            endpoint,
            body,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        text_blocks = [b["text"] for b in resp.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_blocks)
        usage = resp.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        char_count = len(request.user_prompt)
        snippet = request.user_prompt[:80]

        return GenerateResponse(
            text=text,
            model=self._model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            external_call=ExternalCallRecord(
                target_model=self._model,
                endpoint=endpoint,
                doc_count=1,
                char_count=char_count,
                token_count=prompt_tokens,
                snippet_summary=snippet,
            ),
        )

    def is_available(self) -> bool:
        return self._key_store.has(self._key_name)

    def _require_key(self) -> str:
        key = self._key_store.get(self._key_name)
        if not key:
            raise RuntimeError(
                f"API key for '{self._key_name}' not found in keyring. "
                f"Use settings to configure it."
            )
        _log.debug("Using API key %s for %s", mask_key(key), self._key_name)
        return key
