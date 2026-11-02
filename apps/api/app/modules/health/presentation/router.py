from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.modules.health.application.use_cases.check_health import CheckHealthUseCase
from app.modules.health.presentation.schemas import HealthCheckSchema, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


def get_check_health_use_case(request: Request) -> CheckHealthUseCase:
    use_case: CheckHealthUseCase = request.app.state.container.check_health
    return use_case


@router.get("", response_model=HealthResponse)
async def health(
    response: Response,
    use_case: Annotated[CheckHealthUseCase, Depends(get_check_health_use_case)],
) -> HealthResponse:
    """Readiness probe: Redis + Qdrant are checked concurrently with timeouts."""
    report = await use_case.execute()
    if report.status != "ok":
        response.status_code = 503
    return HealthResponse(
        status=report.status,
        checks=[
            HealthCheckSchema(name=check.name, ok=check.ok, detail=check.detail)
            for check in report.checks
        ],
    )
