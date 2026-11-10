from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.infrastructure.errors import map_provider_exception
from app.modules.ai.infrastructure.schema import (
    model_from_parsed,
    parse_json_payload,
    validate_structured_payload,
)
from app.shared.errors import LLMNotConfiguredError, UpstreamError


class GeminiLLM:
    """Google Gemini adapter using the official ``google-genai`` async client."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        client: genai.Client | None = None,
    ) -> None:
        if client is None:
            if not api_key or not api_key.strip():
                raise LLMNotConfiguredError("GEMINI_API_KEY is required for LLM_PROVIDER=gemini")
            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
        *,
        temperature: float | None = None,
    ) -> LLMResult:
        config_kwargs: dict[str, Any] = {}
        if system:
            config_kwargs["system_instruction"] = system
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            raise map_provider_exception("gemini", exc) from exc

        try:
            text = response.text or ""
        except (AttributeError, ValueError):
            text = ""

        parsed = model_from_parsed(response.parsed)
        if response_schema is not None:
            if parsed is None:
                if not text:
                    raise UpstreamError("Gemini returned an empty structured response")
                parsed = parse_json_payload(text, response_schema)
            else:
                parsed = validate_structured_payload(parsed, response_schema)

        usage = None
        metadata = response.usage_metadata
        if metadata is not None:
            usage = {
                "input_tokens": int(metadata.prompt_token_count or 0),
                "output_tokens": int(metadata.candidates_token_count or 0),
            }

        return LLMResult(
            text=text,
            model=response.model_version or self._model,
            parsed=parsed,
            usage=usage,
            provider="gemini",
        )
