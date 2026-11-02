from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: Literal["ok", "degraded"]
    checks: tuple[ProbeResult, ...]
