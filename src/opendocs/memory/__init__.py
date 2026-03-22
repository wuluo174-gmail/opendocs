"""Memory subsystem — lifecycle, policy, and service."""

from .policy import default_ttl, is_expired, m2_gate, should_upgrade_to_m2
from .service import MemoryService

__all__ = [
    "MemoryService",
    "default_ttl",
    "is_expired",
    "m2_gate",
    "should_upgrade_to_m2",
]
