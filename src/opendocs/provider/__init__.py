"""LLM provider abstraction layer."""

from opendocs.provider.base import GenerateRequest, GenerateResponse
from opendocs.provider.mock import MockProvider

__all__ = ["GenerateRequest", "GenerateResponse", "MockProvider"]
