from __future__ import annotations

from typing import Literal

from app.shared.schemas import CamelModel


class HealthCheckSchema(CamelModel):
    name: str
    ok: bool
    detail: str | None = None


class HealthResponse(CamelModel):
    status: Literal["ok", "degraded"]
    checks: list[HealthCheckSchema]
