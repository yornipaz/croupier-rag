from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

REASON_BELOW_RATIO = "below_ratio"
REASON_GAP = "gap"
REASON_DUPLICATE = "duplicate"
REASON_BUDGET = "budget"


@dataclass(frozen=True, slots=True)
class CutoffResult:
    kept: tuple[int, ...]
    dropped: tuple[tuple[int, str], ...]


def adaptive_cutoff(
    scores: Sequence[float],
    *,
    rel_ratio: float,
    gap_ratio: float,
    min_k: int,
    max_k: int,
) -> CutoffResult:
    """Keep relevance-sorted candidates until a ratio or consecutive gap fails.

    Returned indices refer to the input sequence, ordered by descending score.
    """
    if not scores:
        return CutoffResult(kept=(), dropped=())
    order = tuple(sorted(range(len(scores)), key=lambda index: scores[index], reverse=True))
    if not order:
        return CutoffResult(kept=(), dropped=())
    top = max(float(after) for after in scores)
    if top <= 0.0:
        fallback_kept = order[: min(min_k, len(order))]
        fallback_dropped = tuple(
            (index, REASON_BELOW_RATIO) for index in order[len(fallback_kept) :]
        )
        return CutoffResult(kept=fallback_kept, dropped=fallback_dropped)

    kept: list[int] = []
    dropped: list[tuple[int, str]] = []
    previous: float | None = None
    failure_reason: str | None = None
    for rank, index in enumerate(order, start=1):
        score = float(scores[index])
        if failure_reason is not None:
            dropped.append((index, failure_reason))
            continue
        if rank > max_k:
            dropped.append((index, REASON_BELOW_RATIO))
            continue
        if rank <= min_k:
            kept.append(index)
            previous = score
            continue
        below_ratio = score / top < rel_ratio
        gap = previous is not None and previous > 0 and (previous - score) / previous > gap_ratio
        if below_ratio:
            failure_reason = REASON_BELOW_RATIO
            dropped.append((index, failure_reason))
            continue
        if gap:
            failure_reason = REASON_GAP
            dropped.append((index, failure_reason))
            continue
        kept.append(index)
        previous = score
    return CutoffResult(kept=tuple(kept), dropped=tuple(dropped))
