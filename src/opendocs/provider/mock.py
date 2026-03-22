"""Deterministic mock LLM provider for testing — zero network calls."""

from __future__ import annotations

import re

from opendocs.provider.base import GenerateRequest, GenerateResponse, ProviderKind


class MockProvider:
    """Extract evidence blocks from prompt and return formatted answer.

    Deterministic: same input always produces same output.
    """

    kind = ProviderKind.LOCAL
    MODEL_NAME = "mock-deterministic-v1"

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        evidence_blocks = self._extract_evidence(request.user_prompt)
        if not evidence_blocks:
            text = "当前证据不足以可靠回答该问题。"
        else:
            lines = []
            for chunk_id, snippet in evidence_blocks:
                lines.append(f"根据文档记载：{snippet} [CIT:{chunk_id}]")
            text = "\n\n".join(lines)
        return GenerateResponse(
            text=text,
            model=self.MODEL_NAME,
            usage={
                "prompt_tokens": len(request.user_prompt),
                "completion_tokens": len(text),
            },
        )

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _extract_evidence(prompt: str) -> list[tuple[str, str]]:
        """Parse evidence blocks injected by prompt templates.

        Expected format per block:
            [EVIDENCE chunk_id=<id>]
            <text>
            [/EVIDENCE]
        """
        pattern = re.compile(
            r"\[EVIDENCE chunk_id=([^\]]+)\]\s*\n(.*?)\n\s*\[/EVIDENCE\]",
            re.DOTALL,
        )
        return [(m.group(1), m.group(2).strip()[:200]) for m in pattern.finditer(prompt)]
