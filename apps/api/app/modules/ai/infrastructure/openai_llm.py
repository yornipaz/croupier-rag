from __future__ import annotations

import json
from typing import Any

import httpx

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.infrastructure.errors import map_provider_exception
from app.modules.ai.infrastructure.schema import parse_json_payload, to_json_schema
from app.shared.errors import LLMNotConfiguredError, UpstreamError


class OpenAILLM:
    """OpenAI-compatible Chat Completions adapter.

    It is used directly for OpenAI and as the base for DeepSeek, which exposes
    the same wire format with a different base URL and model id.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 60.0,
        provider: str = "openai",
        json_schema_supported: bool = True,
        thinking_enabled: bool | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise LLMNotConfiguredError(
                f"API key is required for LLM_PROVIDER={provider}"
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._provider = provider
        self._json_schema_supported = json_schema_supported
        self._thinking_enabled = thinking_enabled

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
        *,
        temperature: float | None = None,
    ) -> LLMResult:
        effective_prompt = prompt
        effective_system = system
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0 if temperature is None else temperature,
        }

        if response_schema is not None:
            if self._json_schema_supported:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "strict": True,
                        "schema": to_json_schema(response_schema),
                    },
                }
            else:
                # DeepSeek Chat Completions only supports json_object, not
                # json_schema. Put the schema in the prompt and validate the
                # returned JSON with Pydantic after parsing.
                body["response_format"] = {"type": "json_object"}
                schema_text = json.dumps(
                    to_json_schema(response_schema), ensure_ascii=False
                )
                instruction = (
                    "Devuelve exclusivamente un objeto JSON que cumpla este JSON Schema:\n"
                    f"{schema_text}"
                )
                if effective_system:
                    effective_system = f"{effective_system}\n\n{instruction}"
                else:
                    effective_prompt = f"{effective_prompt}\n\n{instruction}"

        if self._thinking_enabled is not None:
            body["thinking"] = {
                "type": "enabled" if self._thinking_enabled else "disabled"
            }

        messages: list[dict[str, str]] = []
        if effective_system:
            messages.append({"role": "system", "content": effective_system})
        messages.append({"role": "user", "content": effective_prompt})
        body["messages"] = messages

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
            raise map_provider_exception(self._provider, exc) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(
                f"{self._provider} returned an unexpected response"
            ) from exc
        if not isinstance(content, str) or not content:
            raise UpstreamError(f"{self._provider} returned an empty response")

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
            provider=self._provider,
        )
