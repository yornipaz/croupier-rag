from __future__ import annotations

from typing import Any

import httpx

from app.modules.ai.application.dto.llm import LLMResult, ResponseSchema
from app.modules.ai.infrastructure.errors import map_provider_exception
from app.modules.ai.infrastructure.schema import parse_json_payload, to_json_schema
from app.shared.errors import UpstreamError


class OllamaLLM:
    """Ollama adapter (``/api/chat``, non-streaming)."""

    def __init__(self, *, base_url: str, model: str, timeout_s: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        response_schema: ResponseSchema | None = None,
        *,
        temperature: float | None = None,
    ) -> LLMResult:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        if response_schema is not None:
            body["format"] = to_json_schema(response_schema)

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_s,
            ) as client:
                response = await client.post("/api/chat", json=body)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise map_provider_exception("ollama", exc) from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content:
            raise UpstreamError("Ollama returned an empty response")

        parsed = (
            parse_json_payload(content, response_schema)
            if response_schema is not None
            else None
        )
        usage = {
            "input_tokens": int(data.get("prompt_eval_count") or 0),
            "output_tokens": int(data.get("eval_count") or 0),
        }
        return LLMResult(
            text=content,
            model=str(data.get("model") or self._model),
            parsed=parsed,
            usage=usage,
            provider="ollama",
        )
