from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.calibration import calibrate_gate  # noqa: E402


def _row(
    *,
    refuse: bool,
    dense: float,
    lexical: float,
    separation: float = 0.1,
) -> dict[str, object]:
    return {
        "shouldRefuse": refuse,
        "denseTop1": dense,
        "lexicalCoverage": lexical,
        "denseSeparation": separation,
    }


def test_calibration_enables_gate_when_classes_are_separated() -> None:
    rows = [
        _row(refuse=False, dense=0.80, lexical=0.90),
        _row(refuse=False, dense=0.90, lexical=1.00),
        _row(refuse=True, dense=0.20, lexical=0.10),
        _row(refuse=True, dense=0.30, lexical=0.20),
    ]

    signals, thresholds, caught = calibrate_gate(rows, margin=0.05)

    assert signals == ("denseTop1", "lexicalCoverage")
    assert caught == 2
    assert thresholds["denseTop1"]["reject"] == 0.80 * 0.95


def test_calibration_disables_gate_when_classes_overlap() -> None:
    rows = [
        _row(refuse=False, dense=0.50, lexical=0.50),
        _row(refuse=False, dense=0.90, lexical=0.90),
        _row(refuse=True, dense=0.49, lexical=0.49),
        _row(refuse=True, dense=0.95, lexical=0.95),
    ]

    signals, thresholds, caught = calibrate_gate(rows, margin=0.05)

    assert signals == ()
    assert thresholds == {}
    assert caught == 0
