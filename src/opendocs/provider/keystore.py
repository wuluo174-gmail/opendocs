"""Keyring-backed credential store — API keys never touch disk or logs."""

from __future__ import annotations

import logging

import keyring
import keyring.errors

_SERVICE_NAME = "opendocs"
_log = logging.getLogger(__name__)


class KeyStore:
    """Thin wrapper around OS keyring for provider API keys."""

    def get(self, provider_name: str) -> str | None:
        """Retrieve API key. Returns None if not stored."""
        return keyring.get_password(_SERVICE_NAME, provider_name)

    def set(self, provider_name: str, api_key: str) -> None:
        keyring.set_password(_SERVICE_NAME, provider_name, api_key)
        _log.info("API key stored for provider=%s", provider_name)

    def delete(self, provider_name: str) -> None:
        try:
            keyring.delete_password(_SERVICE_NAME, provider_name)
        except keyring.errors.PasswordDeleteError:
            pass

    def has(self, provider_name: str) -> bool:
        return self.get(provider_name) is not None


def mask_key(key: str) -> str:
    """Redact API key for display: 'sk-****abcd'. Never log raw keys."""
    if len(key) <= 8:
        return "****"
    return key[:3] + "****" + key[-4:]
