from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types

from app.modules.ai.infrastructure.errors import map_provider_exception
from app.shared.errors import ConfigurationError, EmbeddingNotConfiguredError, UpstreamError


class GeminiEmbedding:
    """Dense embeddings through the official ``google-genai`` async client."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dimension: int,
        client: genai.Client | None = None,
    ) -> None:
        if client is None:
            if not api_key or not api_key.strip():
                raise EmbeddingNotConfiguredError(
                    "GEMINI_API_KEY is required for EMBEDDING_PROVIDER=gemini"
                )
            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        contents: list[Any] = list(texts)
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=self._dimension),
            )
        except Exception as exc:
            raise map_provider_exception("gemini", exc) from exc

        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise UpstreamError("Gemini returned an unexpected embeddings payload")

        result: list[list[float]] = []
        for embedding in embeddings:
            if embedding.values is None:
                raise UpstreamError("Gemini returned an empty embedding")
            values = [float(value) for value in embedding.values]
            if len(values) != self._dimension:
                raise ConfigurationError(
                    f"Gemini returned dimension {len(values)}, expected {self._dimension}"
                )
            result.append(values)
        return result
