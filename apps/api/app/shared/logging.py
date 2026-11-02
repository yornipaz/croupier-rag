from __future__ import annotations

from typing import cast

import structlog
from structlog.typing import FilteringBoundLogger


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    return cast(FilteringBoundLogger, structlog.get_logger(name))
