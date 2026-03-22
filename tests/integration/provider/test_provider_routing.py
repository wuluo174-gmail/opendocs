"""Integration tests for ProviderService routing logic."""

from __future__ import annotations

import pytest

from opendocs.provider.base import (
    GenerateRequest,
    GenerateResponse,
    PrivacyMode,
    ProviderKind,
)
from opendocs.provider.mock import MockProvider
from opendocs.provider.service import ProviderService


class _FakeCloudProvider:
    """Fake cloud provider for testing routing."""

    kind = ProviderKind.REMOTE

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        return GenerateResponse(text="cloud", model="fake-cloud", usage={})

    def is_available(self) -> bool:
        return True


class _UnavailableProvider:
    kind = ProviderKind.LOCAL

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        raise RuntimeError("should not be called")

    def is_available(self) -> bool:
        return False


# --- Routing tests ---


def test_local_mode_returns_local_provider() -> None:
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider()},
        active_name="mock",
    )
    req = GenerateRequest(system_prompt="test", user_prompt="hello")
    resp = svc.generate(req)
    assert resp.model == "mock-deterministic-v1"
    assert resp.external_call is None


def test_local_mode_blocks_cloud_provider() -> None:
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider(), "cloud": _FakeCloudProvider()},
        active_name="cloud",
    )
    with pytest.raises(RuntimeError, match="blocked by mode"):
        svc.generate(GenerateRequest(system_prompt="", user_prompt=""))


def test_hybrid_mode_prefers_local() -> None:
    svc = ProviderService(
        mode=PrivacyMode.HYBRID,
        providers={"mock": MockProvider(), "cloud": _FakeCloudProvider()},
        active_name="mock",
    )
    resp = svc.generate(GenerateRequest(system_prompt="", user_prompt="hi"))
    assert resp.model == "mock-deterministic-v1"


def test_cloud_mode_allows_remote() -> None:
    svc = ProviderService(
        mode=PrivacyMode.CLOUD,
        providers={"cloud": _FakeCloudProvider()},
        active_name="cloud",
    )
    resp = svc.generate(GenerateRequest(system_prompt="", user_prompt=""))
    assert resp.model == "fake-cloud"


def test_fallback_when_active_unavailable() -> None:
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={
            "bad": _UnavailableProvider(),
            "mock": MockProvider(),
        },
        active_name="bad",
    )
    resp = svc.generate(GenerateRequest(system_prompt="", user_prompt="x"))
    assert resp.model == "mock-deterministic-v1"


def test_list_providers() -> None:
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider(), "cloud": _FakeCloudProvider()},
        active_name="mock",
    )
    result = svc.list_providers()
    assert len(result) == 2
    mock_entry = next(e for e in result if e["name"] == "mock")
    assert mock_entry["active"] is True
    assert mock_entry["allowed"] is True
    cloud_entry = next(e for e in result if e["name"] == "cloud")
    assert cloud_entry["allowed"] is False


def test_generate_delegates_to_provider(local_service: ProviderService) -> None:
    req = GenerateRequest(system_prompt="test", user_prompt="hello world")
    resp = local_service.generate(req)
    assert isinstance(resp, GenerateResponse)
    assert resp.external_call is None


def test_test_provider_mock() -> None:
    svc = ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider()},
        active_name="mock",
    )
    assert svc.test_provider("mock") is True
    assert svc.test_provider("nonexistent") is False
