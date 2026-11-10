from __future__ import annotations

from typing import Protocol

from app.modules.retrieval.domain.gate import SelectionCalibration


class CalibrationStorePort(Protocol):
    async def load(self) -> SelectionCalibration | None: ...
