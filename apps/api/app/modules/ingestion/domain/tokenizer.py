from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    """Approximate model tokens without adding a tokenizer dependency."""
    return len(_TOKEN_RE.findall(text))
