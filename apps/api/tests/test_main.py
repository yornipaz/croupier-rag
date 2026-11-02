from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.main import OPENAPI_TAGS, create_app
from app.modules.health.application.dto.health import ProbeResult
from app.modules.health.application.use_cases.check_health import CheckHealthUseCase
from app.modules.health.presentation.router import get_check_health_use_case


@dataclass
class OkProbe:
    name: str
    critical: bool = True

    async def check(self) -> ProbeResult:
        return ProbeResult(name=self.name, ok=True)


def _ok_use_case() -> CheckHealthUseCase:
    return CheckHealthUseCase([OkProbe("redis"), OkProbe("qdrant")])


def test_health_and_docs_are_exposed() -> None:
    app = create_app()
    app.dependency_overrides[get_check_health_use_case] = _ok_use_case

    with TestClient(app) as client:
        health = client.get("/health")
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert openapi.status_code == 200


def test_openapi_tags_are_ordered() -> None:
    app = create_app()
    app.dependency_overrides[get_check_health_use_case] = _ok_use_case

    with TestClient(app) as client:
        document = client.get("/openapi.json").json()

    assert [tag["name"] for tag in document["tags"]] == [tag["name"] for tag in OPENAPI_TAGS]
    assert "/health" in document["paths"]


def test_unknown_route_uses_error_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_check_health_use_case] = _ok_use_case

    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
