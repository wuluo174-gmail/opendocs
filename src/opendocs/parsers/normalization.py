"""Text normalization utilities for parsed documents.

Applied after parsing and before chunking to ensure consistent text
representation across document types.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Apply standard normalization to extracted text.

    Steps:
    1. Unicode NFC normalization (compose characters canonically)
    2. Normalize full-width ASCII characters to half-width equivalents
    3. Collapse runs of spaces (preserving paragraph breaks and tabs)
    """
    # NFC normalization – important for CJK text
    text = unicodedata.normalize("NFC", text)

    # Full-width ASCII → half-width (U+FF01..U+FF5E → U+0021..U+007E)
    text = _fullwidth_to_halfwidth(text)

    # Collapse space-like runs within lines while preserving tabs. Tabs can
    # carry layout meaning in DOCX-derived text and should remain truthful to
    # the parser output instead of being silently rewritten as plain spaces.
    text = re.sub(r"[ \f\v\r]+", " ", text)

    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    return text


def _fullwidth_to_halfwidth(text: str) -> str:
    """Convert full-width *letters and digits* to their half-width equivalents.

    Only converts:
    - Full-width digits 0-9 (U+FF10..U+FF19)
    - Full-width uppercase A-Z (U+FF21..U+FF3A)
    - Full-width lowercase a-z (U+FF41..U+FF5A)
    - Full-width space U+3000

    Full-width punctuation (，！？（）etc.) is intentionally preserved
    because Chinese text conventionally uses full-width punctuation.
    """
    result: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (
            0xFF10 <= cp <= 0xFF19  # ０-９ → 0-9
            or 0xFF21 <= cp <= 0xFF3A  # Ａ-Ｚ → A-Z
            or 0xFF41 <= cp <= 0xFF5A
        ):  # ａ-ｚ → a-z
            result.append(chr(cp - 0xFEE0))
        elif cp == 0x3000:  # full-width space
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result)
