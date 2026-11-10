from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    """Approximate model tokens without adding a tokenizer dependency.

    Words and individual punctuation marks count as one token. This mirrors the
    estimator used by the ingestion chunker, so usage metrics reported by the
    API are comparable with ``Chunk.token_count`` when the provider does not
    return usage metadata.
    """
    return len(_TOKEN_RE.findall(text))
