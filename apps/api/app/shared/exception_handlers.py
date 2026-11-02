from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.context import get_request_id
from app.shared.errors import AppError
from app.shared.logging import get_logger
from app.shared.schemas import CamelModel

logger = get_logger(__name__)


class ErrorDetail(CamelModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(CamelModel):
    error: ErrorDetail


def _request_id_from(request: Request) -> str | None:
    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str) and state_id:
        return state_id
    return get_request_id() or request.headers.get("x-request-id")


def _payload(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    retry_after: float | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
            request_id=_request_id_from(request),
        )
    )
    headers = {"Retry-After": str(max(1, round(retry_after)))} if retry_after else None
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(by_alias=True, mode="json"),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.http_status >= 500:
            logger.warning("app_error", code=exc.code, message=exc.message, details=exc.details)
        return _payload(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.http_status,
            retryable=exc.retryable,
            details=exc.details,
            retry_after=exc.retry_after,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
            for error in exc.errors()
        ]
        return _payload(
            request,
            code="validation_error",
            message="Request validation failed",
            status_code=422,
            details={"errors": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = "Resource not found" if exc.status_code == 404 else str(exc.detail)
        return _payload(request, code=code, message=message, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error_type=type(exc).__name__)
        return _payload(
            request,
            code="internal_error",
            message="An unexpected error occurred",
            status_code=500,
        )
