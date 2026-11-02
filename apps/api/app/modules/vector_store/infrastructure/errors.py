from __future__ import annotations

import httpx
from qdrant_client.http import exceptions as qdrant_exceptions

from app.shared.errors import (
    AppError,
    AuthenticationError,
    BadRequestError,
    RateLimitedError,
    UpstreamError,
    UpstreamTimeoutError,
)


def map_qdrant_exception(exc: BaseException) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return UpstreamTimeoutError("Qdrant request timed out")
    if isinstance(exc, httpx.TransportError):
        return UpstreamError("Qdrant transport error")
    if isinstance(exc, qdrant_exceptions.UnexpectedResponse):
        status = exc.status_code
        message = f"Qdrant returned HTTP {status}"
        if status == 429:
            return RateLimitedError(message)
        if status in (401, 403):
            return AuthenticationError(message)
        if status == 408:
            return UpstreamTimeoutError(message)
        if status is not None and 400 <= status < 500:
            return BadRequestError(message)
        return UpstreamError(message, details={"statusCode": status})
    if isinstance(exc, qdrant_exceptions.ResponseHandlingException):
        return UpstreamError("Qdrant response handling error")
    return UpstreamError(
        f"Qdrant request failed: {type(exc).__name__}",
        details={"errorType": type(exc).__name__},
    )
