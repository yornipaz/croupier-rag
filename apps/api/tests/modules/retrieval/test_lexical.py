from __future__ import annotations

import pytest

from app.modules.retrieval.domain.lexical import lexical_coverage


def test_lexical_coverage_counts_query_terms_found_in_any_chunk() -> None:
    assert lexical_coverage([1, 2, 3], [[1, 2], [3]]) == pytest.approx(1.0)
    assert lexical_coverage([1, 2, 3, 4], [[1, 2], [3]]) == pytest.approx(0.75)


def test_lexical_coverage_deduplicates_query_terms_and_handles_empty_inputs() -> None:
    assert lexical_coverage([1, 1, 2], [[1]]) == pytest.approx(0.5)
    assert lexical_coverage([], [[1, 2]]) == 0.0
    assert lexical_coverage([1], []) == 0.0
    assert lexical_coverage([1], [None, []]) == 0.0
