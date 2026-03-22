"""Backward-compatible re-export. Real implementation in memory/service.py."""


def __getattr__(name: str) -> object:
    if name == "MemoryService":
        from opendocs.memory.service import MemoryService

        return MemoryService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["MemoryService"]
