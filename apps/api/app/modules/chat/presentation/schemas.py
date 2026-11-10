from __future__ import annotations

from pydantic import Field

from app.modules.chat.application.dto.chat import ChatAnswer, ChatRole, ChatTurn
from app.modules.retrieval.application.dto.retrieval import RetrievalDebug
from app.shared.chunks import BBox
from app.shared.schemas import CamelModel


class ChatTurnSchema(CamelModel):
    role: ChatRole
    content: str = Field(min_length=1)


class ChatAskRequest(CamelModel):
    query: str = Field(min_length=1)
    history: list[ChatTurnSchema] = Field(default_factory=list)
    doc_id: str | None = None
    conversation_id: str | None = None


class SourceSchema(CamelModel):
    file: str
    page: int
    bbox: BBox
    section_path: list[str]


class ChatImageSchema(CamelModel):
    url: str
    page: int
    bbox: BBox


class ChatDebugHitSchema(CamelModel):
    chunk_id: str
    doc_id: str
    page: int
    section_path: list[str]
    kind: str
    rrf_score: float
    relevance_score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None


class ChatDebugSchema(CamelModel):
    retrieved: list[ChatDebugHitSchema]

    @classmethod
    def from_dto(cls, debug: RetrievalDebug) -> ChatDebugSchema:
        return cls(
            retrieved=[
                ChatDebugHitSchema(
                    chunk_id=item.chunk_id,
                    doc_id=item.doc_id,
                    page=item.page,
                    section_path=list(item.section_path),
                    kind=item.kind,
                    rrf_score=item.rrf_score,
                    relevance_score=item.relevance_score,
                    dense_rank=item.dense_rank,
                    sparse_rank=item.sparse_rank,
                    dense_score=item.dense_score,
                    sparse_score=item.sparse_score,
                )
                for item in debug.retrieved
            ]
        )


class ChatUsageSchema(CamelModel):
    chunks_retrieved: int
    chunks_sent: int
    context_tokens: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    llm_called: bool


class ChatResponse(CamelModel):
    answer: str
    sufficient: bool
    sources: list[SourceSchema]
    images: list[ChatImageSchema]
    usage: ChatUsageSchema
    debug: ChatDebugSchema | None = None

    @classmethod
    def from_answer(
        cls,
        answer: ChatAnswer,
        *,
        include_debug: bool,
    ) -> ChatResponse:
        return cls(
            answer=answer.answer,
            sufficient=answer.sufficient,
            sources=[
                SourceSchema(
                    file=source.file,
                    page=source.page,
                    bbox=source.bbox,
                    section_path=list(source.section_path),
                )
                for source in answer.sources
            ],
            images=[
                ChatImageSchema(url=image.url, page=image.page, bbox=image.bbox)
                for image in answer.images
            ],
            usage=ChatUsageSchema(
                chunks_retrieved=answer.usage.chunks_retrieved,
                chunks_sent=answer.usage.chunks_sent,
                context_tokens=answer.usage.context_tokens,
                prompt_tokens=answer.usage.prompt_tokens,
                completion_tokens=answer.usage.completion_tokens,
                latency_ms=answer.usage.latency_ms,
                llm_called=answer.usage.llm_called,
            ),
            debug=ChatDebugSchema.from_dto(answer.debug)
            if include_debug and answer.debug is not None
            else None,
        )


def to_chat_turns(history: list[ChatTurnSchema]) -> list[ChatTurn]:
    return [ChatTurn(role=turn.role, content=turn.content) for turn in history]
