from __future__ import annotations

from app.modules.retrieval.domain.gate import (
    GateDecision,
    GateSignals,
    SelectionCalibration,
    SignalThreshold,
    evaluate_gate,
)


def _calibration(
    *,
    dense_reject: float = 0.5,
    lexical_reject: float = 0.6,
) -> SelectionCalibration:
    return SelectionCalibration(
        embedding_model="model",
        signals_used=("denseTop1", "lexicalCoverage"),
        thresholds={
            "denseTop1": SignalThreshold(reject=dense_reject, accept=0.8),
            "lexicalCoverage": SignalThreshold(reject=lexical_reject, accept=0.9),
        },
        margin=0.05,
        n_calibration=10,
        created_at="2026-01-01T00:00:00Z",
        rel_ratio=0.55,
        gap_ratio=0.35,
    )


def test_gate_rejects_only_when_both_signals_are_low() -> None:
    result = evaluate_gate(
        GateSignals(dense_top1=0.4, dense_separation=0.1, lexical_coverage=0.3),
        _calibration(),
    )

    assert result.decision is GateDecision.REJECT
    assert result.enabled is True


def test_gate_does_not_reject_when_one_signal_is_healthy() -> None:
    result = evaluate_gate(
        GateSignals(dense_top1=0.4, dense_separation=0.1, lexical_coverage=0.95),
        _calibration(),
    )

    assert result.decision is GateDecision.UNSURE


def test_gate_accepts_when_both_signals_are_high() -> None:
    result = evaluate_gate(
        GateSignals(dense_top1=0.9, dense_separation=0.2, lexical_coverage=0.95),
        _calibration(),
    )

    assert result.decision is GateDecision.ACCEPT


def test_gate_is_disabled_without_calibration() -> None:
    result = evaluate_gate(
        GateSignals(dense_top1=0.0, dense_separation=0.0, lexical_coverage=0.0),
        None,
    )

    assert result.decision is GateDecision.ACCEPT
    assert result.enabled is False


def test_gate_never_rejects_the_lowest_calibration_answerable() -> None:
    lowest = GateSignals(dense_top1=0.51, dense_separation=0.0, lexical_coverage=0.61)

    result = evaluate_gate(lowest, _calibration())

    assert result.decision is not GateDecision.REJECT
