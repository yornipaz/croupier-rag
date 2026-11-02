from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMAnswerPayload(BaseModel):
    """Validated JSON contract returned by the answer LLM."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    answer: str = Field(min_length=1)
    used_sources: list[str] = Field(default_factory=list)
    sufficient: bool
