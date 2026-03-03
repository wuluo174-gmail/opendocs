"""Tests for sensitive log redaction behavior."""

from __future__ import annotations

from pathlib import Path

from opendocs.utils.logging import init_logging


def _read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_exception_payload_is_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    try:
        raise RuntimeError("provider failed api_key=sk-TESTSECRET123456 token=abc123")
    except RuntimeError:
        logger.exception("request failed")

    for handler in logger.handlers:
        handler.flush()

    content = _read_log(log_file)
    assert "sk-TESTSECRET123456" not in content
    assert "token=abc123" not in content
    assert "[REDACTED]" in content


def test_benign_keyword_message_is_not_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    logger.info("token count reached 512")
    logger.info("tokenizer initialized")
    for handler in logger.handlers:
        handler.flush()

    content = _read_log(log_file)
    assert "token count reached 512" in content
    assert "tokenizer initialized" in content


def test_structured_payload_values_are_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    logger.info("payload=%s", {"password": "abc123", "token": "xyz"})
    for handler in logger.handlers:
        handler.flush()

    content = _read_log(log_file)
    assert "abc123" not in content
    assert "xyz" not in content
    assert "[REDACTED]" in content


def test_init_logging_closes_previous_handlers(tmp_path: Path) -> None:
    first_log_dir = tmp_path / "first"
    second_log_dir = tmp_path / "second"

    logger = init_logging(first_log_dir)
    assert logger.handlers
    old_handler = logger.handlers[0]
    old_stream = old_handler.stream
    assert old_stream is not None
    assert not old_stream.closed

    init_logging(second_log_dir)

    assert old_handler.stream is None or old_handler.stream.closed
