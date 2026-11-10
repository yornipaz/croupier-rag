"""Pure calibration helpers for the evaluation harness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

from app.modules.retrieval.domain.cutoff import adaptive_cutoff

SIGNAL_ORDER = ("denseTop1", "lexicalCoverage", "denseSeparation")


def calibrate_gate(
    rows: Sequence[Mapping[str, Any]],
    margin: float,
) -> tuple[tuple[str, ...], dict[str, dict[str, float]], int]:
    answerable = [row for row in rows if not row["shouldRefuse"]]
    refusals = [row for row in rows if row["shouldRefuse"]]
    if not answerable or not refusals:
        return (), {}, 0

    best_signals: tuple[str, ...] = ()
    best_thresholds: dict[str, dict[str, float]] = {}
    best_caught = 0
    for pair in combinations(SIGNAL_ORDER, 2):
        thresholds: dict[str, dict[str, float]] = {}
        for signal in pair:
            minimum = min(float(row[signal]) for row in answerable)
            maximum_refusal = max(float(row[signal]) for row in refusals)
            thresholds[signal] = {
                "reject": max(0.0, minimum * (1.0 - margin)),
                "accept": min(1.0, maximum_refusal * (1.0 + margin)),
            }
        caught = sum(
            1
            for row in refusals
            if all(float(row[signal]) < thresholds[signal]["reject"] for signal in pair)
        )
        if caught > best_caught:
            best_caught = caught
            best_signals = pair
            best_thresholds = thresholds
    if best_caught == 0:
        return (), {}, 0
    return best_signals, best_thresholds, best_caught


def calibrate_cutoff(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_k: int,
    max_k: int,
) -> tuple[float, float]:
    answerable = [
        row
        for row in rows
        if not row["shouldRefuse"] and row["expectedPages"] and row["denseScores"]
    ]
    if not answerable:
        return 0.3, 0.9

    best: tuple[int, float, float] | None = None
    for rel_ratio in [round(0.30 + 0.05 * index, 2) for index in range(14)]:
        for gap_ratio in [round(0.10 + 0.05 * index, 2) for index in range(17)]:
            total_kept = 0
            valid = True
            for row in answerable:
                scores = list(row["denseScores"])
                pages = list(row["pages"])
                result = adaptive_cutoff(
                    scores,
                    rel_ratio=rel_ratio,
                    gap_ratio=gap_ratio,
                    min_k=min_k,
                    max_k=max_k,
                )
                kept_pages = {pages[index] for index in result.kept if index < len(pages)}
                if not set(row["expectedPages"]).intersection(kept_pages):
                    valid = False
                    break
                total_kept += len(result.kept)
            if valid and (best is None or total_kept < best[0]):
                best = (total_kept, rel_ratio, gap_ratio)
    if best is None:
        return 0.30, 0.90
    return best[1], best[2]
