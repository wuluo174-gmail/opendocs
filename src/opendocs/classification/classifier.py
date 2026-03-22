"""S6-T01: Rule-based document classifier."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from opendocs.classification.models import ClassificationResult
from opendocs.domain.models import DocumentModel

_DATE_RE = re.compile(r"\d{4}[-_]?\d{2}[-_]?\d{2}")


class RuleBasedClassifier:
    """Classify documents using path patterns, dates, and existing metadata."""

    def classify(self, docs: list[DocumentModel]) -> list[ClassificationResult]:
        return [self._classify_one(doc) for doc in docs]

    def _classify_one(self, doc: DocumentModel) -> ClassificationResult:
        if doc.category:
            return ClassificationResult(
                doc_id=doc.doc_id,
                current_path=doc.path,
                category=doc.category,
                tags=list(doc.tags_json or []),
                confidence=1.0,
            )

        category = self._category_from_path(doc.relative_directory_path)
        tags = list(doc.tags_json or [])
        confidence = 0.8 if category else 0.5

        date_tag = self._date_from_filename(doc.path)
        if date_tag:
            tags.append(date_tag)
            confidence = max(confidence, 0.7)

        tags.append(doc.file_type)

        return ClassificationResult(
            doc_id=doc.doc_id,
            current_path=doc.path,
            category=category,
            tags=tags,
            confidence=confidence,
        )

    def _category_from_path(self, relative_dir: str) -> str | None:
        parts = PurePosixPath(relative_dir).parts
        if not parts or parts[0] == ".":
            return None
        return parts[0]

    def _date_from_filename(self, path: str) -> str | None:
        name = PurePosixPath(path).stem
        match = _DATE_RE.search(name)
        if match:
            raw = match.group().replace("_", "-")
            if len(raw) == 8:
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            return raw
        return None
