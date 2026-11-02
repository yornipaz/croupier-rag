from __future__ import annotations

import asyncio
from collections.abc import Sequence

from app.modules.health.application.dto.health import HealthReport, ProbeResult
from app.modules.health.application.ports.health import HealthProbe


class CheckHealthUseCase:
    """Runs every probe concurrently and aggregates readiness."""

    def __init__(self, probes: Sequence[HealthProbe]) -> None:
        self._probes = tuple(probes)

    async def execute(self) -> HealthReport:
        results = await asyncio.gather(*(self._run(probe) for probe in self._probes))
        critical_ok = all(
            result.ok for probe, result in zip(self._probes, results, strict=True) if probe.critical
        )
        return HealthReport(
            status="ok" if critical_ok else "degraded",
            checks=tuple(results),
        )

    async def _run(self, probe: HealthProbe) -> ProbeResult:
        try:
            return await probe.check()
        except Exception as exc:  # a broken probe must never break readiness
            return ProbeResult(name=probe.name, ok=False, detail=type(exc).__name__)
