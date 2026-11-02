from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import ValidationError

from app.modules.chat.application.dto.llm_answer import LLMAnswerPayload

_SOURCE_RE = re.compile(r"(?:S\s*)?(\d+)", re.IGNORECASE)


class InvalidLLMResponse(ValueError):
    """The provider did not return the required JSON answer contract."""


def parse_llm_answer(raw: str) -> LLMAnswerPayload:
    text = _strip_code_fence(raw.strip())
    if not text:
        raise InvalidLLMResponse("empty response")
    try:
        return LLMAnswerPayload.model_validate_json(text)
    except ValidationError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidate = text[start : end + 1]
            try:
                return LLMAnswerPayload.model_validate_json(candidate)
            except ValidationError:
                pass
        raise InvalidLLMResponse("response is not valid answer JSON") from exc


def normalize_used_sources(labels: Sequence[str]) -> tuple[int, ...]:
    indexes: set[int] = set()
    for label in labels:
        for match in _SOURCE_RE.finditer(label):
            indexes.add(int(match.group(1)))
    return tuple(sorted(index for index in indexes if index >= 1))


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
