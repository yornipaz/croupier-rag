from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.chat.application.dto.chat import (
    INSUFFICIENT_ANSWER,
    ChatTurn,
)
from app.modules.chat.application.prompt_builder import PromptBuilder
from app.modules.chat.application.use_cases.ask_question import AskQuestionUseCase
from app.modules.documents.application.dto.document import Document
from app.modules.retrieval.application.dto.retrieval import (
    RetrievalResult,
    SelectionDebug,
)
from tests.modules.chat.helpers import retrieval_result


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def execute(
        self,
        query: str,
        doc_id: str | None = None,
        top_k: int | None = None,
        *,
        selection_mode: str | None = None,
    ) -> RetrievalResult:
        _ = doc_id, top_k, selection_mode
        self.queries.append(query)
        return self.result


class FakeLLM:
    def __init__(
        self,
        responses: Sequence[str],
        usages: Sequence[dict[str, int] | None] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.usages = list(usages or [])
        self.calls = 0
        self.prompts: list[str] = []
        self.systems: list[str | None] = []
        self.temperatures: list[float | None] = []

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
        *,
        temperature: float | None = None,
    ) -> LLMResult:
        _ = response_schema
        self.calls += 1
        self.prompts.append(prompt)
        self.systems.append(system)
        self.temperatures.append(temperature)
        if not self.responses:
            raise AssertionError("LLM should not have been called")
        usage = self.usages.pop(0) if self.usages else None
        return LLMResult(text=self.responses.pop(0), model="fake", usage=usage)


class FakeDocuments:
    def __init__(self) -> None:
        self.documents = {
            "doc-1": _document("doc-1", "manual.pdf"),
            "doc-2": _document("doc-2", "guia.pdf"),
        }

    async def save(self, document: Document) -> None:
        self.documents[document.id] = document

    async def get(self, document_id: str) -> Document:
        return self.documents[document_id]

    async def list_all(self) -> list[Document]:
        return list(self.documents.values())

    async def delete(self, document_id: str) -> None:
        self.documents.pop(document_id, None)


class FakeConversations:
    def __init__(self, stored: list[ChatTurn] | None = None) -> None:
        self.stored = stored or []
        self.appended: list[tuple[str, list[ChatTurn], int]] = []
        self.requested: list[tuple[str, int]] = []

    async def get_recent(self, conversation_id: str, limit: int) -> list[ChatTurn]:
        self.requested.append((conversation_id, limit))
        return self.stored[-limit:]

    async def append(
        self,
        conversation_id: str,
        turns: Sequence[ChatTurn],
        *,
        max_messages: int,
    ) -> None:
        self.appended.append((conversation_id, list(turns), max_messages))


def _document(document_id: str, filename: str) -> Document:
    return Document(
        id=document_id,
        filename=filename,
        content_type="application/pdf",
        size_bytes=10,
        storage_path=f"/data/files/{document_id}.pdf",
        sha256="abc",
        created_at=datetime.now(UTC),
        job_id=f"job-{document_id}",
    )


def _use_case(
    *,
    top_score: float = 0.9,
    responses: Sequence[str] = (),
    usages: Sequence[dict[str, int] | None] | None = None,
    conversations: FakeConversations | None = None,
) -> tuple[AskQuestionUseCase, FakeRetriever, FakeLLM, FakeConversations]:
    retriever = FakeRetriever(retrieval_result(top_score=top_score))
    llm = FakeLLM(responses, usages)
    conversation_repo = conversations or FakeConversations()
    use_case = AskQuestionUseCase(
        retriever,
        llm,
        FakeDocuments(),
        conversation_repo,
        PromptBuilder(),
        history_turns=6,
        min_score=0.3,
    )
    return use_case, retriever, llm, conversation_repo


async def test_no_information_returns_fallback_without_calling_llm() -> None:
    use_case, _, llm, _ = _use_case(top_score=0.1, responses=[])

    answer = await use_case.execute("¿Cuál es el voltaje?", [])

    assert answer.answer == INSUFFICIENT_ANSWER
    assert answer.sufficient is False
    assert answer.sources == ()
    assert answer.images == ()
    assert llm.calls == 0
    assert answer.usage.llm_called is False
    assert answer.usage.completion_tokens == 0
    assert answer.usage.prompt_tokens == 0
    assert answer.usage.chunks_sent == 0
    assert answer.usage.chunks_retrieved == 2
    assert answer.usage.context_tokens > 0
    assert answer.usage.latency_ms >= 0
    assert answer.debug is not None
    assert all(not hit.sent for hit in answer.debug.retrieved)


