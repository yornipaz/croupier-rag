from __future__ import annotations

from collections.abc import Sequence


def lexical_coverage(
    query_term_ids: Sequence[int],
    chunk_term_ids: Sequence[Sequence[int] | None],
) -> float:
    """Fraction of query BM25 term ids present anywhere in the top-N chunks.

    Using the sparse encoder's term ids guarantees the same lowercasing,
    punctuation removal, stopword filtering and stemming that produced the
    stored sparse vectors. Duplicate query ids count once.
    """
    query_terms = {int(term) for term in query_term_ids}
    if not query_terms:
        return 0.0
    found: set[int] = set()
    for chunk_terms in chunk_term_ids:
        if chunk_terms:
            found.update(int(term) for term in chunk_terms)
    return len(query_terms.intersection(found)) / len(query_terms)
