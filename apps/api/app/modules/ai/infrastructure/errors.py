from __future__ import annotations

import httpx
from google.genai import errors as genai_errors

from app.shared.errors import (
    AppError,
    AuthenticationError,
    BadRequestError,
    RateLimitedError,
    UpstreamError,
    UpstreamTimeoutError,
)

_MAX_DETAIL = 500


def _details(
    provider: str,
    exc: BaseException,
    status_code: int | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "provider": provider,
        "errorType": type(exc).__name__,
    }
    if status_code is not None:
        details["statusCode"] = status_code
    return details


def _status_code(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    if isinstance(exc, genai_errors.APIError):
        code: object = getattr(exc, "code", None)
        if isinstance(code, int):
            return code
        if isinstance(code, str) and code.isdigit():
            return int(code)
    return None


def map_http_status(provider: str, status_code: int, message: str) -> AppError:
    """Map an upstream HTTP status to the project error taxonomy.

    429 and 5xx are retryable; 400/401/403 are not. A 408 is a timeout and is
    therefore retryable.
    """
    details = {"provider": provider, "statusCode": status_code}
    if status_code == 429:
        return RateLimitedError(message, details=details)
    if status_code in (401, 403):
        return AuthenticationError(message, details=details)
    if status_code == 408:
        return UpstreamTimeoutError(message, details=details)
    if 400 <= status_code < 500:
        return BadRequestError(message, details=details)
    if status_code >= 500:
        return UpstreamError(message, details=details)
    return UpstreamError(message, details=details)


def map_provider_exception(provider: str, exc: BaseException) -> AppError:
    """Convert SDK/HTTP/SDK-specific exceptions into ``AppError`` instances."""
    if isinstance(exc, AppError):
        return exc

    status_code = _status_code(exc)
    message = f"{provider} request failed"
    if status_code is not None:
        reason = str(exc).strip()
        if reason:
            message = f"{provider} returned HTTP {status_code}: {reason[:_MAX_DETAIL]}"
        return map_http_status(provider, status_code, message)

    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return UpstreamTimeoutError(
            f"{provider} request timed out",
            details=_details(provider, exc),
        )

    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
        return UpstreamError(
            f"{provider} transport error: {type(exc).__name__}",
            details=_details(provider, exc),
        )

    # SDK-specific failures that do not expose a status code are still an
    # upstream failure. Unknown programming errors remain visible in details.
    reason = str(exc).strip()
    return UpstreamError(
        f"{provider} request failed: {reason[:_MAX_DETAIL] or type(exc).__name__}",
        details=_details(provider, exc),
    )
