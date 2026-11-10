from __future__ import annotations

import time
from collections.abc import Sequence

from app.modules.ai.application.ports.llm import LLMPort
from app.modules.chat.application.answer_parser import (
    InvalidLLMResponse,
    normalize_used_sources,
    parse_llm_answer,
)
from app.modules.chat.application.context_formatter import (
    ContextFormatterPort,
    VerboseContextFormatter,
)
from app.modules.chat.application.dto.chat import (
    INSUFFICIENT_ANSWER,
    ChatAnswer,
    ChatImage,
    ChatTurn,
    Source,
)
from app.modules.chat.application.ports.conversations import ConversationRepositoryPort
from app.modules.chat.application.prompt_builder import PromptBuilder
from app.modules.chat.application.usage import UsageTracker
from app.modules.documents.application.ports.document_repository import (
    DocumentRepositoryPort,
)
from app.modules.retrieval.application.dto.retrieval import RetrievalResult, RetrievedChunk
from app.modules.retrieval.application.ports.context_retriever import (
    ContextRetrieverPort,
)
from app.shared.errors import AppError, BadRequestError, LLMNotConfiguredError
from app.shared.identifiers import require_safe_id
from app.shared.logging import get_logger

logger = get_logger(__name__)


class AskQuestionUseCase:
    """Rewrite, retrieve, answer defensively and filter citations/images."""

    def __init__(
        self,
        retrieval: ContextRetrieverPort,
        llm: LLMPort | None,
        documents: DocumentRepositoryPort,
        conversations: ConversationRepositoryPort,
        prompt_builder: PromptBuilder,
        *,
        history_turns: int,
        min_score: float,
        context_formatter: ContextFormatterPort | None = None,
    ) -> None:
        if history_turns < 1:
            raise ValueError("history_turns must be >= 1")
        self._retrieval = retrieval
        self._llm = llm
        self._documents = documents
        self._conversations = conversations
        self._prompt_builder = prompt_builder
        self._context_formatter = context_formatter or VerboseContextFormatter()
        self._history_turns = history_turns
        self._min_score = min_score

    async def execute(
        self,
        query: str,
        history: Sequence[ChatTurn] | None = None,
        doc_id: str | None = None,
        *,
        conversation_id: str | None = None,
        temperature: float | None = None,
        selection_mode: str | None = None,
    ) -> ChatAnswer:
        started = time.perf_counter()
        usage = UsageTracker()
        normalized_query = query.strip()
        if not normalized_query:
            raise BadRequestError("query must not be blank")

        conversation_key = conversation_id.strip() if conversation_id else None
        if conversation_key:
            require_safe_id(conversation_key, kind="conversation id")

        message_limit = self._history_turns * 2
        effective_history = list(history or [])[-message_limit:]
        if conversation_key:
            try:
                stored = await self._conversations.get_recent(
                    conversation_key,
                    message_limit,
                )
            except AppError:
                logger.warning("chat.history_load_failed", conversation_id=conversation_key)
                stored = []
            if stored:
                effective_history = stored

        standalone_query = await self._rewrite(
            normalized_query,
            effective_history,
            usage,
            temperature=temperature,
        )
        retrieval = await self._retrieval.execute(
            standalone_query,
            doc_id=doc_id,
            selection_mode=selection_mode,
        )
        selection = retrieval.debug.selection
        if selection is not None and selection.decision == "REJECT":
            usage.chunks_retrieved = len(retrieval.debug.retrieved)
            return await self._finish(
                normalized_query,
                INSUFFICIENT_ANSWER,
                False,
                (),
                (),
                retrieval,
                conversation_key,
                usage,
                started,
            )
        document_names = await self._document_names(retrieval.chunks)
        context = self._context_formatter.format(
            retrieval.chunks,
            document_names=document_names,
        )
        usage.observe_retrieval(retrieval.chunks, context=context)
        usage.chunks_retrieved = len(retrieval.debug.retrieved)

        if (selection is None or selection.mode == "static") and (
            retrieval.top_score < self._min_score
        ):
            return await self._finish(
                normalized_query,
                INSUFFICIENT_ANSWER,
                False,
                (),
                (),
                retrieval,
                conversation_key,
                usage,
                started,
            )

        llm = self._require_llm()
        prompt_parts = self._prompt_builder.build_answer_parts(
            normalized_query,
            effective_history,
            context,
        )
        answer_prompt = prompt_parts.text
        system = self._prompt_builder.system_prompt()
        usage.record_prompt_breakdown(system=system, parts=prompt_parts)
        usage.mark_context_sent(retrieval.chunks)
        first_text = ""
        try:
            first = await llm.generate(
                answer_prompt,
                system=system,
                temperature=temperature,
            )
            usage.record_call(answer_prompt, system, first)
            first_text = first.text
            payload = parse_llm_answer(first.text)
        except InvalidLLMResponse:
            repair_prompt = self._prompt_builder.build_repair_prompt(
                answer_prompt,
                first_text,
            )
            try:
                repaired = await llm.generate(
                    repair_prompt,
                    system=system,
                    temperature=temperature,
                )
                usage.record_call(repair_prompt, system, repaired)
                payload = parse_llm_answer(repaired.text)
            except (InvalidLLMResponse, AppError):
                logger.warning("chat.invalid_json_fallback")
                return await self._finish(
                    normalized_query,
                    INSUFFICIENT_ANSWER,
                    False,
                    (),
                    (),
                    retrieval,
                    conversation_key,
                    usage,
                    started,
                )

        cited = set(normalize_used_sources(payload.used_sources))
        cited.intersection_update(range(1, len(retrieval.chunks) + 1))
        if payload.sufficient and not cited:
            logger.warning("chat.uncited_answer_fallback")
            return await self._finish(
                normalized_query,
                INSUFFICIENT_ANSWER,
                False,
                (),
                (),
                retrieval,
                conversation_key,
                usage,
                started,
            )

        sources = await self._sources(retrieval.chunks, cited, document_names)
        images = tuple(
            ChatImage(url=image.url, page=image.page, bbox=image.bbox)
            for image in retrieval.images
            if cited.intersection(image.source_indexes)
        )
        return await self._finish(
            normalized_query,
            payload.answer.strip(),
            payload.sufficient,
            sources,
            images,
            retrieval,
            conversation_key,
            usage,
            started,
        )

    async def _rewrite(
        self,
        query: str,
        history: Sequence[ChatTurn],
        usage: UsageTracker,
        *,
        temperature: float | None = None,
    ) -> str:
        if not history or self._llm is None:
            return query
        prompt = self._prompt_builder.build_rewrite_prompt(query, history)
        system = self._prompt_builder.rewrite_system()
        try:
            result = await self._llm.generate(
                prompt,
                system=system,
                temperature=temperature,
            )
            usage.record_call(prompt, system, result)
        except AppError:
            logger.warning("chat.rewrite_failed")
            return query
        rewritten = " ".join(result.text.strip().strip("\"'").split())
        return rewritten or query

    async def _document_names(
        self,
        chunks: Sequence[RetrievedChunk],
    ) -> dict[str, str]:
        names: dict[str, str] = {}
        for document_id in {item.chunk.doc_id for item in chunks}:
            try:
                document = await self._documents.get(document_id)
                names[document_id] = document.filename
            except AppError:
                names[document_id] = document_id
        return names

    async def _sources(
        self,
        chunks: Sequence[RetrievedChunk],
        cited: set[int],
        document_names: dict[str, str],
    ) -> tuple[Source, ...]:
        selected = [(index, item) for index, item in enumerate(chunks, start=1) if index in cited]
        return tuple(
            Source(
                file=document_names.get(item.chunk.doc_id, item.chunk.doc_id),
                page=item.chunk.page,
                bbox=item.chunk.bbox,
                section_path=item.chunk.section_path,
            )
            for _, item in selected
        )

    async def _finish(
        self,
        query: str,
        answer: str,
        sufficient: bool,
        sources: tuple[Source, ...],
        images: tuple[ChatImage, ...],
        retrieval: RetrievalResult,
        conversation_id: str | None,
        usage: UsageTracker,
        started: float,
    ) -> ChatAnswer:
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        response = ChatAnswer(
            answer=answer,
            sufficient=sufficient,
            sources=sources,
            images=images,
            usage=usage.to_dto(latency_ms=latency_ms),
            debug=retrieval.debug.with_sent(usage.sent_chunk_ids),
        )
        if conversation_id:
            try:
                await self._conversations.append(
                    conversation_id,
                    (
                        ChatTurn(role="user", content=query),
                        ChatTurn(role="assistant", content=response.answer),
                    ),
                    max_messages=self._history_turns * 2,
                )
            except AppError:
                logger.warning("chat.history_append_failed", conversation_id=conversation_id)
        return response

    def _require_llm(self) -> LLMPort:
        if self._llm is None:
            raise LLMNotConfiguredError("LLM is not configured for chat")
        return self._llm
