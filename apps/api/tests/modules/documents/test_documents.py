from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.documents.application.dto.document import Document, UploadedDocument
from app.modules.documents.application.use_cases.delete_document import DeleteDocumentUseCase
from app.modules.documents.application.use_cases.render_page_crop import parse_bbox
from app.modules.documents.application.use_cases.upload_document import UploadDocumentUseCase
from app.modules.documents.infrastructure.document_repository import (
    FileSystemDocumentRepository,
)
from app.modules.documents.presentation.router import get_upload_document_use_case, router
from app.shared.errors import (
    BadRequestError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    UpstreamError,
)
from app.shared.jobs import Job


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    async def save(self, document: Document) -> None:
        self.documents[document.id] = document

    async def get(self, document_id: str) -> Document:
        return self.documents[document_id]

    async def list_all(self) -> list[Document]:
        return list(self.documents.values())

    async def delete(self, document_id: str) -> None:
        self.documents.pop(document_id, None)


class FakeFileStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save_pdf(self, document_id: str, content: bytes) -> Path:
        self.saved[document_id] = content
        return Path(f"/data/files/{document_id}.pdf")

    async def pdf_path(self, document_id: str) -> Path:
        return Path(f"/data/files/{document_id}.pdf")

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


class FakeJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.deleted: list[str] = []

    async def save(self, job: Job) -> None:
        self.jobs[job.job_id] = job

    async def get(self, job_id: str) -> Job:
        return self.jobs[job_id]

    async def delete(self, job_id: str) -> None:
        self.deleted.append(job_id)


class FakeDispatcher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error = error

    async def enqueue(self, job_id: str, document_id: str) -> None:
        self.calls.append((job_id, document_id))
        if self.error is not None:
            raise self.error


class FakeVectorDeleter:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_by_doc(self, document_id: str) -> None:
        self.deleted.append(document_id)


class FakePageRenderer:
    def __init__(self) -> None:
        self.invalidated: list[str] = []

    async def render_crop(
        self,
        document_id: str,
        page_number: int,
        bbox: tuple[float, float, float, float],
        *,
        highlight: bool,
    ) -> bytes:
        _ = document_id, page_number, bbox, highlight
        return b"png"

    async def invalidate(self, document_id: str) -> None:
        self.invalidated.append(document_id)


async def test_upload_persists_document_and_pending_job() -> None:
    documents = FakeDocumentRepository()
    files = FakeFileStorage()
    jobs = FakeJobRepository()
    dispatcher = FakeDispatcher()
    use_case = UploadDocumentUseCase(
        documents,
        files,
        jobs,
        dispatcher,
        max_upload_bytes=1024,
    )

    result = await use_case.execute(
        filename="manual.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7 small fixture",
    )

    assert result.document_id in documents.documents
    assert result.job_id in jobs.jobs
    assert jobs.jobs[result.job_id].status == "PENDING"
    assert jobs.jobs[result.job_id].progress == 0
    assert dispatcher.calls == [(result.job_id, result.document_id)]
    assert files.saved[result.document_id].startswith(b"%PDF-")


async def test_upload_cleans_up_when_enqueue_fails() -> None:
    documents = FakeDocumentRepository()
    files = FakeFileStorage()
    jobs = FakeJobRepository()
    use_case = UploadDocumentUseCase(
        documents,
        files,
        jobs,
        FakeDispatcher(error=RuntimeError("broker down")),
        max_upload_bytes=1024,
    )

    with pytest.raises(UpstreamError):
        await use_case.execute(
            filename="manual.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7 fixture",
        )

    assert documents.documents == {}
    assert files.deleted
    assert len(jobs.jobs) == 1
    assert next(iter(jobs.jobs.values())).status == "FAILED"


async def test_upload_rejects_non_pdf_and_oversize() -> None:
    use_case = UploadDocumentUseCase(
        FakeDocumentRepository(),
        FakeFileStorage(),
        FakeJobRepository(),
        FakeDispatcher(),
        max_upload_bytes=10,
    )

    with pytest.raises(UnsupportedMediaTypeError):
        await use_case.execute(filename="x.pdf", content_type="text/plain", content=b"hello")
    with pytest.raises(UnsupportedMediaTypeError):
        await use_case.execute(
            filename="x.pdf",
            content_type="application/pdf",
            content=b"not a pdf",
        )
    with pytest.raises(PayloadTooLargeError):
        await use_case.execute(
            filename="x.pdf",
            content_type="application/pdf",
            content=b"%PDF-" + b"x" * 20,
        )


async def test_delete_removes_vectors_files_cache_and_job() -> None:
    document = Document(
        id="doc-1",
        filename="manual.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_path="/data/files/doc-1.pdf",
        sha256="abc",
        created_at=datetime.now(UTC),
        job_id="job-1",
    )
    documents = FakeDocumentRepository()
    await documents.save(document)
    jobs = FakeJobRepository()
    jobs.jobs["job-1"] = Job("job-1", "doc-1", "COMPLETED", "completed", 100)
    files = FakeFileStorage()
    vectors = FakeVectorDeleter()
    pages = FakePageRenderer()
    use_case = DeleteDocumentUseCase(documents, files, jobs, vectors, pages)

    await use_case.execute("doc-1")

    assert vectors.deleted == ["doc-1"]
    assert files.deleted == ["doc-1"]
    assert pages.invalidated == ["doc-1"]
    assert jobs.deleted == ["job-1"]
    assert "doc-1" not in documents.documents


def test_parse_bbox_validates_shape() -> None:
    assert parse_bbox("1,2,3,4") == (1.0, 2.0, 3.0, 4.0)
    with pytest.raises(BadRequestError):
        parse_bbox("1,2,3")
    with pytest.raises(BadRequestError):
        parse_bbox("1,2,3,2")


async def test_filesystem_metadata_repository_roundtrip(tmp_path: Path) -> None:
    repository = FileSystemDocumentRepository(tmp_path)
    document = Document(
        id="doc-1",
        filename="manual.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_path="/data/files/doc-1.pdf",
        sha256="abc",
        created_at=datetime.now(UTC),
        job_id="job-1",
    )

    await repository.save(document)
    loaded = await repository.get("doc-1")
    assert loaded == document
    assert await repository.list_all() == [document]
    with pytest.raises(BadRequestError):
        await repository.get("../../etc/passwd")
    await repository.delete("doc-1")
    assert await repository.list_all() == []


class UploadFake:
    async def execute(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> UploadedDocument:
        _ = filename, content_type, content
        return UploadedDocument(document_id="doc-1", job_id="job-1")


def test_upload_route_returns_202_camel_case() -> None:
    app = FastAPI()
    app.include_router(router)
    fake = UploadFake()
    app.dependency_overrides[get_upload_document_use_case] = lambda: fake

    with TestClient(app) as client:
        response = client.post(
            "/documents",
            files={"file": ("manual.pdf", b"%PDF-1.7 fixture", "application/pdf")},
        )

    assert response.status_code == 202
    assert response.json() == {"jobId": "job-1", "documentId": "doc-1"}


def test_upload_route_without_file_is_422() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_upload_document_use_case] = lambda: UploadFake()

    with TestClient(app) as client:
        response = client.post("/documents")

    assert response.status_code == 422
