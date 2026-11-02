from __future__ import annotations

from typing import Protocol

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema


class LLMPort(Protocol):
    """Provider-agnostic text generation port."""

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult: ...
