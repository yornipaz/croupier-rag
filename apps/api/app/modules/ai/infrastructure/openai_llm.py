from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.infrastructure.errors import map_provider_exception
from app.modules.ai.infrastructure.schema import parse_json_payload, to_json_schema
from app.shared.errors import LLMNotConfiguredError, UpstreamError


class OpenAILLM:
    """Minimal OpenAI Chat Completions adapter (optional provider)."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 60.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise LLMNotConfiguredError("OPENAI_API_KEY is required for LLM_PROVIDER=openai")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
    ) -> LLMResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
        }
        if response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": to_json_schema(response_schema),
                },
            }

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_s,
                headers={"Authorization": f"Bearer {self._api_key}"},
            ) as client:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise map_provider_exception("openai", exc) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError("OpenAI returned an unexpected response") from exc
        if not isinstance(content, str) or not content:
            raise UpstreamError("OpenAI returned an empty response")

        parsed = (
            parse_json_payload(content, response_schema)
            if response_schema is not None
            else None
        )
        raw_usage = data.get("usage") or {}
        usage = {
            "input_tokens": int(raw_usage.get("prompt_tokens") or 0),
            "output_tokens": int(raw_usage.get("completion_tokens") or 0),
        }
        return LLMResult(
            text=content,
            model=str(data.get("model") or self._model),
            parsed=parsed,
            usage=usage,
            provider="openai",
        )
