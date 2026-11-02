from __future__ import annotations

import asyncio
from collections.abc import Sequence

from fastembed.sparse import SparseTextEmbedding
from fastembed.sparse.bm25 import supported_languages

from app.modules.vector_store.application.dto.search import SparseVector
from app.shared.errors import ConfigurationError


class FastEmbedBM25:
    """Sparse BM25 encoder backed by FastEmbed and a language-specific stemmer."""

    def __init__(
        self,
        *,
        model_name: str = "Qdrant/bm25",
        language: str = "spanish",
        cache_dir: str | None = None,
        model: SparseTextEmbedding | None = None,
    ) -> None:
        if language not in supported_languages:
            raise ConfigurationError(
                f"Unsupported BM25 language: {language}",
                details={"supportedLanguages": sorted(supported_languages)},
            )
        self._model_name = model_name
        self._language = language
        self._cache_dir = cache_dir
        self._model = model
        self._load_lock = asyncio.Lock()

    async def _get_model(self) -> SparseTextEmbedding:
        if self._model is None:
            async with self._load_lock:
                if self._model is None:
                    try:
                        self._model = await asyncio.to_thread(
                            SparseTextEmbedding,
                            model_name=self._model_name,
                            cache_dir=self._cache_dir,
                            language=self._language,
                        )
                    except (OSError, ValueError) as exc:
                        raise ConfigurationError(
                            f"Could not load BM25 model {self._model_name}",
                            details={"error": type(exc).__name__},
                        ) from exc
        return self._model

    async def embed(self, texts: Sequence[str]) -> list[SparseVector]:
        if not texts:
            return []
        model = await self._get_model()
        embeddings = await asyncio.to_thread(lambda: list(model.embed(list(texts))))
        result: list[SparseVector] = []
        for embedding in embeddings:
            indices = [int(index) for index in embedding.indices]
            values = [float(value) for value in embedding.values]
            if len(indices) != len(values):
                raise ConfigurationError("BM25 returned mismatched indices/values")
            result.append(SparseVector(indices=indices, values=values))
        return result
