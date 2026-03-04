"""OpenDocs exception hierarchy."""

from __future__ import annotations


class OpenDocsError(Exception):
    """Base exception for all OpenDocs errors."""


class ConfigError(OpenDocsError):
    """Raised when configuration cannot be loaded or validated."""


class BootstrapError(OpenDocsError):
    """Raised when bootstrap/setup actions fail."""
