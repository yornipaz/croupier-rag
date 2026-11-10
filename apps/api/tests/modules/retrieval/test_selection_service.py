from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.retrieval.application.selection_service import (
    SelectionConfig,
    SelectionService,
)
from app.modules.retrieval.domain.gate import SelectionCalibration, SignalThreshold
from tests.modules.chat.helpers import retrieval_result


class FakeCalibration:
    def __init__(self, calibration: SelectionCalibration | None) -> None:
        self.calibration = calibration

    async def load(self) -> SelectionCalibration | None:
        return self.calibration


def _config(mode: str = "dynamic") -> SelectionConfig:
    return SelectionConfig(
        mode=mode,  # type: ignore[arg-type]
        min_k=1,
        max_k=4,
        rel_ratio=0.5,
        gap_ratio=1.0,
        mmr_lambda=0.7,
        duplicate_threshold=0.95,
        context_token_budget=1000,
        token_estimate_factor=1.0,
    )


def _chunks() -> tuple[object, ...]:
    chunks = retrieval_result().chunks
    vectors = ((1.0, 0.0), (0.0, 1.0))
    return tuple(
        replace(item, dense_vector=vector, sparse_indices=(index + 1,))
        for index, (item, vector) in enumerate(zip(chunks, vectors, strict=True))
    )


def _calibration(*, reject_dense: float, reject_lexical: float) -> SelectionCalibration:
    return SelectionCalibration(
        embedding_model="model",
        signals_used=("denseTop1", "lexicalCoverage"),
        thresholds={
            "denseTop1": SignalThreshold(reject=reject_dense, accept=0.9),
            "lexicalCoverage": SignalThreshold(reject=reject_lexical, accept=0.9),
        },
        margin=0.05,
        n_calibration=10,
        created_at="2026-01-01T00:00:00Z",
        rel_ratio=0.5,
        gap_ratio=1.0,
    )


@pytest.mark.asyncio
async def test_static_mode_keeps_the_previous_chunk_order() -> None:
    chunks = _chunks()
    service = SelectionService(_config("static"))

    outcome = await service.select(chunks, query_term_ids=(1,))

    assert outcome.chunks == chunks
    assert outcome.debug.mode == "static"
    assert outcome.debug.decision == "ACCEPT"
    assert outcome.debug.dropped == ()


@pytest.mark.asyncio
async def test_dynamic_gate_reject_returns_no_chunks() -> None:
    chunks = _chunks()
    service = SelectionService(
        _config(),
        calibration=FakeCalibration(
            _calibration(reject_dense=0.95, reject_lexical=0.6)
        ),
    )

    outcome = await service.select(chunks, query_term_ids=(99,))

    assert outcome.debug.decision == "REJECT"
    assert outcome.chunks == ()
    assert outcome.debug.kept == ()


@pytest.mark.asyncio
async def test_dynamic_mode_applies_cutoff_and_packer() -> None:
    chunks = _chunks()
    service = SelectionService(
        _config(),
        calibration=FakeCalibration(
            _calibration(reject_dense=0.1, reject_lexical=0.1)
        ),
    )

    outcome = await service.select(chunks, query_term_ids=(1, 2))

    assert outcome.debug.decision in {"ACCEPT", "UNSURE"}
    assert len(outcome.chunks) <= len(chunks)
    assert outcome.debug.kept
