from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.modules.ai.application.ports.embedding import EmbeddingPort
from app.modules.documents.application.dto.document import Document
from app.modules.documents.application.ports.document_repository import DocumentRepositoryPort
from app.modules.documents.application.ports.file_storage import FileStoragePort
from app.modules.ingestion.application.ports.jobs import (
    JobEventPublisherPort,
    JobRepositoryPort,
)
from app.modules.ingestion.application.ports.parser import DocumentParserPort
from app.modules.ingestion.domain.chunking import LayoutChunker
from app.modules.ingestion.domain.image_linker import link_images
from app.modules.ingestion.domain.parsed import ParsedDocument
from app.modules.ingestion.domain.structure import detect_sections
from app.modules.vector_store.application.dto.embedded import EmbeddedChunk
from app.modules.vector_store.application.ports.sparse_encoder import SparseEncoderPort
from app.modules.vector_store.application.ports.vector_store import VectorStorePort
from app.shared.chunks import Chunk
from app.shared.errors import AppError, UpstreamError
from app.shared.jobs import Job, JobStatus
from app.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class IngestionContext:
    job_id: str
    document: Document
    pdf_path: Path
    parsed: ParsedDocument | None = None
    chunks: list[Chunk] = field(default_factory=list)
    embedded: list[EmbeddedChunk] = field(default_factory=list)


class PipelineStage(Protocol):
    name: str
    start_progress: int
    end_progress: int

    async def run(self, context: IngestionContext) -> IngestionContext: ...


class ParseStage:
    name = "parse"
    start_progress = 0
    end_progress = 25

    def __init__(self, parser: DocumentParserPort) -> None:
        self._parser = parser

    async def run(self, context: IngestionContext) -> IngestionContext:
        context.parsed = await self._parser.parse(
            context.pdf_path,
            context.document.id,
        )
        return context


class DetectStructureStage:
    name = "detect_structure"
    start_progress = 25
    end_progress = 40

    async def run(self, context: IngestionContext) -> IngestionContext:
        context.parsed = detect_sections(_require_parsed(context))
        return context


class LinkImagesStage:
    name = "link_images"
    start_progress = 40
    end_progress = 50

    async def run(self, context: IngestionContext) -> IngestionContext:
        context.parsed = link_images(_require_parsed(context))
        return context


class ChunkStage:
    name = "chunk"
    start_progress = 50
    end_progress = 65

    def __init__(self, chunker: LayoutChunker) -> None:
        self._chunker = chunker

    async def run(self, context: IngestionContext) -> IngestionContext:
        context.chunks = self._chunker.chunk(_require_parsed(context))
        return context


class EmbedStage:
    name = "embed"
    start_progress = 65
    end_progress = 85

    def __init__(
        self,
        embedding: EmbeddingPort,
        sparse_encoder: SparseEncoderPort,
        *,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._embedding = embedding
        self._sparse_encoder = sparse_encoder
        self._batch_size = batch_size

    async def run(self, context: IngestionContext) -> IngestionContext:
        warmup = getattr(self._embedding, "warmup", None)
        if callable(warmup):
            await warmup()
        embedded: list[EmbeddedChunk] = []
        for start in range(0, len(context.chunks), self._batch_size):
            batch = context.chunks[start : start + self._batch_size]
            texts = [chunk.text for chunk in batch]
            dense_vectors = await self._embedding.embed(texts)
            sparse_vectors = await self._sparse_encoder.embed(texts)
            if len(dense_vectors) != len(batch) or len(sparse_vectors) != len(batch):
                raise UpstreamError("Embedding adapters returned a different number of vectors")
            for chunk, dense, sparse in zip(
                batch,
                dense_vectors,
                sparse_vectors,
                strict=True,
            ):
                if len(dense) != self._embedding.dimension:
                    raise UpstreamError(
                        "Embedding adapter returned an invalid vector dimension",
                        details={
                            "expected": self._embedding.dimension,
                            "actual": len(dense),
                        },
                    )
                embedded.append(
                    EmbeddedChunk(
                        chunk=chunk,
                        dense=tuple(dense),
                        sparse=sparse,
                    )
                )
        context.embedded = embedded
        return context


class IndexStage:
    name = "index"
    start_progress = 85
    end_progress = 98

    def __init__(self, vectors: VectorStorePort) -> None:
        self._vectors = vectors

    async def run(self, context: IngestionContext) -> IngestionContext:
        if context.embedded:
            await self._vectors.ensure_collection()
            await self._vectors.upsert_embedded(context.embedded)
        return context


class IngestionPipeline:
    """Interchangeable-stage ingestion pipeline reporting progress to Redis."""

    def __init__(
        self,
        *,
        documents: DocumentRepositoryPort,
        files: FileStoragePort,
        jobs: JobRepositoryPort,
        events: JobEventPublisherPort,
        stages: list[PipelineStage],
    ) -> None:
        self._documents = documents
        self._files = files
        self._jobs = jobs
        self._events = events
        self._stages = stages

    async def run(self, job_id: str, document_id: str) -> None:
        job = await self._jobs.get(job_id)
        current_stage = "loading"
        try:
            job = await self._report(job, "PROCESSING", current_stage, 0)
            document = await self._documents.get(document_id)
            pdf_path = await self._files.pdf_path(document_id)
            context = IngestionContext(
                job_id=job_id,
                document=document,
                pdf_path=pdf_path,
            )

            for stage in self._stages:
                current_stage = stage.name
                job = await self._report(
                    job,
                    "PROCESSING",
                    stage.name,
                    stage.start_progress,
                )
                context = await stage.run(context)
                job = await self._report(
                    job,
                    "PROCESSING",
                    stage.name,
                    stage.end_progress,
                )

            parsed = context.parsed
            if parsed is None:
                raise UpstreamError("Ingestion finished without a parsed document")
            await self._documents.save(
                replace(
                    document,
                    page_count=parsed.page_count,
                    chunk_count=len(context.chunks),
                )
            )
            await self._report(job, "COMPLETED", "completed", 100)
        except Exception as exc:
            if job is not None:
                message = _error_message(current_stage, exc)
                try:
                    await self._report(job, "FAILED", current_stage, job.progress, message)
                except Exception:
                    logger.exception("ingestion.failed_state_not_persisted", job_id=job_id)
            raise

    async def _report(
        self,
        job: Job,
        status: JobStatus,
        stage: str,
        progress: int,
        error: str | None = None,
    ) -> Job:
        updated = replace(
            job,
            status=status,
            stage=stage,
            progress=max(0, min(100, progress)),
            error=error,
            updated_at=datetime.now(UTC),
        )
        await self._jobs.save(updated)
        try:
            await self._events.publish(updated)
        except Exception:
            logger.warning("ingestion.event_publish_failed", job_id=job.job_id)
        return updated


def _require_parsed(context: IngestionContext) -> ParsedDocument:
    if context.parsed is None:
        raise UpstreamError("Pipeline stage ran before parsing")
    return context.parsed


def _error_message(stage: str, exc: BaseException) -> str:
    if isinstance(exc, AppError):
        message = f"{stage}: {exc.message}"
    else:
        message = f"{stage}: {type(exc).__name__}: {exc}"
    return message[:500]
