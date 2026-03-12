"""Tests for sensitive log redaction behavior."""

from __future__ import annotations

import json
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from opendocs.utils.logging import get_audit_logger, get_task_logger, init_logging


def _read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_log_entries(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in _read_log(path).splitlines() if line.strip()]


def test_logs_are_structured_json_lines(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    logger.info("hello json logger")
    for handler in logger.handlers:
        handler.flush()

    entries = _read_log_entries(log_file)
    assert len(entries) == 1
    assert entries[0]["message"] == "hello json logger"
    assert entries[0]["level"] == "INFO"
    assert entries[0]["logger"] == "opendocs"
    assert isinstance(entries[0]["timestamp"], str)


def test_exception_payload_is_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    try:
        raise RuntimeError("provider failed api_key=sk-TESTSECRET123456 token=abc123")
    except RuntimeError:
        logger.exception("request failed")

    for handler in logger.handlers:
        handler.flush()

    entries = _read_log_entries(log_file)
    content = _read_log(log_file)
    assert entries[0]["message"] == "request failed"
    assert "exception" in entries[0]
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

    entries = _read_log_entries(log_file)
    assert entries[0]["message"] == "token count reached 512"
    assert entries[1]["message"] == "tokenizer initialized"


def test_structured_payload_values_are_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    logger.info("payload=%s", {"password": "abc123", "token": "xyz"})
    for handler in logger.handlers:
        handler.flush()

    entries = _read_log_entries(log_file)
    content = _read_log(log_file)
    assert "payload=" in str(entries[0]["message"])
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


def test_init_logging_uses_daily_rotation_for_all_log_streams(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    audit_logger = get_audit_logger()
    task_logger = get_task_logger()

    handlers = [logger.handlers[0], audit_logger.handlers[0], task_logger.handlers[0]]
    for handler in handlers:
        assert isinstance(handler, TimedRotatingFileHandler)
        assert handler.when == "MIDNIGHT"
        assert handler.backupCount == 7


def test_audit_and_task_loggers_write_jsonl(tmp_path: Path) -> None:
    init_logging(tmp_path)
    audit_logger = get_audit_logger()
    task_logger = get_task_logger()

    audit_logger.info("audit bootstrap event")
    task_logger.info("task bootstrap event")
    for logger in (audit_logger, task_logger):
        for handler in logger.handlers:
            handler.flush()

    audit_entries = _read_log_entries(tmp_path / "audit.jsonl")
    task_entries = _read_log_entries(tmp_path / "task.jsonl")
    assert audit_entries[0]["message"] == "audit bootstrap event"
    assert task_entries[0]["message"] == "task bootstrap event"


def test_assignment_values_with_commas_semicolons_spaces_are_redacted(tmp_path: Path) -> None:
    logger = init_logging(tmp_path)
    log_file = tmp_path / "app.log"

    logger.info("password=abc,123 token='abc;123' secret=\"hello world\"")
    for handler in logger.handlers:
        handler.flush()

    content = _read_log(log_file)
    assert "abc,123" not in content
    assert "abc;123" not in content
    assert "hello world" not in content
    assert "[REDACTED]" in content
