from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from fastembed import TextEmbedding

from app.shared.errors import ConfigurationError


def _model_info(model_name: str) -> dict[str, Any] | None:
    normalized = model_name.strip().lower()
    for info in TextEmbedding.list_supported_models():
        if str(info.get("model", "")).lower() == normalized:
            return info
    return None


def list_multilingual_models() -> list[str]:
    """Supported FastEmbed text models that advertise multilingual/Spanish support."""
    models: list[str] = []
    for info in TextEmbedding.list_supported_models():
        description = str(info.get("description", "")).lower()
        if "multimodal" in description or "programming languages" in description:
            continue
        if not any(token in description for token in ("multilingual", "multi-lingual", "spanish")):
            continue
        name = info.get("model")
        if isinstance(name, str):
            models.append(name)
    return sorted(set(models))


class FastEmbedEmbedding:
    """Local dense embeddings via FastEmbed; the ONNX model is loaded lazily."""

    def __init__(
        self,
        *,
        model_name: str,
        cache_dir: str | None = None,
        dimension: int | None = None,
        model: TextEmbedding | None = None,
    ) -> None:
        info = _model_info(model_name)
        if dimension is None:
            if info is None:
                raise ConfigurationError(
                    f"Unsupported FastEmbed model: {model_name}",
                    details={"supportedModels": list_multilingual_models()},
                )
            dimension = int(info["dim"])
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._dimension = dimension
        self._model = model
        self._load_lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _get_model(self) -> TextEmbedding:
        if self._model is None:
            async with self._load_lock:
                if self._model is None:
                    try:
                        self._model = await asyncio.to_thread(
                            TextEmbedding,
                            model_name=self._model_name,
                            cache_dir=self._cache_dir,
                        )
                    except (OSError, ValueError) as exc:
                        raise ConfigurationError(
                            f"Could not load FastEmbed model {self._model_name}",
                            details={"error": type(exc).__name__},
                        ) from exc
        return self._model

    async def warmup(self) -> None:
        """Load the ONNX model outside the resilience timeout (first download)."""
        await self._get_model()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await self._get_model()
        vectors = await asyncio.to_thread(lambda: list(model.embed(list(texts))))
        result: list[list[float]] = []
        for vector in vectors:
            values = [float(value) for value in vector]
            if len(values) != self._dimension:
                raise ConfigurationError(
                    f"FastEmbed model returned dimension {len(values)}, expected {self._dimension}"
                )
            result.append(values)
        return result
