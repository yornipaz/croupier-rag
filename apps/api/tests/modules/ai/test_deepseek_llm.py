from __future__ import annotations

import json

import httpx
import respx
from pydantic import BaseModel

from app.modules.ai.infrastructure.deepseek_llm import DeepSeekLLM


class AnswerPayload(BaseModel):
    answer: str


@respx.mock
async def test_deepseek_uses_json_object_and_disables_thinking() -> None:
    route = respx.post("https://api.deepseek.test/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer": "ok"}'}}],
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )
    )
    llm = DeepSeekLLM(
        api_key="sk-test",
        model="deepseek-flash",
        base_url="https://api.deepseek.test",
        thinking_enabled=False,
    )

    result = await llm.generate(
        "Devuelve la respuesta en JSON",
        system="Eres un asistente técnico",
        response_schema=AnswerPayload,
    )

    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert "json_schema" not in body["response_format"]
    assert "JSON Schema" in body["messages"][0]["content"]
    assert result.provider == "deepseek"
    assert result.parsed == {"answer": "ok"}
    assert result.usage == {"input_tokens": 12, "output_tokens": 4}
