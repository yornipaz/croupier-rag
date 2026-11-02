from __future__ import annotations

from typing import Protocol

from app.modules.health.application.dto.health import ProbeResult


class HealthProbe(Protocol):
    name: str
    critical: bool

    async def check(self) -> ProbeResult: ...