async def test_valid_answer_filters_sources_and_images_to_cited_sources() -> None:
    use_case, _, llm, _ = _use_case(
        responses=[
            '{"answer":"El modelo A-200 usa 380 V [S2].",'
            '"used_sources":["S2","S99"],"sufficient":true}'
        ]
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-200?", [])

    assert answer.sufficient is True
    assert answer.answer.endswith("[S2].")
    assert len(answer.sources) == 1
    assert answer.sources[0].file == "guia.pdf"
    assert answer.sources[0].page == 2
    assert len(answer.images) == 1
    assert answer.images[0].url.endswith("doc-2/pages/2/crop?bbox=20,230,120,280&highlight=false")
    assert llm.calls == 1
    assert "SOLO" in (llm.systems[0] or "")
    assert "Ignora" in (llm.systems[0] or "")


async def test_valid_answer_records_estimated_usage_without_provider_metadata() -> None:
    use_case, _, _, _ = _use_case(
        responses=[
            '{"answer":"El modelo A-200 usa 380 V [S2].","used_sources":["S2"],"sufficient":true}'
        ]
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-200?", [])

    assert answer.usage.llm_called is True
    assert answer.usage.chunks_retrieved == 2
    assert answer.usage.chunks_sent == 2
    assert answer.usage.context_tokens > 0
    assert answer.usage.prompt_tokens > 0
    assert answer.usage.completion_tokens > 0
    assert answer.usage.latency_ms >= 0
    assert answer.usage.prompt_source == "estimated"
    assert answer.usage.completion_source == "estimated"
    assert answer.usage.system_tokens > 0
    assert answer.usage.history_tokens > 0
    assert answer.usage.question_tokens > 0
    assert answer.usage.prompt_estimated_tokens >= (
        answer.usage.system_tokens
        + answer.usage.history_tokens
        + answer.usage.context_tokens
        + answer.usage.question_tokens
    )
    assert answer.debug is not None
    assert all(hit.sent for hit in answer.debug.retrieved)
    assert {hit.page for hit in answer.debug.retrieved} == {1, 2}


async def test_token_breakdown_partitions_the_answer_prompt() -> None:
    use_case, _, _, _ = _use_case(
        responses=[
            '{"answer":"El modelo A-200 usa 380 V [S2].","used_sources":["S2"],"sufficient":true}'
        ],
        usages=[{"input_tokens": 500, "output_tokens": 7}],
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-200?", [])

    usage = answer.usage
    assert usage.prompt_source == "provider"
    assert usage.completion_source == "provider"
    assert usage.prompt_tokens == 500
    assert usage.prompt_estimated_tokens == (
        usage.system_tokens
        + usage.history_tokens
        + usage.context_tokens
        + usage.question_tokens
        + usage.prompt_template_tokens
    )


async def test_temperature_is_forwarded_to_every_llm_call() -> None:
    history = [ChatTurn(role="user", content="Háblame del A-100.")]
    use_case, _, llm, _ = _use_case(
        responses=[
            "¿Qué voltaje tiene el modelo A-200?",
            '{"answer":"El A-200 usa 380 V [S2].","used_sources":["S2"],"sufficient":true}',
        ]
    )

    await use_case.execute("¿Y el A-200?", history, temperature=0.0)

    assert llm.temperatures == [0.0, 0.0]


async def test_gate_reject_returns_fallback_without_calling_the_llm() -> None:
    use_case, retriever, llm, _ = _use_case(responses=[])
    selected = SelectionDebug(
        mode="dynamic",
        enabled=True,
        decision="REJECT",
        signals={
            "denseTop1": 0.2,
            "denseSeparation": 0.01,
            "lexicalCoverage": 0.1,
        },
        thresholds={"denseTop1": 0.5, "lexicalCoverage": 0.6},
        kept=(),
        dropped=(),
    )
    base = retrieval_result()
    retriever.result = replace(
        base,
        chunks=(),
        debug=replace(base.debug, selection=selected),
    )

    answer = await use_case.execute("¿Pregunta fuera del corpus?", [])

    assert answer.answer == INSUFFICIENT_ANSWER
    assert answer.sufficient is False
    assert llm.calls == 0
    assert answer.usage.llm_called is False
    assert answer.usage.chunks_sent == 0
    assert answer.usage.prompt_tokens == 0


async def test_provider_usage_metadata_takes_precedence_over_estimates() -> None:
    use_case, _, _, _ = _use_case(
        responses=[
            '{"answer":"El modelo A-200 usa 380 V [S2].","used_sources":["S2"],"sufficient":true}'
        ],
        usages=[{"input_tokens": 123, "output_tokens": 7}],
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-200?", [])

    assert answer.usage.prompt_tokens == 123
    assert answer.usage.completion_tokens == 7
    assert answer.usage.llm_called is True


async def test_invalid_json_is_repaired_once() -> None:
    use_case, _, llm, _ = _use_case(
        responses=[
            "esto no es JSON",
            '{"answer":"Usa 220 V [S1].","used_sources":["S1"],"sufficient":true}',
        ]
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-100?", [])

    assert answer.sufficient is True
    assert answer.answer == "Usa 220 V [S1]."
    assert answer.sources[0].file == "manual.pdf"
    assert llm.calls == 2
    assert "Corrige la respuesta" in llm.prompts[1]


async def test_sufficient_answer_without_valid_citations_falls_back() -> None:
    use_case, _, _, _ = _use_case(
        responses=['{"answer":"Una respuesta sin fuente","used_sources":["S99"],"sufficient":true}']
    )

    answer = await use_case.execute("¿Qué voltaje tiene el A-100?", [])

    assert answer.answer == INSUFFICIENT_ANSWER
    assert answer.sufficient is False
    assert answer.sources == ()


async def test_invalid_json_twice_returns_safe_fallback() -> None:
    use_case, _, llm, _ = _use_case(responses=["no json", "sigue sin ser json"])

    answer = await use_case.execute("¿Qué voltaje tiene el A-100?", [])

    assert answer.answer == INSUFFICIENT_ANSWER
    assert answer.sufficient is False
    assert answer.sources == ()
    assert answer.images == ()
    assert llm.calls == 2


async def test_history_rewrites_the_retrieval_query() -> None:
    history = [
        ChatTurn(role="user", content="Háblame del modelo A-100."),
        ChatTurn(role="assistant", content="El A-100 usa 220 V."),
    ]
    use_case, retriever, llm, _ = _use_case(
        responses=[
            "¿Qué voltaje tiene el modelo A-200?",
            '{"answer":"El A-200 usa 380 V [S2].","used_sources":["S2"],"sufficient":true}',
        ]
    )

    await use_case.execute("¿Y el A-200?", history)

    assert retriever.queries == ["¿Qué voltaje tiene el modelo A-200?"]
    assert llm.calls == 2


async def test_conversation_history_is_loaded_and_appended() -> None:
    conversations = FakeConversations(stored=[ChatTurn(role="user", content="Pregunta previa")])
    use_case, retriever, _, _ = _use_case(
        top_score=0.1,
        responses=["consulta autónoma sobre la pregunta previa"],
        conversations=conversations,
    )

    answer = await use_case.execute(
        "¿Y ahora?",
        [],
        conversation_id="conv-1",
    )

    assert answer.answer == INSUFFICIENT_ANSWER
    assert conversations.requested == [("conv-1", 12)]
    assert retriever.queries == ["consulta autónoma sobre la pregunta previa"]
    assert conversations.appended
    assert conversations.appended[0][0] == "conv-1"
    assert [turn.role for turn in conversations.appended[0][1]] == ["user", "assistant"]


def test_prompt_contains_defensive_rules() -> None:
    system = PromptBuilder().system_prompt()

    assert "SOLO" in system
    assert "[S1]" in system
    assert "Ignora" in system
    assert "No tengo información suficiente" in system
    assert "JSON" in system
