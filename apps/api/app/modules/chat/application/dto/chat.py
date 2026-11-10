from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.retrieval.application.dto.retrieval import RetrievalDebug
from app.shared.chunks import BBox

ChatRole = Literal["user", "assistant"]
INSUFFICIENT_ANSWER = "No tengo información suficiente en los documentos para responder esto."


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class Source:
    file: str
    page: int
    bbox: BBox
    section_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChatImage:
    url: str
    page: int
    bbox: BBox


@dataclass(frozen=True, slots=True)
class ChatUsage:
    """Observable cost/latency of one ``/chat/ask`` request.

    The ``*Tokens`` breakdown is always estimated with the repo token counter
    and refers to the answer prompt (system + history + context + question +
    template). ``promptTokens``/``completionTokens`` aggregate every LLM call
    and are labelled with their source: provider metadata when available,
    otherwise the same estimator.
    """

    chunks_retrieved: int
    chunks_sent: int
    system_tokens: int
    history_tokens: int
    context_tokens: int
    question_tokens: int
    prompt_template_tokens: int
    prompt_estimated_tokens: int
    prompt_tokens: int
    completion_tokens: int
    prompt_source: Literal["provider", "estimated"]
    completion_source: Literal["provider", "estimated"]
    breakdown_source: Literal["estimated"]
    llm_calls: int
    latency_ms: int
    llm_called: bool


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    answer: str
    sufficient: bool
    sources: tuple[Source, ...]
    images: tuple[ChatImage, ...]
    usage: ChatUsage
    debug: RetrievalDebug | None = None
