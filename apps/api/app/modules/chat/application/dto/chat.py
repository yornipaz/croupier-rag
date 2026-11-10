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

    ``contextTokens`` always describes the retrieved context. ``promptTokens``
    and ``completionTokens`` include every LLM call made while answering
    (rewrite, answer and optional repair); they come from provider metadata
    when available and are estimated otherwise.
    """

    chunks_retrieved: int
    chunks_sent: int
    context_tokens: int
    prompt_tokens: int
    completion_tokens: int
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
