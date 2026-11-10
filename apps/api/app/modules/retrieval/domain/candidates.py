from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.modules.retrieval.domain.gate import GateSignals
from app.modules.retrieval.domain.lexical import lexical_coverage


@dataclass(frozen=True, slots=True)
class Candidate:
    index: int
    chunk_id: str
    page: int
    relevance: float
    token_count: int
    kind: str
    dense_vector: tuple[float, ...] | None = None
    sparse_indices: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class CandidatePool:
    candidates: tuple[Candidate, ...]
    query_term_ids: tuple[int, ...]

    @property
    def dense_values(self) -> tuple[float, ...]:
        return tuple(candidate.relevance for candidate in self.candidates)

    @property
    def top1(self) -> float:
        return max(self.dense_values, default=0.0)

    @property
    def median(self) -> float:
        values = self.dense_values
        return float(statistics.median(values)) if values else 0.0

    @property
    def separation(self) -> float:
        return self.top1 - self.median

    @property
    def lexical_coverage(self) -> float:
        return lexical_coverage(
            self.query_term_ids,
            [candidate.sparse_indices for candidate in self.candidates],
        )

    @property
    def signals(self) -> GateSignals:
        return GateSignals(
            dense_top1=self.top1,
            dense_separation=self.separation,
            lexical_coverage=self.lexical_coverage,
        )
