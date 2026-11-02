from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.health.application.dto.health import ProbeResult
from app.modules.health.application.use_cases.check_health import CheckHealthUseCase
from app.modules.health.presentation.router import router


@dataclass
class FakeProbe:
    name: str
    ok: bool
    critical: bool = True

    async def check(self) -> ProbeResult:
        return ProbeResult(name=self.name, ok=self.ok)


class ExplodingProbe:
    name = "exploding"
    critical = True

    async def check(self) -> ProbeResult:
        raise RuntimeError("probe exploded")


def _app(use_case: CheckHealthUseCase) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(check_health=use_case)
    app.include_router(router)
    return app


def test_health_ok_reports_every_check() -> None:
    use_case = CheckHealthUseCase([FakeProbe("redis", True), FakeProbe("qdrant", True)])

    with TestClient(_app(use_case)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": [
            {"name": "redis", "ok": True, "detail": None},
            {"name": "qdrant", "ok": True, "detail": None},
        ],
    }


def test_health_degraded_when_critical_probe_fails() -> None:
    use_case = CheckHealthUseCase([FakeProbe("redis", False), FakeProbe("qdrant", True)])

    with TestClient(_app(use_case)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_non_critical_failure_keeps_service_ready() -> None:
    use_case = CheckHealthUseCase(
        [FakeProbe("redis", True), FakeProbe("vector-store", False, critical=False)]
    )

    with TestClient(_app(use_case)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_broken_probe_is_contained() -> None:
    use_case = CheckHealthUseCase([ExplodingProbe()])

    with TestClient(_app(use_case)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"][0]["detail"] == "RuntimeError"
