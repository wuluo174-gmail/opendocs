"""TC-016: Audit query and link tracing for external provider calls.

Verifies that cloud-mode provider calls produce audit records with
complete detail_json, and that those records are queryable by trace_id.
"""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Engine

from opendocs.domain.models import AuditLogModel
from opendocs.provider.base import (
    ExternalCallRecord,
    GenerateRequest,
    GenerateResponse,
    PrivacyMode,
    ProviderKind,
)
from opendocs.provider.service import ProviderService
from opendocs.storage.db import session_scope


class _AuditableMockCloud:
    """Mock cloud provider that returns ExternalCallRecord for audit testing."""

    kind = ProviderKind.REMOTE

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        return GenerateResponse(
            text="cloud answer",
            model="test-cloud-v1",
            usage={"prompt_tokens": 50, "completion_tokens": 20},
            external_call=ExternalCallRecord(
                target_model="test-cloud-v1",
                endpoint="https://api.example.com/v1/chat/completions",
                doc_count=2,
                char_count=len(request.user_prompt),
                token_count=50,
                snippet_summary=request.user_prompt[:80],
            ),
        )

    def is_available(self) -> bool:
        return True


def test_cloud_call_creates_audit_record(security_engine: Engine) -> None:
    """External provider call must produce an audit record with full detail."""
    svc = ProviderService(
        mode=PrivacyMode.CLOUD,
        providers={"cloud": _AuditableMockCloud()},
        active_name="cloud",
        engine=security_engine,
    )
    trace = str(uuid.uuid4())
    svc.generate(
        GenerateRequest(system_prompt="sys", user_prompt="test query"),
        trace_id=trace,
    )

    with session_scope(security_engine) as session:
        rows = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.operation == "provider_call")
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.trace_id == trace
        assert row.target_type == "provider_call"
        assert row.target_id == "test-cloud-v1"
        detail = row.detail_json
        assert detail["endpoint"] == "https://api.example.com/v1/chat/completions"
        assert detail["doc_count"] == 2
        assert detail["char_count"] > 0
        assert detail["token_count"] == 50
        assert "snippet_summary" in detail


def test_audit_query_by_trace_id(security_engine: Engine) -> None:
    """Audit records must be traceable by trace_id."""
    svc = ProviderService(
        mode=PrivacyMode.CLOUD,
        providers={"cloud": _AuditableMockCloud()},
        active_name="cloud",
        engine=security_engine,
    )
    trace = str(uuid.uuid4())
    svc.generate(
        GenerateRequest(system_prompt="s", user_prompt="q1"),
        trace_id=trace,
    )
    svc.generate(
        GenerateRequest(system_prompt="s", user_prompt="q2"),
        trace_id=trace,
    )

    with session_scope(security_engine) as session:
        rows = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.trace_id == trace)
            .all()
        )
        assert len(rows) == 2


def test_get_external_call_summary(security_engine: Engine) -> None:
    """get_external_call_summary returns provider_call audit records."""
    svc = ProviderService(
        mode=PrivacyMode.CLOUD,
        providers={"cloud": _AuditableMockCloud()},
        active_name="cloud",
        engine=security_engine,
    )
    svc.generate(
        GenerateRequest(system_prompt="s", user_prompt="query"),
        trace_id=str(uuid.uuid4()),
    )

    summary = svc.get_external_call_summary()
    assert len(summary) >= 1
    assert "detail" in summary[0]
    assert summary[0]["detail"]["endpoint"] == "https://api.example.com/v1/chat/completions"
