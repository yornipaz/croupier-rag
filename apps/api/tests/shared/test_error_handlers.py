from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.shared.errors import DocumentNotFoundError, ValidationError
from app.shared.exception_handlers import register_exception_handlers
from app.shared.middleware import RequestContextMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise DocumentNotFoundError("document 42 does not exist")

    @app.get("/invalid")
    async def invalid() -> None:
        raise ValidationError("bad field", details={"field": "bbox"})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("super secret internal detail")

    return app


def test_typed_error_is_serialized_in_camel_case() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/missing", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "document_not_found"
    assert body["error"]["message"] == "document 42 does not exist"
    assert body["error"]["retryable"] is False
    assert body["error"]["requestId"] == "req-123"
    assert response.headers["x-request-id"] == "req-123"


def test_validation_error_details_are_kept() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/invalid")

    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "bbox"}


def test_unhandled_error_never_leaks_trace_or_message() -> None:
    with TestClient(_build_app(), raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An unexpected error occurred"
    assert "super secret" not in response.text
    assert "Traceback" not in response.text
    assert body["error"]["requestId"]


def test_unknown_route_returns_typed_envelope() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
