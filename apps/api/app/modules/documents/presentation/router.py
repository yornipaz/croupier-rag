from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile

from app.modules.documents.application.use_cases.delete_document import DeleteDocumentUseCase
from app.modules.documents.application.use_cases.get_document import GetDocumentUseCase
from app.modules.documents.application.use_cases.list_documents import ListDocumentsUseCase
from app.modules.documents.application.use_cases.render_page_crop import RenderPageCropUseCase
from app.modules.documents.application.use_cases.upload_document import UploadDocumentUseCase
from app.modules.documents.presentation.schemas import DocumentSchema, UploadDocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


def get_upload_document_use_case(request: Request) -> UploadDocumentUseCase:
    use_case: UploadDocumentUseCase = request.app.state.container.documents.upload
    return use_case


def get_list_documents_use_case(request: Request) -> ListDocumentsUseCase:
    use_case: ListDocumentsUseCase = request.app.state.container.documents.list_documents
    return use_case


def get_get_document_use_case(request: Request) -> GetDocumentUseCase:
    use_case: GetDocumentUseCase = request.app.state.container.documents.get_document
    return use_case


def get_delete_document_use_case(request: Request) -> DeleteDocumentUseCase:
    use_case: DeleteDocumentUseCase = request.app.state.container.documents.delete_document
    return use_case


def get_render_page_crop_use_case(request: Request) -> RenderPageCropUseCase:
    use_case: RenderPageCropUseCase = request.app.state.container.documents.render_page_crop
    return use_case


@router.post("", response_model=UploadDocumentResponse, status_code=202)
async def upload_document(
    file: Annotated[UploadFile, File(description="Technical manual in PDF format")],
    use_case: Annotated[UploadDocumentUseCase, Depends(get_upload_document_use_case)],
) -> UploadDocumentResponse:
    """Accept a PDF, persist it and enqueue its ingestion job."""
    filename = file.filename or "document.pdf"
    content_type = file.content_type
    try:
        content = await file.read()
    finally:
        await file.close()
    result = await use_case.execute(
        filename=filename,
        content_type=content_type,
        content=content,
    )
    return UploadDocumentResponse(job_id=result.job_id, document_id=result.document_id)


@router.get("", response_model=list[DocumentSchema])
async def list_documents(
    use_case: Annotated[ListDocumentsUseCase, Depends(get_list_documents_use_case)],
) -> list[DocumentSchema]:
    documents = await use_case.execute()
    return [DocumentSchema.from_document(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: str,
    use_case: Annotated[GetDocumentUseCase, Depends(get_get_document_use_case)],
) -> DocumentSchema:
    document = await use_case.execute(document_id)
    return DocumentSchema.from_document(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    use_case: Annotated[DeleteDocumentUseCase, Depends(get_delete_document_use_case)],
) -> Response:
    await use_case.execute(document_id)
    return Response(status_code=204)


@router.get(
    "/{document_id}/pages/{page_number}/crop",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def page_crop(
    document_id: str,
    page_number: Annotated[int, Path(ge=1)],
    bbox: Annotated[str, Query(min_length=7, description="x0,y0,x1,y1 in PDF points")],
    use_case: Annotated[RenderPageCropUseCase, Depends(get_render_page_crop_use_case)],
    highlight: bool = True,
) -> Response:
    png = await use_case.execute(document_id, page_number, bbox, highlight=highlight)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )
