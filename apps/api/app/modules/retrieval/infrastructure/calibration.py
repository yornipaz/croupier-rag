from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.modules.retrieval.domain.gate import (
    SIGNAL_NAMES,
    SelectionCalibration,
    SignalThreshold,
)
from app.shared.logging import get_logger

logger = get_logger(__name__)


class FileCalibrationStore:
    """Load ``DATA_DIR/calibration.json`` and invalidate it on model mismatch."""

    def __init__(self, path: Path, *, expected_embedding_model: str) -> None:
        self._path = path
        self._expected_model = expected_embedding_model
        self._cached_mtime: float | None = None
        self._cached: SelectionCalibration | None = None

    async def load(self) -> SelectionCalibration | None:
        if not self._path.exists():
            logger.warning("retrieval.calibration_missing", path=str(self._path))
            return None
        mtime = self._path.stat().st_mtime
        if self._cached_mtime == mtime:
            return self._cached
        calibration = await asyncio.to_thread(self._read)
        self._cached_mtime = mtime
        self._cached = calibration
        return calibration

    def _read(self) -> SelectionCalibration | None:
        try:
            payload: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("retrieval.calibration_invalid", path=str(self._path), error=str(exc))
            return None

        model = str(payload.get("embeddingModel") or "")
        if model != self._expected_model:
            logger.warning(
                "retrieval.calibration_model_mismatch",
                expected=self._expected_model,
                found=model,
            )
            return None

        signals_used = tuple(str(name) for name in payload.get("signalsUsed") or [])
        if len(signals_used) != 2 or any(name not in SIGNAL_NAMES for name in signals_used):
            logger.warning("retrieval.calibration_signals_invalid")
            return None
        raw_thresholds = payload.get("thresholds") or {}
        thresholds: dict[str, SignalThreshold] = {}
        for name in signals_used:
            raw = raw_thresholds.get(name) or {}
            thresholds[name] = SignalThreshold(
                reject=float(raw.get("reject", 0.0)),
                accept=float(raw.get("accept", 1.0)),
            )
        cutoff = payload.get("cutoff") or {}
        return SelectionCalibration(
            embedding_model=model,
            signals_used=signals_used,
            thresholds=thresholds,
            margin=float(payload.get("margin", 0.0)),
            n_calibration=int(payload.get("nCalibration", 0)),
            created_at=str(payload.get("createdAt", "")),
            rel_ratio=float(cutoff.get("relRatio", 0.55)),
            gap_ratio=float(cutoff.get("gapRatio", 0.35)),
        )
