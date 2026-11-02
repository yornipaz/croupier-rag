from __future__ import annotations

import re

from app.shared.errors import BadRequestError

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def require_safe_id(value: str, *, kind: str = "id") -> str:
    """Reject path traversal / separator characters in IDs used for filenames."""
    if not _SAFE_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise BadRequestError(f"Invalid {kind}")
    return value
