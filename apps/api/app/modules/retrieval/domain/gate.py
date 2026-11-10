from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SIGNAL_DENSE_TOP1 = "denseTop1"
SIGNAL_DENSE_SEPARATION = "denseSeparation"
SIGNAL_LEXICAL_COVERAGE = "lexicalCoverage"
SIGNAL_NAMES = (SIGNAL_DENSE_TOP1, SIGNAL_DENSE_SEPARATION, SIGNAL_LEXICAL_COVERAGE)


class GateDecision(StrEnum):
    REJECT = "REJECT"
    ACCEPT = "ACCEPT"
    UNSURE = "UNSURE"


@dataclass(frozen=True, slots=True)
class GateSignals:
    dense_top1: float
    dense_separation: float
    lexical_coverage: float

    def value(self, name: str) -> float:
        if name == SIGNAL_DENSE_TOP1:
            return self.dense_top1
        if name == SIGNAL_DENSE_SEPARATION:
            return self.dense_separation
        if name == SIGNAL_LEXICAL_COVERAGE:
            return self.lexical_coverage
        raise ValueError(f"unknown gate signal: {name}")


@dataclass(frozen=True, slots=True)
class SignalThreshold:
    reject: float
    accept: float


@dataclass(frozen=True, slots=True)
class SelectionCalibration:
    embedding_model: str
    signals_used: tuple[str, ...]
    thresholds: dict[str, SignalThreshold]
    margin: float
    n_calibration: int
    created_at: str
    rel_ratio: float
    gap_ratio: float


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: GateDecision
    enabled: bool
    signals_used: tuple[str, ...]
    thresholds: dict[str, float]


def evaluate_gate(
    signals: GateSignals,
    calibration: SelectionCalibration | None,
) -> GateResult:
    """Conservative two-signal gate.

    REJECT only when *all* calibrated signals are below their reject threshold.
    The calibration step sets those thresholds below every answerable question
    (minus a safety margin), so this rule never rejects a calibration
    answerable in practice.
    """
    if calibration is None or len(calibration.signals_used) != 2:
        return GateResult(
            decision=GateDecision.ACCEPT,
            enabled=False,
            signals_used=(),
            thresholds={},
        )
    signals_used = calibration.signals_used
    if any(name not in SIGNAL_NAMES for name in signals_used):
        return GateResult(
            decision=GateDecision.ACCEPT,
            enabled=False,
            signals_used=(),
            thresholds={},
        )

    values = {name: signals.value(name) for name in signals_used}
    reject_thresholds = {
        name: calibration.thresholds[name].reject for name in signals_used
    }
    accept_thresholds = {
        name: calibration.thresholds[name].accept for name in signals_used
    }
    if all(values[name] < reject_thresholds[name] for name in signals_used):
        decision = GateDecision.REJECT
    elif all(values[name] >= accept_thresholds[name] for name in signals_used):
        decision = GateDecision.ACCEPT
    else:
        decision = GateDecision.UNSURE
    return GateResult(
        decision=decision,
        enabled=True,
        signals_used=signals_used,
        thresholds=reject_thresholds,
    )
