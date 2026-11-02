from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

type ResponseSchema = type[BaseModel] | dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResult:
    """Normalized result returned by every LLM adapter."""

    text: str
    model: str = ""
    parsed: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    provider: str = ""
