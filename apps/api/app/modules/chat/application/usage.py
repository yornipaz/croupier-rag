from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.modules.ai.application.dto.llm import LLMResult
from app.modules.chat.application.dto.chat import ChatUsage
from app.modules.chat.application.prompt_builder import AnswerPromptParts
from app.modules.retrieval.application.dto.retrieval import RetrievedChunk
from app.shared.tokens import count_tokens


@dataclass(slots=True)
class UsageTracker:
    """Accumulate retrieval, prompt breakdown and real LLM usage per request."""

    chunks_retrieved: int = 0
    chunks_sent: int = 0
    system_tokens: int = 0
    history_tokens: int = 0
    context_tokens: int = 0
    question_tokens: int = 0
    prompt_template_tokens: int = 0
    prompt_estimated_tokens: int = 0
    provider_prompt_tokens: int = 0
    provider_completion_tokens: int = 0
    estimated_prompt_tokens: int = 0
    estimated_completion_tokens: int = 0
    provider_prompt_calls: int = 0
    provider_completion_calls: int = 0
    llm_calls: int = 0
    sent_chunk_ids: set[str] = field(default_factory=set)

    def observe_retrieval(
        self,
        chunks: Sequence[RetrievedChunk],
        *,
        context: str,
    ) -> None:
        self.chunks_retrieved = len(chunks)
        self.context_tokens = count_tokens(context)

    def mark_context_sent(self, chunks: Sequence[RetrievedChunk]) -> None:
        self.chunks_sent = len(chunks)
        self.sent_chunk_ids = {item.chunk.id for item in chunks}

    def record_prompt_breakdown(
        self,
        *,
        system: str,
        parts: AnswerPromptParts,
    ) -> None:
        """Estimate every disjoint piece of the answer prompt with one counter."""
        self.system_tokens = count_tokens(system)
        self.history_tokens = count_tokens(parts.history)
        self.context_tokens = count_tokens(parts.context)
        self.question_tokens = count_tokens(parts.question)
        self.prompt_estimated_tokens = count_tokens(
            f"{system}\n\n{parts.text}" if system else parts.text
        )
        components = (
            self.system_tokens + self.history_tokens + self.context_tokens + self.question_tokens
        )
        self.prompt_template_tokens = max(0, self.prompt_estimated_tokens - components)

    def record_call(
        self,
        prompt: str,
        system: str | None,
        result: LLMResult,
    ) -> None:
        """Record one LLM call, preferring provider usage over estimates."""
        self.llm_calls += 1
        usage = result.usage or {}
        prompt_tokens = usage.get("input_tokens")
        completion_tokens = usage.get("output_tokens")
        if prompt_tokens is None:
            estimated_prompt = f"{system}\n\n{prompt}" if system else prompt
            self.estimated_prompt_tokens += count_tokens(estimated_prompt)
        else:
            self.provider_prompt_tokens += int(prompt_tokens)
            self.provider_prompt_calls += 1
        if completion_tokens is None:
            self.estimated_completion_tokens += count_tokens(result.text)
        else:
            self.provider_completion_tokens += int(completion_tokens)
            self.provider_completion_calls += 1

    def to_dto(self, *, latency_ms: int) -> ChatUsage:
        prompt_source: Literal["provider", "estimated"] = (
            "provider"
            if self.llm_calls > 0 and self.provider_prompt_calls == self.llm_calls
            else "estimated"
        )
        completion_source: Literal["provider", "estimated"] = (
            "provider"
            if self.llm_calls > 0 and self.provider_completion_calls == self.llm_calls
            else "estimated"
        )
        return ChatUsage(
            chunks_retrieved=self.chunks_retrieved,
            chunks_sent=self.chunks_sent,
            system_tokens=self.system_tokens,
            history_tokens=self.history_tokens,
            context_tokens=self.context_tokens,
            question_tokens=self.question_tokens,
            prompt_template_tokens=self.prompt_template_tokens,
            prompt_estimated_tokens=self.prompt_estimated_tokens,
            prompt_tokens=self.provider_prompt_tokens + self.estimated_prompt_tokens,
            completion_tokens=(self.provider_completion_tokens + self.estimated_completion_tokens),
            prompt_source=prompt_source,
            completion_source=completion_source,
            breakdown_source="estimated",
            llm_calls=self.llm_calls,
            latency_ms=latency_ms,
            llm_called=self.llm_calls > 0,
        )
