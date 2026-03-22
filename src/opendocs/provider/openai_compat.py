"""OpenAI-compatible cloud adapter — covers OpenAI, Qwen (DashScope), Zhipu."""

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

OPENAI_DEFAULTS = {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "key_name": "openai",
}

QWEN_DEFAULTS = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-plus",
    "key_name": "qwen",
}

ZHIPU_DEFAULTS = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
    "key_name": "zhipu",
}


class OpenAICompatProvider:
    """Single adapter for any OpenAI chat-completions-compatible API."""

    kind = ProviderKind.REMOTE

    def __init__(
        self,
        base_url: str,
        model: str,
        key_name: str,
        key_store: KeyStore,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._key_name = key_name
        self._key_store = key_store

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        api_key = self._require_key()
        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]
        body = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        endpoint = f"{self._base_url}/chat/completions"
        resp = http_post_json(
            endpoint,
            body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        text = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

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
