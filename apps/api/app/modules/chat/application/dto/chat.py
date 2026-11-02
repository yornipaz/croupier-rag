from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.retrieval.application.dto.retrieval import RetrievalDebug
from app.shared.chunks import BBox

ChatRole = Literal["user", "assistant"]
INSUFFICIENT_ANSWER = (
    "No tengo información suficiente en los documentos para responder esto."
)


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
class ChatAnswer:
    answer: str
    sufficient: bool
    sources: tuple[Source, ...]
    images: tuple[ChatImage, ...]
    debug: RetrievalDebug | None = None
