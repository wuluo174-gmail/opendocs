"""ProviderService — privacy-mode routing, external-call audit, factory."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import Engine

from opendocs.provider.base import (
    ALLOWED_KINDS,
    ExternalCallRecord,
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PrivacyMode,
    ProviderKind,
)
from opendocs.provider.keystore import KeyStore
from opendocs.provider.mock import MockProvider
from opendocs.provider.ollama import OllamaProvider

_log = logging.getLogger(__name__)

# Providers classified as local (never make external calls).
_LOCAL_NAMES = frozenset({"mock", "ollama"})


class ProviderService:
    """Routes LLM calls based on PrivacyMode. Audits external calls."""

    kind = ProviderKind.LOCAL  # satisfy Protocol for pass-through usage

    def __init__(
        self,
        mode: PrivacyMode,
        providers: dict[str, LLMProvider],
        active_name: str,
        engine: Engine | None = None,
    ) -> None:
        self._mode = mode
        self._providers = providers
        self._active_name = active_name
        self._engine = engine
        self._allowed = ALLOWED_KINDS[mode]

    @property
    def mode(self) -> PrivacyMode:
        return self._mode

    @property
    def active_provider_name(self) -> str:
        return self._active_name

    def generate(
        self,
        request: GenerateRequest,
        *,
        trace_id: str = "",
    ) -> GenerateResponse:
        provider = self._resolve()
        response = provider.generate(request)
        if response.external_call is not None and self._engine is not None:
            self._audit_external_call(response.external_call, trace_id or str(uuid.uuid4()))
        return response

    def is_available(self) -> bool:
        try:
            self._resolve()
            return True
        except RuntimeError:
            return False

    def _resolve(self) -> LLMProvider:
        """Pick the active provider, enforcing mode constraints."""
        provider = self._providers.get(self._active_name)
        if provider is None:
            raise RuntimeError(f"Provider '{self._active_name}' not registered")
        if provider.kind not in self._allowed:
            raise RuntimeError(
                f"Provider '{self._active_name}' (kind={provider.kind.value}) "
                f"blocked by mode={self._mode.value}"
            )
        if not provider.is_available():
            # Fallback: try any available local provider.
            for name, p in self._providers.items():
                if p.kind in self._allowed and p.is_available():
                    _log.info("Falling back from %s to %s", self._active_name, name)
                    return p
            raise RuntimeError(f"No available provider for mode={self._mode.value}")
        return provider

    def list_providers(self) -> list[dict[str, Any]]:
        result = []
        for name, p in self._providers.items():
            result.append({
                "name": name,
                "kind": p.kind.value,
                "available": p.is_available(),
                "active": name == self._active_name,
                "allowed": p.kind in self._allowed,
            })
        return result

    def test_provider(self, name: str) -> bool:
        provider = self._providers.get(name)
        if provider is None:
            return False
        return provider.is_available()

    def get_external_call_summary(self) -> list[dict[str, Any]]:
        """Query audit_logs for provider_call records."""
        if self._engine is None:
            return []
        from opendocs.domain.models import AuditLogModel
        from opendocs.storage.db import session_scope

        with session_scope(self._engine) as session:
            rows = (
                session.query(AuditLogModel)
                .filter(AuditLogModel.operation == "provider_call")
                .order_by(AuditLogModel.timestamp.desc())
                .limit(100)
                .all()
            )
            return [
                {
                    "audit_id": r.audit_id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                    "detail": r.detail_json,
                    "trace_id": r.trace_id,
                }
                for r in rows
            ]

    def _audit_external_call(
        self,
        record: ExternalCallRecord,
        trace_id: str,
    ) -> None:
        from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
        from opendocs.storage.db import session_scope

        with session_scope(self._engine) as session:  # type: ignore[arg-type]
            audit = create_audit_record(
                session,
                actor="system",
                operation="provider_call",
                target_type="provider_call",
                target_id=record.target_model,
                result="success",
                detail_json={
                    "endpoint": record.endpoint,
                    "doc_count": record.doc_count,
                    "char_count": record.char_count,
                    "token_count": record.token_count,
                    "snippet_summary": record.snippet_summary,
                },
                trace_id=trace_id,
            )
        flush_audit_to_jsonl(audit)


def create_provider_service(
    settings: Any,
    engine: Engine | None = None,
) -> ProviderService:
    """Factory: build ProviderService from OpenDocsSettings."""
    from opendocs.provider.anthropic_adapter import AnthropicProvider
    from opendocs.provider.openai_compat import (
        OPENAI_DEFAULTS,
        QWEN_DEFAULTS,
        ZHIPU_DEFAULTS,
        OpenAICompatProvider,
    )

    ps = settings.provider
    mode = PrivacyMode(ps.default_mode)
    key_store = KeyStore()

    providers: dict[str, LLMProvider] = {
        "mock": MockProvider(),
        "ollama": OllamaProvider(
            base_url=ps.ollama_url,
        ),
    }

    # Only instantiate cloud providers when mode allows remote.
    if mode != PrivacyMode.LOCAL:
        providers["openai"] = OpenAICompatProvider(
            key_store=key_store, **OPENAI_DEFAULTS,
        )
        providers["qwen"] = OpenAICompatProvider(
            key_store=key_store, **QWEN_DEFAULTS,
        )
        providers["zhipu"] = OpenAICompatProvider(
            key_store=key_store, **ZHIPU_DEFAULTS,
        )
        providers["anthropic"] = AnthropicProvider(key_store=key_store)

    active = ps.llm_provider
    if active not in providers:
        active = "mock"

    return ProviderService(
        mode=mode,
        providers=providers,
        active_name=active,
        engine=engine,
    )
