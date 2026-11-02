from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from qdrant_client import AsyncQdrantClient

from app.config.settings import Settings
from app.modules.documents.application.ports.document_repository import (
    DocumentRepositoryPort,
)
from app.modules.documents.application.use_cases.delete_document import DeleteDocumentUseCase
from app.modules.documents.application.use_cases.get_document import GetDocumentUseCase
from app.modules.documents.application.use_cases.list_documents import ListDocumentsUseCase
from app.modules.documents.application.use_cases.render_page_crop import RenderPageCropUseCase
from app.modules.documents.application.use_cases.upload_document import UploadDocumentUseCase
from app.modules.documents.infrastructure.celery_dispatcher import CeleryIngestionDispatcher
from app.modules.documents.infrastructure.document_repository import FileSystemDocumentRepository
from app.modules.documents.infrastructure.filesystem import FileSystemStorage
from app.modules.documents.infrastructure.pymupdf_renderer import PyMuPDFPageRenderer
from app.modules.documents.infrastructure.qdrant_deleter import QdrantVectorDeleter
from app.modules.documents.presentation.router import router
from app.modules.ingestion.application.ports.jobs import JobRepositoryPort

__all__ = [
    "DocumentServices",
    "build_document_services",
    "build_documents_module",
    "build_documents_router",
    "router",
]


@dataclass(frozen=True, slots=True)
class DocumentServices:
    repository: DocumentRepositoryPort
    upload: UploadDocumentUseCase
    list_documents: ListDocumentsUseCase
    get_document: GetDocumentUseCase
    delete_document: DeleteDocumentUseCase
    render_page_crop: RenderPageCropUseCase


def build_document_services(
    settings: Settings,
    *,
    qdrant: AsyncQdrantClient,
    job_repository: JobRepositoryPort,
) -> DocumentServices:
    data_dir = settings.resolved_data_dir
    files = FileSystemStorage(data_dir)
    documents = FileSystemDocumentRepository(data_dir)
    pages = PyMuPDFPageRenderer(
        files,
        data_dir / "cache" / "crops",
        margin_pt=settings.crop_margin_pt,
        dpi=settings.crop_dpi,
    )
    vectors = QdrantVectorDeleter(qdrant, settings.qdrant_collection)
    dispatcher = CeleryIngestionDispatcher()

    return DocumentServices(
        repository=documents,
        upload=UploadDocumentUseCase(
            documents,
            files,
            job_repository,
            dispatcher,
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        ),
        list_documents=ListDocumentsUseCase(documents),
        get_document=GetDocumentUseCase(documents),
        delete_document=DeleteDocumentUseCase(
            documents,
            files,
            job_repository,
            vectors,
            pages,
        ),
        render_page_crop=RenderPageCropUseCase(pages),
    )


def build_documents_router(settings: Settings) -> APIRouter:
    _ = settings
    return router


def build_documents_module(settings: Settings) -> APIRouter:
    return build_documents_router(settings)
