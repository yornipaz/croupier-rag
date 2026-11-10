from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.retrieval.application.dto.retrieval import (
    RetrievedChunk,
    SelectionDebug,
    SelectionDrop,
)
from app.modules.retrieval.application.ports.calibration import CalibrationStorePort
from app.modules.retrieval.domain.candidates import Candidate, CandidatePool
from app.modules.retrieval.domain.cutoff import adaptive_cutoff
from app.modules.retrieval.domain.gate import GateDecision, evaluate_gate
from app.modules.retrieval.domain.packer import mmr_pack


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    mode: Literal["static", "dynamic"]
    min_k: int
    max_k: int
    rel_ratio: float
    gap_ratio: float
    mmr_lambda: float
    duplicate_threshold: float
    context_token_budget: int
    token_estimate_factor: float


@dataclass(frozen=True, slots=True)
class SelectionOutcome:
    chunks: tuple[RetrievedChunk, ...]
    debug: SelectionDebug


class SelectionService:
    """Apply the calibrated gate, adaptive cutoff and MMR packer."""

    def __init__(
        self,
        config: SelectionConfig,
        *,
        calibration: CalibrationStorePort | None = None,
    ) -> None:
        self._config = config
        self._calibration = calibration

    @property
    def mode(self) -> str:
        return self._config.mode

    async def select(
        self,
        chunks: tuple[RetrievedChunk, ...],
        *,
        query_term_ids: tuple[int, ...],
        mode: str | None = None,
    ) -> SelectionOutcome:
        effective_mode = mode or self._config.mode
        pool = _pool(chunks, query_term_ids)
        if effective_mode == "static":
            return SelectionOutcome(
                chunks=chunks,
                debug=_static_debug(pool, chunks),
            )

        calibration = await self._calibration.load() if self._calibration is not None else None
        gate = evaluate_gate(pool.signals, calibration)
        thresholds = dict(gate.thresholds)
        rel_ratio = calibration.rel_ratio if calibration is not None else self._config.rel_ratio
        gap_ratio = calibration.gap_ratio if calibration is not None else self._config.gap_ratio
        thresholds["relRatio"] = rel_ratio
        thresholds["gapRatio"] = gap_ratio
        signals = {
            "denseTop1": pool.top1,
            "denseSeparation": pool.separation,
            "lexicalCoverage": pool.lexical_coverage,
        }

        if gate.decision is GateDecision.REJECT:
            return SelectionOutcome(
                chunks=(),
                debug=SelectionDebug(
                    mode=effective_mode,
                    enabled=gate.enabled,
                    decision=gate.decision.value,
                    signals=signals,
                    thresholds=thresholds,
                    kept=(),
                    dropped=(),
                ),
            )

        ordered = tuple(
            sorted(pool.candidates, key=lambda candidate: candidate.relevance, reverse=True)
        )
        cutoff = adaptive_cutoff(
            [candidate.relevance for candidate in ordered],
            rel_ratio=rel_ratio,
            gap_ratio=gap_ratio,
            min_k=self._config.min_k,
            max_k=self._config.max_k,
        )
        cutoff_kept = [ordered[index] for index in cutoff.kept]
        dropped = [
            SelectionDrop(chunk_id=ordered[index].chunk_id, reason=reason)
            for index, reason in cutoff.dropped
        ]
        packed = mmr_pack(
            cutoff_kept,
            budget_tokens=self._config.context_token_budget,
            token_estimate_factor=self._config.token_estimate_factor,
            mmr_lambda=self._config.mmr_lambda,
            duplicate_threshold=self._config.duplicate_threshold,
        )
        for index, reason in packed.dropped:
            dropped.append(SelectionDrop(chunk_id=cutoff_kept[index].chunk_id, reason=reason))
        kept_candidates = tuple(cutoff_kept[index] for index in packed.kept)
        kept = tuple(chunks[candidate.index] for candidate in kept_candidates)
        return SelectionOutcome(
            chunks=kept,
            debug=SelectionDebug(
                mode=effective_mode,
                enabled=gate.enabled,
                decision=gate.decision.value,
                signals=signals,
                thresholds=thresholds,
                kept=tuple(candidate.chunk_id for candidate in kept_candidates),
                dropped=tuple(dropped),
            ),
        )


def _pool(
    chunks: tuple[RetrievedChunk, ...],
    query_term_ids: tuple[int, ...],
) -> CandidatePool:
    return CandidatePool(
        candidates=tuple(
            Candidate(
                index=index,
                chunk_id=item.chunk.id,
                page=item.chunk.page,
                relevance=_relevance(item),
                token_count=item.chunk.token_count,
                kind=item.chunk.kind,
                dense_vector=item.dense_vector,
                sparse_indices=item.sparse_indices,
            )
            for index, item in enumerate(chunks)
        ),
        query_term_ids=query_term_ids,
    )


def _relevance(item: RetrievedChunk) -> float:
    if item.dense_cosine is not None:
        return item.dense_cosine
    if item.dense_score is not None:
        return item.dense_score
    return item.relevance_score


def _static_debug(
    pool: CandidatePool,
    chunks: tuple[RetrievedChunk, ...],
) -> SelectionDebug:
    return SelectionDebug(
        mode="static",
        enabled=False,
        decision=GateDecision.ACCEPT.value,
        signals={
            "denseTop1": pool.top1,
            "denseSeparation": pool.separation,
            "lexicalCoverage": pool.lexical_coverage,
        },
        thresholds={},
        kept=tuple(item.chunk.id for item in chunks),
        dropped=(),
    )
