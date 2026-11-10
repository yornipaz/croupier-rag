from __future__ import annotations

from app.modules.retrieval.domain.candidates import Candidate
from app.modules.retrieval.domain.cutoff import REASON_BUDGET, REASON_DUPLICATE
from app.modules.retrieval.domain.packer import mmr_pack


def _candidate(
    index: int,
    relevance: float,
    vector: tuple[float, ...],
    *,
    tokens: int = 10,
    kind: str = "text",
) -> Candidate:
    return Candidate(
        index=index,
        chunk_id=f"c{index}",
        page=index + 1,
        relevance=relevance,
        token_count=tokens,
        kind=kind,
        dense_vector=vector,
    )


def test_packer_drops_near_duplicates() -> None:
    candidates = [
        _candidate(0, 0.9, (1.0, 0.0)),
        _candidate(1, 0.8, (1.0, 0.0)),
        _candidate(2, 0.7, (0.0, 1.0)),
    ]

    result = mmr_pack(
        candidates,
        budget_tokens=100,
        token_estimate_factor=1.0,
        mmr_lambda=0.7,
        duplicate_threshold=0.95,
    )

    assert result.kept == (0, 2)
    assert result.dropped == ((1, REASON_DUPLICATE),)


def test_packer_respects_token_budget_and_factor() -> None:
    candidates = [
        _candidate(0, 0.9, (1.0, 0.0)),
        _candidate(1, 0.8, (0.0, 1.0)),
    ]

    result = mmr_pack(
        candidates,
        budget_tokens=15,
        token_estimate_factor=1.0,
        mmr_lambda=1.0,
        duplicate_threshold=0.99,
    )
    factor_result = mmr_pack(
        candidates,
        budget_tokens=10,
        token_estimate_factor=1.32,
        mmr_lambda=1.0,
        duplicate_threshold=0.99,
    )

    assert result.kept == (0,)
    assert result.dropped == ((1, REASON_BUDGET),)
    assert factor_result.kept == ()
    assert {reason for _, reason in factor_result.dropped} == {REASON_BUDGET}


def test_packer_prefers_diverse_candidate_over_near_duplicate() -> None:
    candidates = [
        _candidate(0, 0.9, (1.0, 0.0)),
        _candidate(1, 0.85, (0.95, 0.05)),
        _candidate(2, 0.6, (0.0, 1.0)),
    ]

    result = mmr_pack(
        candidates,
        budget_tokens=100,
        token_estimate_factor=1.0,
        mmr_lambda=0.7,
        duplicate_threshold=0.99,
    )

    assert result.kept[:2] == (0, 2)


def test_packer_keeps_table_whole() -> None:
    table = _candidate(0, 0.9, (1.0, 0.0), tokens=40, kind="table")

    result = mmr_pack(
        [table],
        budget_tokens=100,
        token_estimate_factor=1.0,
        mmr_lambda=0.7,
        duplicate_threshold=0.95,
    )

    assert result.kept == (0,)
    assert result.dropped == ()
