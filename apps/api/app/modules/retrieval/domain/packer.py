from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.retrieval.domain.candidates import Candidate
from app.modules.retrieval.domain.cutoff import REASON_BUDGET, REASON_DUPLICATE
from app.shared.vectors import cosine_similarity


@dataclass(frozen=True, slots=True)
class PackResult:
    kept: tuple[int, ...]
    dropped: tuple[tuple[int, str], ...]


def mmr_pack(
    candidates: Sequence[Candidate],
    *,
    budget_tokens: int,
    token_estimate_factor: float,
    mmr_lambda: float,
    duplicate_threshold: float,
) -> PackResult:
    """Select diverse, non-duplicate candidates within a token budget."""
    remaining = set(range(len(candidates)))
    selected: list[int] = []
    dropped: list[tuple[int, str]] = []
    used = 0.0

    while remaining:
        if selected:
            duplicate = next(
                (
                    index
                    for index in sorted(remaining)
                    if _max_similarity(candidates[index], candidates, selected)
                    >= duplicate_threshold
                ),
                None,
            )
            if duplicate is not None:
                remaining.remove(duplicate)
                dropped.append((duplicate, REASON_DUPLICATE))
                continue

        best = max(
            sorted(remaining),
            key=lambda index: _mmr_score(
                candidates[index],
                candidates,
                selected,
                mmr_lambda,
            ),
        )
        cost = candidates[best].token_count * token_estimate_factor
        if used + cost > budget_tokens:
            remaining.remove(best)
            dropped.append((best, REASON_BUDGET))
            continue
        remaining.remove(best)
        selected.append(best)
        used += cost

    return PackResult(kept=tuple(selected), dropped=tuple(dropped))


def _mmr_score(
    candidate: Candidate,
    candidates: Sequence[Candidate],
    selected: Sequence[int],
    mmr_lambda: float,
) -> float:
    if not selected:
        return candidate.relevance
    similarity = _max_similarity(candidate, candidates, selected)
    return mmr_lambda * candidate.relevance - (1.0 - mmr_lambda) * similarity


def _max_similarity(
    candidate: Candidate,
    candidates: Sequence[Candidate],
    selected: Sequence[int],
) -> float:
    dense_vector = candidate.dense_vector
    if not selected or dense_vector is None:
        return 0.0
    similarities: list[float] = []
    for index in selected:
        other = candidates[index].dense_vector
        if other is not None:
            similarities.append(cosine_similarity(dense_vector, other))
    return max(similarities, default=0.0)
