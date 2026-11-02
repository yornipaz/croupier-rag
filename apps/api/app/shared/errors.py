from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AppError(Exception):
    """Base typed error. Never leaks stack traces to the client."""

    code: str = "internal_error"
    http_status: int = 500
    retryable: bool = False

    def __init__(
        self,
        message: str = "Unexpected error",
        *,
        details: Mapping[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details or {})
        self.retry_after = retry_after


class BadRequestError(AppError):
    code = "bad_request"
    http_status = 400


class ValidationError(AppError):
    code = "validation_error"
    http_status = 422


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class DocumentNotFoundError(NotFoundError):
    code = "document_not_found"


class JobNotFoundError(NotFoundError):
    code = "job_not_found"


class IngestionCancelledError(AppError):
    """The document/job disappeared while background ingestion was running."""

    code = "ingestion_cancelled"
    http_status = 409


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    http_status = 413


class UnsupportedMediaTypeError(AppError):
    code = "unsupported_media_type"
    http_status = 415


class AuthenticationError(AppError):
    """Provider rejected our credentials (401/403). Retrying cannot help."""

    code = "authentication_error"
    http_status = 401


class ConfigurationError(AppError):
    code = "configuration_error"
    http_status = 503


class LLMNotConfiguredError(ConfigurationError):
    code = "llm_not_configured"


class EmbeddingNotConfiguredError(ConfigurationError):
    code = "embedding_not_configured"


class UpstreamError(AppError):
    code = "upstream_error"
    http_status = 502
    retryable = True


class UpstreamTimeoutError(UpstreamError):
    code = "upstream_timeout"
    http_status = 504


class RateLimitedError(AppError):
    code = "rate_limited"
    http_status = 429
    retryable = True


class CircuitOpenError(AppError):
    code = "circuit_open"
    http_status = 503
    retryable = False

    def __init__(
        self,
        breaker_name: str,
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            f"Service temporarily unavailable: '{breaker_name}' circuit is open",
            details={"breaker": breaker_name},
            retry_after=retry_after,
        )
