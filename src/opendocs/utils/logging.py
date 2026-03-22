"""Logging setup helpers."""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

APP_LOGGER_NAME = "opendocs"
AUDIT_LOGGER_NAME = "opendocs.audit"
TASK_LOGGER_NAME = "opendocs.task"

_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    (?P<key_quote>["']?)
    (?P<key>api[_-]?key|token|password|secret)
    (?P=key_quote)
    \s*(?P<separator>[:=])\s*
    (?:
        (?P<quoted_value_quote>["'])
        (?P<quoted_value>.*?)
        (?P=quoted_value_quote)
      |
        (?P<unquoted_value>[^\s]+)
    )
    """
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/=]+")
_SK_PATTERN = re.compile(r"\bsk-[a-zA-Z0-9\-_]{8,}\b")


def _replace_assignment(match: re.Match[str]) -> str:
    key_quote = match.group("key_quote") or ""
    key = match.group("key")
    separator = match.group("separator")
    value_quote = match.group("quoted_value_quote") or ""
    return f"{key_quote}{key}{key_quote}{separator}{value_quote}[REDACTED]{value_quote}"


def _sanitize_text(text: str) -> str:
    sanitized = _ASSIGNMENT_PATTERN.sub(_replace_assignment, text)
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    sanitized = _SK_PATTERN.sub("sk-[REDACTED]", sanitized)
    return sanitized


def _sanitize_structured(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_structured(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_structured(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_structured(item) for item in value)
    if isinstance(value, set):
        return [_sanitize_structured(item) for item in sorted(value, key=repr)]
    return value


class RedactFilter(logging.Filter):
    """Best-effort sensitive field redaction for plain log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted_message = _sanitize_text(message)
        if redacted_message != message:
            record.msg = redacted_message
            record.args = ()

        if record.exc_info:
            traceback_text = "".join(traceback.format_exception(*record.exc_info))
            redacted_traceback = _sanitize_text(traceback_text)
            if redacted_traceback != traceback_text:
                record.exc_info = None
                record.exc_text = redacted_traceback
        return True


class AuditJsonFormatter(logging.Formatter):
    """Audit-specific formatter: promotes record.audit_data fields to top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        audit_data = getattr(record, "audit_data", None)
        if isinstance(audit_data, dict):
            payload.update(_sanitize_structured(audit_data))
        else:
            payload["message"] = _sanitize_text(record.getMessage())
        return json.dumps(_sanitize_structured(payload), ensure_ascii=False)


class RaisingAuditHandler(TimedRotatingFileHandler):
    """Audit handler that propagates I/O exceptions instead of swallowing them."""

    def handleError(self, record: logging.LogRecord) -> None:
        _, exc, _ = sys.exc_info()
        if exc is not None:
            raise exc


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(_sanitize_structured(payload), ensure_ascii=False)


def _build_handler(log_path: Path) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactFilter())
    return handler


def _build_audit_handler(log_path: Path) -> RaisingAuditHandler:
    handler = RaisingAuditHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=True,
    )
    handler.setFormatter(AuditJsonFormatter())
    handler.addFilter(RedactFilter())
    return handler


def _reset_logger_with_handler(name: str, handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _reset_logger(name: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.addHandler(_build_handler(log_path))
    logger.propagate = False
    return logger


def get_app_logger() -> logging.Logger:
    return logging.getLogger(APP_LOGGER_NAME)


def get_audit_logger() -> logging.Logger:
    return logging.getLogger(AUDIT_LOGGER_NAME)


def get_task_logger() -> logging.Logger:
    return logging.getLogger(TASK_LOGGER_NAME)


def init_logging(log_dir: str | Path) -> logging.Logger:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    app_logger = _reset_logger(APP_LOGGER_NAME, path / "app.log")
    # Audit logger uses RaisingAuditHandler + AuditJsonFormatter
    _reset_logger_with_handler(AUDIT_LOGGER_NAME, _build_audit_handler(path / "audit.jsonl"))
    _reset_logger(TASK_LOGGER_NAME, path / "task.jsonl")
    return app_logger
