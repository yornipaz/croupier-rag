from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.modules.documents.application.dto.document import Document
from app.modules.ingestion.application.pipeline import IngestionPipeline
from app.modules.ingestion.domain.parsed import ParsedDocument
from app.modules.ingestion.module import build_ingestion_pipeline
from app.modules.vector_store.application.dto.embedded import EmbeddedChunk
from app.modules.vector_store.application.dto.search import SearchHit, SparseVector
from app.shared.chunks import Chunk
from app.shared.errors import BadRequestError, JobNotFoundError
from app.shared.jobs import Job
from tests.modules.ingestion.helpers import parsed_fixture


class FakeDocumentRepository:
    def __init__(self, document: Document) -> None:
        self.documents = {document.id: document}

    async def save(self, document: Document) -> None:
        self.documents[document.id] = document

    async def get(self, document_id: str) -> Document:
        return self.documents[document_id]

    async def list_all(self) -> list[Document]:
        return list(self.documents.values())

    async def delete(self, document_id: str) -> None:
        self.documents.pop(document_id, None)


class FakeFileStorage:
    async def save_pdf(self, document_id: str, content: bytes) -> Path:
        _ = document_id, content
        return Path("/tmp/fake.pdf")

    async def pdf_path(self, document_id: str) -> Path:
        _ = document_id
        return Path("/tmp/fake.pdf")

    async def delete_document(self, document_id: str) -> None:
        _ = document_id


class FakeJobRepository:
    def __init__(self, job: Job) -> None:
        self.jobs = {job.job_id: job}
        self.history: list[Job] = [job]

    async def save(self, job: Job) -> None:
        self.jobs[job.job_id] = job
        self.history.append(job)

    async def get(self, job_id: str) -> Job:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError("missing job") from exc

    async def delete(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)


class FakePublisher:
    def __init__(self) -> None:
        self.jobs: list[Job] = []

    async def publish(self, job: Job) -> None:
        self.jobs.append(job)


class FakeParser:
    def __init__(self, parsed: ParsedDocument, error: Exception | None = None) -> None:
        self.parsed = parsed
        self.error = error

    async def parse(self, pdf_path: Path, document_id: str) -> ParsedDocument:
        _ = pdf_path, document_id
        if self.error is not None:
            raise self.error
        return self.parsed


class FakeEmbedding:
    dimension = 3

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeSparseEncoder:
    async def embed(self, texts: Sequence[str]) -> list[SparseVector]:
        return [SparseVector(indices=[1], values=[1.0]) for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.points: dict[str, EmbeddedChunk] = {}
        self.ensured = 0

    async def ensure_collection(self) -> None:
        self.ensured += 1

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        _ = chunks

    async def upsert_embedded(self, chunks: Sequence[EmbeddedChunk]) -> None:
        for item in chunks:
            self.points[item.chunk.id] = item

    async def hybrid_search(
        self,
        dense: Sequence[float],
        sparse: SparseVector,
        top_k: int,
        doc_id: str | None = None,
    ) -> list[SearchHit]:
        _ = dense, sparse, top_k, doc_id
        return []

    async def delete_by_doc(self, doc_id: str) -> None:
        _ = doc_id


def _document() -> Document:
    return Document(
        id="doc-1",
        filename="manual.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_path="/tmp/fake.pdf",
        sha256="abc",
        created_at=datetime.now(UTC),
        job_id="job-1",
    )


def _pipeline(
    *,
    parser_error: Exception | None = None,
) -> tuple[IngestionPipeline, FakeJobRepository, FakeDocumentRepository, FakeVectorStore]:
    settings = Settings(
        _env_file=None,
        chunk_max_tokens=80,
        chunk_overlap_tokens=0,
    )
    document = _document()
    documents = FakeDocumentRepository(document)
    jobs = FakeJobRepository(
        Job(job_id="job-1", doc_id="doc-1", status="PENDING", stage="queued", progress=0)
    )
    vectors = FakeVectorStore()
    pipeline = build_ingestion_pipeline(
        settings,
        parser=FakeParser(parsed_fixture(), parser_error),
        documents=documents,
        files=FakeFileStorage(),
        jobs=jobs,
        events=FakePublisher(),
        embedding=FakeEmbedding(),
        sparse_encoder=FakeSparseEncoder(),
        vectors=vectors,
    )
    return pipeline, jobs, documents, vectors


async def test_pipeline_reaches_completed_and_is_idempotent() -> None:
    pipeline, jobs, documents, vectors = _pipeline()

    await pipeline.run("job-1", "doc-1")
    first_ids = set(vectors.points)
    first_chunk_count = len(first_ids)
    await pipeline.run("job-1", "doc-1")

    assert jobs.history[-1].status == "COMPLETED"
    assert jobs.history[-1].stage == "completed"
    stages = {job.stage for job in jobs.history}
    assert {"parse", "detect_structure", "link_images", "chunk", "embed", "index"} <= stages
    assert len(vectors.points) == first_chunk_count
    assert set(vectors.points) == first_ids
    assert any(item.chunk.image_ids for item in vectors.points.values())
    assert documents.documents["doc-1"].chunk_count == first_chunk_count
    assert documents.documents["doc-1"].page_count == 1


async def test_pipeline_failure_sets_failed_reason() -> None:
    pipeline, jobs, _, _ = _pipeline(parser_error=BadRequestError("pdf inválido"))

    with pytest.raises(BadRequestError):
        await pipeline.run("job-1", "doc-1")

    assert jobs.history[-1].status == "FAILED"
    assert jobs.history[-1].error == "parse: pdf inválido"


async def test_pipeline_marks_failed_if_document_metadata_is_missing() -> None:
    pipeline, jobs, documents, _ = _pipeline()
    documents.documents.clear()

    with pytest.raises(KeyError):
        await pipeline.run("job-1", "doc-1")

    assert jobs.history[-1].status == "FAILED"
    assert jobs.history[-1].error is not None
