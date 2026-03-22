"""TC-015: Local-Only mode must produce ZERO external network requests.

Strategy: monkeypatch socket.socket.connect to block any non-localhost connection.
"""

from __future__ import annotations

import socket

import pytest
from sqlalchemy.engine import Engine

from opendocs.provider.base import GenerateRequest, PrivacyMode
from opendocs.provider.mock import MockProvider
from opendocs.provider.service import ProviderService


class NetworkLeakError(AssertionError):
    """Raised when a forbidden outbound connection is attempted."""


_LOCALHOST = frozenset({"localhost", "127.0.0.1", "::1"})
_original_connect = socket.socket.connect


@pytest.fixture()
def block_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Block all outbound connections except localhost. Collect attempts."""
    attempts: list[str] = []

    def _guarded_connect(self: socket.socket, address: object) -> object:
        if isinstance(address, tuple) and len(address) >= 2:
            host = str(address[0])
            if host not in _LOCALHOST:
                attempts.append(host)
                raise NetworkLeakError(
                    f"Outbound connection to {host} blocked in local-only test"
                )
        return _original_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    return attempts


def test_local_only_zero_external_calls(
    block_network: list[str],
    security_engine: Engine,
) -> None:
    """Core TC-015: local mode generates zero outbound network requests."""
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider()},
        active_name="mock",
        engine=security_engine,
    )

    # Simulate the four operations: search, QA, summary, archive.
    for prompt in ["search query", "qa question", "summary request", "archive plan"]:
        resp = svc.generate(
            GenerateRequest(system_prompt="test", user_prompt=prompt)
        )
        assert resp.external_call is None

    assert len(block_network) == 0, f"External attempts detected: {block_network}"


def test_local_mode_blocks_cloud_provider(
    block_network: list[str],
) -> None:
    """Local mode must reject cloud provider selection entirely."""
    from opendocs.provider.base import ProviderKind

    class _FakeCloud:
        kind = ProviderKind.REMOTE

        def generate(self, request: GenerateRequest) -> None:
            raise AssertionError("should never reach generate")

        def is_available(self) -> bool:
            return True

    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"cloud": _FakeCloud(), "mock": MockProvider()},
        active_name="cloud",
    )

    with pytest.raises(RuntimeError, match="blocked by mode"):
        svc.generate(GenerateRequest(system_prompt="", user_prompt=""))

    assert len(block_network) == 0


def test_local_mode_no_audit_provider_call(security_engine: Engine) -> None:
    """In local mode, audit_logs should contain NO provider_call records."""
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider()},
        active_name="mock",
        engine=security_engine,
    )
    svc.generate(GenerateRequest(system_prompt="sys", user_prompt="usr"))

    summary = svc.get_external_call_summary()
    assert len(summary) == 0
