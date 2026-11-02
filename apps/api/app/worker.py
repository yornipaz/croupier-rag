from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

from celery.app.task import Task
from celery.exceptions import SoftTimeLimitExceeded
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.celery_app import INGESTION_TASK_NAME, celery_app
from app.config.settings import get_settings
from app.modules.ai.module import build_embedding
from app.modules.documents.infrastructure.document_repository import (
    FileSystemDocumentRepository,
)
from app.modules.documents.infrastructure.filesystem import FileSystemStorage
from app.modules.ingestion.infrastructure.parser import PyMuPDFParser
from app.modules.ingestion.infrastructure.redis_jobs import (
    RedisJobEventPublisher,
    RedisJobRepository,
)
from app.modules.ingestion.module import build_ingestion_pipeline
from app.modules.vector_store.module import build_sparse_encoder, build_vector_store
from app.shared.context import bind_job_id, reset_job_id
from app.shared.errors import AppError, JobNotFoundError
from app.shared.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name=INGESTION_TASK_NAME,
    acks_late=True,
    max_retries=settings.ingestion_max_retries,
    soft_time_limit=settings.ingestion_soft_time_limit_s,
    time_limit=settings.ingestion_time_limit_s,
)
def ingest_document(self: Task, job_id: str, document_id: str) -> None:
    """Run the ingestion pipeline in an isolated asyncio event loop."""
    token = bind_job_id(job_id)
    logger.info("ingestion.started", job_id=job_id, document_id=document_id)
    try:
        _process(job_id, document_id)
    except SoftTimeLimitExceeded:
        _mark_failed(job_id, "La ingesta excedió el tiempo máximo permitido")
        logger.warning("ingestion.soft_timeout", job_id=job_id)
    except AppError as exc:
        if exc.retryable and self.request.retries < settings.ingestion_max_retries:
            countdown = _backoff(self.request.retries)
            logger.warning(
                "ingestion.retry",
                job_id=job_id,
                retry=self.request.retries + 1,
                countdown=countdown,
                code=exc.code,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc
        _mark_failed(job_id, exc.message)
        logger.warning("ingestion.failed", job_id=job_id, code=exc.code)
    except Exception as exc:
        if self.request.retries < settings.ingestion_max_retries:
            countdown = _backoff(self.request.retries)
            logger.warning(
                "ingestion.retry",
                job_id=job_id,
                retry=self.request.retries + 1,
                countdown=countdown,
                error_type=type(exc).__name__,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc
        _mark_failed(job_id, f"Ingesta fallida: {type(exc).__name__}")
        logger.exception("ingestion.failed", job_id=job_id)
    finally:
        reset_job_id(token)


def _process(job_id: str, document_id: str) -> None:
    asyncio.run(_process_async(job_id, document_id))


async def _process_async(job_id: str, document_id: str) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=int(settings.vector_store_timeout_s),
    )
    try:
        documents = FileSystemDocumentRepository(settings.resolved_data_dir)
        files = FileSystemStorage(settings.resolved_data_dir)
        jobs = RedisJobRepository(
            redis,
            prefix=settings.job_state_prefix,
            ttl_seconds=settings.job_state_ttl_seconds,
        )
        events = RedisJobEventPublisher(redis, prefix=settings.job_events_prefix)
        parser = PyMuPDFParser(
            files,
            min_image_size_pt=settings.image_min_size_pt,
            image_dpi=settings.image_dpi,
        )
        embedding = build_embedding(settings)
        sparse_encoder = build_sparse_encoder(settings)
        vectors = build_vector_store(
            settings,
            client=qdrant,
            embedding=embedding,
            sparse_encoder=sparse_encoder,
        )
        pipeline = build_ingestion_pipeline(
            settings,
            parser=parser,
            documents=documents,
            files=files,
            jobs=jobs,
            events=events,
            embedding=embedding,
            sparse_encoder=sparse_encoder,
            vectors=vectors,
        )
        await pipeline.run(job_id, document_id)
    finally:
        await _close(redis.aclose)
        await _close(qdrant.close)


def _mark_failed(job_id: str, message: str) -> None:
    async def _run() -> None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            jobs = RedisJobRepository(
                redis,
                prefix=settings.job_state_prefix,
                ttl_seconds=settings.job_state_ttl_seconds,
            )
            events = RedisJobEventPublisher(redis, prefix=settings.job_events_prefix)
            try:
                job = await jobs.get(job_id)
            except JobNotFoundError:
                return
            failed = replace(
                job,
                status="FAILED",
                stage="failed",
                error=message[:500],
                updated_at=datetime.now(UTC),
            )
            await jobs.save(failed)
            try:
                await events.publish(failed)
            except Exception:
                logger.warning("ingestion.failed_event_not_published", job_id=job_id)
        finally:
            await _close(redis.aclose)

    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("ingestion.failed_state_not_persisted", job_id=job_id)


def _backoff(retries: int) -> float:
    return float(
        min(
            settings.ingestion_retry_max_s,
            settings.ingestion_retry_base_s * (2**retries),
        )
    )


async def _close(operation: Callable[[], Awaitable[None]]) -> None:
    try:
        await operation()
    except Exception:
        logger.debug("ingestion.close_failed")


__all__ = ["celery_app", "ingest_document"]
