"""TC-017: Keyring credential management and sensitive data masking.

Verifies:
- keyring round-trip (store → read → delete)
- mask_key redaction
- API keys never appear in logs or audit detail_json
"""

from __future__ import annotations

import logging
import uuid

import pytest
from sqlalchemy.engine import Engine

from opendocs.provider.base import (
    ExternalCallRecord,
    GenerateRequest,
    GenerateResponse,
    PrivacyMode,
    ProviderKind,
)
from opendocs.provider.keystore import KeyStore, mask_key
from opendocs.provider.service import ProviderService
from opendocs.storage.db import session_scope
from opendocs.domain.models import AuditLogModel


# --- mask_key tests ---


def test_mask_key_normal() -> None:
    assert mask_key("sk-1234567890abcdef") == "sk-****cdef"


def test_mask_key_short() -> None:
    assert mask_key("short") == "****"
    assert mask_key("12345678") == "****"


def test_mask_key_nine_chars() -> None:
    result = mask_key("123456789")
    assert "****" in result
    assert result == "123****6789"


# --- keyring round-trip ---


@pytest.fixture()
def key_store() -> KeyStore:
    return KeyStore()


def test_keyring_roundtrip(key_store: KeyStore) -> None:
    provider = "test-roundtrip"
    secret = "sk-test-roundtrip-secret-value"
    try:
        key_store.set(provider, secret)
        assert key_store.get(provider) == secret
        assert key_store.has(provider) is True
    finally:
        key_store.delete(provider)
        assert key_store.get(provider) is None
        assert key_store.has(provider) is False


def test_delete_nonexistent_key(key_store: KeyStore) -> None:
    key_store.delete("nonexistent-provider-xyz")


# --- Key never in logs ---


class _KeyLeakCheckProvider:
    """Provider that checks key never leaks to audit."""

    kind = ProviderKind.REMOTE

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        return GenerateResponse(
            text="answer",
            model="leak-check",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            external_call=ExternalCallRecord(
                target_model="leak-check",
                endpoint="https://api.test.com/v1",
                doc_count=1,
                char_count=100,
                token_count=10,
                snippet_summary="test snippet",
            ),
        )

    def is_available(self) -> bool:
        return True


def test_key_not_in_audit_detail(security_engine: Engine) -> None:
    """API key must never appear in audit detail_json."""
    secret = "sk-super-secret-key-1234567890"
    svc = ProviderService(
        mode=PrivacyMode.CLOUD,
        providers={"cloud": _KeyLeakCheckProvider(secret)},
        active_name="cloud",
        engine=security_engine,
    )
    svc.generate(
        GenerateRequest(system_prompt="s", user_prompt="q"),
        trace_id=str(uuid.uuid4()),
    )

    with session_scope(security_engine) as session:
        rows = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.operation == "provider_call")
            .all()
        )
        for row in rows:
            detail_str = str(row.detail_json)
            assert secret not in detail_str, "API key leaked into audit detail_json"


def test_key_not_in_logs(
    caplog: pytest.LogCaptureFixture,
    security_engine: Engine,
) -> None:
    """API key must never appear in log output."""
    secret = "sk-log-leak-test-99887766"

    with caplog.at_level(logging.DEBUG):
        svc = ProviderService(
            mode=PrivacyMode.CLOUD,
            providers={"cloud": _KeyLeakCheckProvider(secret)},
            active_name="cloud",
            engine=security_engine,
        )
        svc.generate(
            GenerateRequest(system_prompt="s", user_prompt="q"),
            trace_id=str(uuid.uuid4()),
        )

    assert secret not in caplog.text, "API key leaked into log output"
