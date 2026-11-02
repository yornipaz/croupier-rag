from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from redis.asyncio import Redis

from app.config.settings import Settings
from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort
from app.modules.documents.application.ports.file_storage import FileStoragePort
from app.modules.ingestion.application.pipeline import (
    ChunkStage,
    DetectStructureStage,
    EmbedStage,
    IndexStage,
    IngestionPipeline,
    LinkImagesStage,
    ParseStage,
)
from app.modules.ingestion.application.ports.jobs import (
    JobEventPublisherPort,
    JobEventSubscriberPort,
    JobRepositoryPort,
)
from app.modules.ingestion.application.ports.parser import DocumentParserPort
from app.modules.ingestion.application.use_cases.get_job import GetJobUseCase
from app.modules.ingestion.application.use_cases.stream_job_events import (
    StreamJobEventsUseCase,
)
from app.modules.ingestion.domain.chunking import LayoutChunker
from app.modules.ingestion.infrastructure.redis_jobs import (
    RedisJobEventPublisher,
    RedisJobEventSubscriber,
    RedisJobRepository,
)
from app.modules.ingestion.presentation.router import router
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.application.ports.vector_store import VectorStorePort

__all__ = [
    "IngestionServices",
    "build_ingestion_module",
    "build_ingestion_pipeline",
    "build_ingestion_router",
    "build_ingestion_services",
    "router",
]


@dataclass(frozen=True, slots=True)
class IngestionServices:
    job_repository: JobRepositoryPort
    job_publisher: JobEventPublisherPort
    job_subscriber: JobEventSubscriberPort
    get_job: GetJobUseCase
    stream_job_events: StreamJobEventsUseCase


def build_ingestion_services(settings: Settings, redis: Redis) -> IngestionServices:
    repository = RedisJobRepository(
        redis,
        prefix=settings.job_state_prefix,
        ttl_seconds=settings.job_state_ttl_seconds,
    )
    publisher = RedisJobEventPublisher(redis, prefix=settings.job_events_prefix)
    subscriber = RedisJobEventSubscriber(redis, prefix=settings.job_events_prefix)
    return IngestionServices(
        job_repository=repository,
        job_publisher=publisher,
        job_subscriber=subscriber,
        get_job=GetJobUseCase(repository),
        stream_job_events=StreamJobEventsUseCase(repository, subscriber),
    )


def build_ingestion_pipeline(
    settings: Settings,
    *,
    parser: DocumentParserPort,
    documents: DocumentRepositoryPort,
    files: FileStoragePort,
    jobs: JobRepositoryPort,
    events: JobEventPublisherPort,
    embedding: EmbeddingPort,
    sparse_encoder: SparseEncoderPort,
    vectors: VectorStorePort,
) -> IngestionPipeline:
    chunker = LayoutChunker(
        settings.chunk_max_tokens,
        settings.chunk_overlap_tokens,
    )
    return IngestionPipeline(
        documents=documents,
        files=files,
        jobs=jobs,
        events=events,
        stages=[
            ParseStage(parser),
            DetectStructureStage(),
            LinkImagesStage(),
            ChunkStage(chunker),
            EmbedStage(
                embedding,
                sparse_encoder,
                batch_size=settings.embed_batch_size,
            ),
            IndexStage(vectors),
        ],
    )


def build_ingestion_router(settings: Settings) -> APIRouter:
    _ = settings
    return router


def build_ingestion_module(settings: Settings) -> APIRouter:
    return build_ingestion_router(settings)
