"""Unit tests for MockProvider."""

from opendocs.provider.base import GenerateRequest
from opendocs.provider.mock import MockProvider


def test_mock_provider_extracts_evidence():
    provider = MockProvider()
    prompt = (
        "问题：项目预算\n\n"
        "[EVIDENCE chunk_id=abc-123]\n"
        "项目预算为100万元\n"
        "[/EVIDENCE]\n"
    )
    response = provider.generate(
        GenerateRequest(system_prompt="test", user_prompt=prompt)
    )
    assert "abc-123" in response.text
    assert "[CIT:abc-123]" in response.text
    assert "100万元" in response.text
    assert response.model == "mock-deterministic-v1"


def test_mock_provider_no_evidence_returns_insufficient():
    provider = MockProvider()
    response = provider.generate(
        GenerateRequest(system_prompt="test", user_prompt="无相关内容")
    )
    assert "证据不足" in response.text


def test_mock_provider_multiple_evidence():
    provider = MockProvider()
    prompt = (
        "[EVIDENCE chunk_id=aaa]\nfact A\n[/EVIDENCE]\n"
        "[EVIDENCE chunk_id=bbb]\nfact B\n[/EVIDENCE]\n"
    )
    response = provider.generate(
        GenerateRequest(system_prompt="test", user_prompt=prompt)
    )
    assert "[CIT:aaa]" in response.text
    assert "[CIT:bbb]" in response.text


def test_mock_provider_is_available():
    assert MockProvider().is_available()


def test_mock_provider_deterministic():
    provider = MockProvider()
    req = GenerateRequest(
        system_prompt="test",
        user_prompt="[EVIDENCE chunk_id=x]\nhello\n[/EVIDENCE]\n",
    )
    r1 = provider.generate(req)
    r2 = provider.generate(req)
    assert r1.text == r2.text
