"""Encoding detection utilities for text-based parsers.

Tries UTF-8 first; then uses the locked-baseline charset-normalizer detector
before falling back to explicit CJK encodings.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Common CJK legacy encodings to probe when auto-detection is uncertain.
_CJK_FALLBACK_ENCODINGS = ("gb18030", "gbk", "big5", "euc-kr", "shift_jis")


def read_text_with_fallback(file_path: Path) -> str:
    """Read *file_path* as text, detecting encoding when UTF-8 fails.

    Strategy:
    1. Try UTF-8 (strict) — covers the vast majority of modern files.
    2. On ``UnicodeDecodeError``, use *charset-normalizer* from the locked baseline.
    3. If auto-detection is unavailable because the environment is broken, or
       confidence is low, probe common
       CJK encodings.
    4. Last resort: ``utf-8`` with ``errors="replace"``.
    """
    raw = file_path.read_bytes()
    if not raw:
        return ""

    # Fast path: UTF-8
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    # Auto-detect via charset-normalizer from the locked runtime baseline.
    # Keep the ImportError fallback as a defensive guard for broken envs.
    detected = _detect_with_charset_normalizer(raw)
    if detected is not None:
        return detected

    # Probe common CJK encodings explicitly
    for enc in _CJK_FALLBACK_ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue

    # Last resort
    logger.warning("Could not detect encoding for %s, using utf-8 replace", file_path)
    return raw.decode("utf-8", errors="replace")


def _detect_with_charset_normalizer(raw: bytes) -> str | None:
    """Return decoded text if charset-normalizer is confident, else None."""
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        logger.debug("charset-normalizer not installed, skipping auto-detection")
        return None

    results = from_bytes(raw)
    best = results.best()
    if best is None:
        return None
    # Only trust when coherence is reasonable (> 0.1)
    if best.coherence > 0.1:
        logger.info("Detected encoding %s (coherence=%.2f)", best.encoding, best.coherence)
        return str(best)
    return None
