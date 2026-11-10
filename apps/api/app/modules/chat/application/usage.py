from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.ai.application.dto.llm import LLMResult
from app.modules.chat.application.dto.chat import ChatUsage
from app.modules.retrieval.application.dto.retrieval import RetrievedChunk
from app.shared.tokens import count_tokens


@dataclass(slots=True)
class UsageTracker:
    """Accumulate retrieval size and LLM usage during one chat request."""

    chunks_retrieved: int = 0
    context_tokens: int = 0
    chunks_sent: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0

    def observe_chunks(self, chunks: Sequence[RetrievedChunk]) -> None:
        context = "\n\n".join(item.chunk.text for item in chunks)
        self.chunks_retrieved = len(chunks)
        self.context_tokens = count_tokens(context)

    def mark_context_sent(self, chunks: Sequence[RetrievedChunk]) -> None:
        self.chunks_sent = len(chunks)

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
            prompt_tokens = count_tokens(estimated_prompt)
        if completion_tokens is None:
            completion_tokens = count_tokens(result.text)
        self.prompt_tokens += int(prompt_tokens)
        self.completion_tokens += int(completion_tokens)

    def to_dto(self, *, latency_ms: int) -> ChatUsage:
        return ChatUsage(
            chunks_retrieved=self.chunks_retrieved,
            chunks_sent=self.chunks_sent,
            context_tokens=self.context_tokens,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=latency_ms,
            llm_called=self.llm_calls > 0,
        )
