from __future__ import annotations

from contextvars import ContextVar, Token

import structlog

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)


def set_request_id(value: str) -> Token[str | None]:
    token = _request_id.set(value)
    structlog.contextvars.bind_contextvars(request_id=value)
    return token


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def bind_job_id(job_id: str) -> Token[str | None]:
    token = _job_id.set(job_id)
    structlog.contextvars.bind_contextvars(job_id=job_id)
    return token


def reset_job_id(token: Token[str | None]) -> None:
    _job_id.reset(token)


def get_job_id() -> str | None:
    return _job_id.get()
