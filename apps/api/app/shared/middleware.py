from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.shared.context import reset_request_id, set_request_id
from app.shared.logging import get_logger

logger = get_logger(__name__)

_REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    """Pure ASGI middleware: binds a request id to structlog and the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)
        structlog.contextvars.bind_contextvars(
            http_method=scope["method"],
            http_path=scope["path"],
        )

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers: list[tuple[bytes, bytes]] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                response_headers.append((_REQUEST_ID_HEADER, request_id.encode()))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "http.request.completed",
                status_code=status_code,
                duration_ms=duration_ms,
            )
            reset_request_id(token)
            structlog.contextvars.clear_contextvars()


def get_header(headers: Any, name: str) -> str | None:
    value = headers.get(name)
    return str(value) if value is not None else None
