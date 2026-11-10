from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter

from app.config.settings import Settings
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.retrieval.application.ports.image_catalog import ImageCatalogPort
from app.modules.retrieval.application.ports.image_url_builder import ImageUrlBuilderPort
from app.modules.retrieval.application.selection_service import (
    SelectionConfig,
    SelectionService,
)
from app.modules.retrieval.application.use_cases.retrieve_context import (
    RetrieveContextUseCase,
)
from app.modules.retrieval.infrastructure.calibration import FileCalibrationStore
from app.modules.retrieval.infrastructure.image_catalog import FileSystemImageCatalog
from app.modules.retrieval.infrastructure.image_urls import CropImageUrlBuilder
from app.modules.retrieval.presentation.router import router
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.application.ports.vector_store import VectorStorePort

__all__ = [
    "RetrievalServices",
    "build_retrieval_module",
    "build_retrieval_router",
    "build_retrieval_services",
    "router",
]


@dataclass(frozen=True, slots=True)
class RetrievalServices:
    retrieve_context: RetrieveContextUseCase


def build_retrieval_services(
    settings: Settings,
    *,
    embedding: EmbeddingPort,
    sparse_encoder: SparseEncoderPort,
    vectors: VectorStorePort,
    images: ImageCatalogPort | None = None,
    image_urls: ImageUrlBuilderPort | None = None,
) -> RetrievalServices:
    data_dir: Path = settings.resolved_data_dir
    catalog = images or FileSystemImageCatalog(data_dir)
    urls = image_urls or CropImageUrlBuilder(settings.api_prefix)
    calibration = FileCalibrationStore(
        data_dir / "calibration.json",
        expected_embedding_model=settings.embedding_model,
    )
    selection = SelectionService(
        SelectionConfig(
            mode=settings.selection_mode,
            min_k=settings.min_k,
            max_k=settings.max_k,
            rel_ratio=settings.rel_ratio,
            gap_ratio=settings.gap_ratio,
            mmr_lambda=settings.mmr_lambda,
            duplicate_threshold=settings.mmr_duplicate_threshold,
            context_token_budget=settings.context_token_budget,
            token_estimate_factor=settings.token_estimate_factor,
        ),
        calibration=calibration,
    )
    return RetrievalServices(
        retrieve_context=RetrieveContextUseCase(
            embedding,
            sparse_encoder,
            vectors,
            catalog,
            urls,
            default_top_k=settings.retrieval_top_k,
            selection=selection,
            candidate_pool=settings.candidate_pool,
        )
    )


def build_retrieval_router(settings: Settings) -> APIRouter:
    _ = settings
    return router


def build_retrieval_module(settings: Settings) -> APIRouter:
    return build_retrieval_router(settings)
