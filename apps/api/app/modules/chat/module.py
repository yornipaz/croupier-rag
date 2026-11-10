from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from redis.asyncio import Redis

from app.config.settings import Settings
from app.modules.ai.application.ports.llm import LLMPort
from app.modules.chat.application.context_formatter import (
    CompactContextFormatter,
    ContextFormatterPort,
    VerboseContextFormatter,
)
from app.modules.chat.application.prompt_builder import PromptBuilder
from app.modules.chat.application.use_cases.ask_question import AskQuestionUseCase
from app.modules.chat.infrastructure.conversations import RedisConversationRepository
from app.modules.chat.presentation.router import router
from app.modules.documents.application.ports.document_repository import (
    DocumentRepositoryPort,
)
from app.modules.retrieval.application.ports.context_retriever import (
    ContextRetrieverPort,
)

__all__ = [
    "ChatServices",
    "build_chat_module",
    "build_chat_router",
    "build_chat_services",
    "router",
]


@dataclass(frozen=True, slots=True)
class ChatServices:
    ask: AskQuestionUseCase


def build_chat_services(
    settings: Settings,
    *,
    redis: Redis,
    retrieval: ContextRetrieverPort,
    llm: LLMPort | None,
    documents: DocumentRepositoryPort,
) -> ChatServices:
    conversations = RedisConversationRepository(
        redis,
        prefix=settings.conversation_prefix,
        ttl_seconds=settings.conversation_ttl_seconds,
    )
    return ChatServices(
        ask=AskQuestionUseCase(
            retrieval,
            llm,
            documents,
            conversations,
            PromptBuilder(),
            history_turns=settings.chat_history_turns,
            min_score=settings.retrieval_min_score,
            context_formatter=_context_formatter(settings),
        )
    )


def _context_formatter(settings: Settings) -> ContextFormatterPort:
    if settings.context_format == "compact":
        return CompactContextFormatter()
    return VerboseContextFormatter()


def build_chat_router(settings: Settings) -> APIRouter:
    _ = settings
    return router


def build_chat_module(settings: Settings) -> APIRouter:
    return build_chat_router(settings)
