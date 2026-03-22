"""LLM provider abstraction layer."""

from opendocs.provider.base import (
    ALLOWED_KINDS,
    ExternalCallRecord,
    GenerateRequest,
    GenerateResponse,
    LLMProvider,
    PrivacyMode,
    ProviderKind,
)
from opendocs.provider.mock import MockProvider

__all__ = [
    "ALLOWED_KINDS",
    "ExternalCallRecord",
    "GenerateRequest",
    "GenerateResponse",
    "LLMProvider",
    "MockProvider",
    "PrivacyMode",
    "ProviderKind",
]
