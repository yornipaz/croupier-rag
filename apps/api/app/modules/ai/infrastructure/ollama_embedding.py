from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.modules.ai.infrastructure.errors import map_provider_exception
from app.shared.errors import ConfigurationError, UpstreamError


class OllamaEmbedding:
    """Dense embeddings through Ollama's batch ``/api/embed`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimension: int,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout_s = timeout_s

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_s,
            ) as client:
                response = await client.post(
                    "/api/embed",
                    json={"model": self._model, "input": list(texts)},
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
        except Exception as exc:
            raise map_provider_exception("ollama", exc) from exc

        raw_embeddings = data.get("embeddings")
        if not isinstance(raw_embeddings, list) or len(raw_embeddings) != len(texts):
            raise UpstreamError("Ollama returned an unexpected embeddings payload")

        result: list[list[float]] = []
        for raw in raw_embeddings:
            if not isinstance(raw, list):
                raise UpstreamError("Ollama returned a non-vector embedding")
            values = [float(value) for value in raw]
            if len(values) != self._dimension:
                raise ConfigurationError(
                    f"Ollama returned dimension {len(values)}, expected {self._dimension}"
                )
            result.append(values)
        return result
