from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.chat.application.dto.chat import ChatAnswer, ChatImage, ChatTurn, Source
from app.modules.chat.presentation.router import (
    get_ask_question_use_case,
    router,
)
from tests.modules.chat.helpers import retrieval_result


class FakeAsk:
    def __init__(self) -> None:
        debug = retrieval_result().debug
        self.answer = ChatAnswer(
            answer="Usa 220 V [S1].",
            sufficient=True,
            sources=(
                Source(
                    file="manual.pdf",
                    page=1,
                    bbox=(10.0, 10.0, 100.0, 20.0),
                    section_path=("Manual",),
                ),
            ),
            images=(
                ChatImage(
                    url="/documents/doc-1/pages/1/crop?bbox=10,30,100,80&highlight=false",
                    page=1,
                    bbox=(10.0, 30.0, 100.0, 80.0),
                ),
            ),
            debug=debug,
        )
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        query: str,
        history: Sequence[ChatTurn] | None = None,
        doc_id: str | None = None,
        *,
        conversation_id: str | None = None,
    ) -> ChatAnswer:
        self.calls.append(
            {
                "query": query,
                "history": list(history or []),
                "doc_id": doc_id,
                "conversation_id": conversation_id,
            }
        )
        return self.answer


def _app(fake: FakeAsk) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ask_question_use_case] = lambda: fake
    return app


def test_chat_api_returns_grounded_answer_without_debug() -> None:
    fake = FakeAsk()
    with TestClient(_app(fake)) as client:
        response = client.post(
            "/chat/ask",
            json={
                "query": "¿Qué voltaje usa?",
                "history": [{"role": "user", "content": "Háblame del A-100"}],
                "docId": "doc-1",
                "conversationId": "conv-1",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Usa 220 V [S1]."
    assert body["sufficient"] is True
    assert body["sources"][0]["file"] == "manual.pdf"
    assert body["sources"][0]["sectionPath"] == ["Manual"]
    assert body["images"][0]["url"].startswith("/documents/doc-1/")
    assert "debug" not in body
    assert fake.calls[0]["query"] == "¿Qué voltaje usa?"
    assert fake.calls[0]["doc_id"] == "doc-1"
    assert fake.calls[0]["conversation_id"] == "conv-1"
    assert fake.calls[0]["history"][0].content == "Háblame del A-100"


def test_chat_api_includes_debug_with_query_flag() -> None:
    fake = FakeAsk()
    with TestClient(_app(fake)) as client:
        response = client.post("/chat/ask?debug=true", json={"query": "¿Qué voltaje usa?"})

    assert response.status_code == 200
    debug = response.json()["debug"]
    assert debug["retrieved"][0]["chunkId"] == "chunk-1"
    assert debug["retrieved"][0]["rrfScore"] == 0.02
