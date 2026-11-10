from __future__ import annotations

from app.modules.retrieval.domain.cutoff import (
    REASON_BELOW_RATIO,
    REASON_GAP,
    adaptive_cutoff,
)


def test_cutoff_keeps_min_k_and_stops_below_relative_ratio() -> None:
    result = adaptive_cutoff(
        [1.0, 0.9, 0.8, 0.2, 0.1],
        rel_ratio=0.5,
        gap_ratio=1.0,
        min_k=2,
        max_k=5,
    )

    assert result.kept == (0, 1, 2)
    assert result.dropped == ((3, REASON_BELOW_RATIO), (4, REASON_BELOW_RATIO))


def test_cutoff_stops_at_consecutive_gap() -> None:
    result = adaptive_cutoff(
        [1.0, 0.95, 0.4, 0.39],
        rel_ratio=0.1,
        gap_ratio=0.3,
        min_k=2,
        max_k=4,
    )

    assert result.kept == (0, 1)
    assert result.dropped == ((2, REASON_GAP), (3, REASON_GAP))


def test_cutoff_honours_max_k() -> None:
    result = adaptive_cutoff(
        [1.0, 0.99, 0.98, 0.97],
        rel_ratio=0.0,
        gap_ratio=1.0,
        min_k=1,
        max_k=2,
    )

    assert result.kept == (0, 1)
    assert result.dropped == ((2, REASON_BELOW_RATIO), (3, REASON_BELOW_RATIO))


def test_cutoff_handles_empty_and_zero_scores() -> None:
    empty = adaptive_cutoff([], rel_ratio=0.5, gap_ratio=0.3, min_k=2, max_k=4)
    zeros = adaptive_cutoff([0.0, 0.0, 0.0], rel_ratio=0.5, gap_ratio=0.3, min_k=2, max_k=4)

    assert empty.kept == ()
    assert zeros.kept == (0, 1)
    assert zeros.dropped == ((2, REASON_BELOW_RATIO),)
