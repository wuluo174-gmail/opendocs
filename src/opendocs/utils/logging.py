"""Logging setup helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import traceback


_ASSIGNMENT_PATTERN = re.compile(
    r"""(?ix)
    (?P<key_quote>["']?)
    (?P<key>api[_-]?key|token|password|secret)
    (?P=key_quote)
    \s*(?P<separator>[:=])\s*
    (?P<value_quote>["']?)
    (?P<value>[^\s,;}'"]+)
    (?P=value_quote)
    """
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/=]+")
_SK_PATTERN = re.compile(r"\bsk-[a-zA-Z0-9\-_]{8,}\b")


def _replace_assignment(match: re.Match[str]) -> str:
    key_quote = match.group("key_quote") or ""
    key = match.group("key")
    separator = match.group("separator")
    value_quote = match.group("value_quote") or ""
    return f"{key_quote}{key}{key_quote}{separator}{value_quote}[REDACTED]{value_quote}"


def _sanitize_text(text: str) -> str:
    sanitized = _ASSIGNMENT_PATTERN.sub(_replace_assignment, text)
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    sanitized = _SK_PATTERN.sub("sk-[REDACTED]", sanitized)
    return sanitized


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


def init_logging(log_dir: str | Path) -> logging.Logger:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("opendocs")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    file_handler = RotatingFileHandler(
        path / "app.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactFilter())
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger
