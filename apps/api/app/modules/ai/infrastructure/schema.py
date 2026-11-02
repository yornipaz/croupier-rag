from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.modules.ai.application.dto.llm import ResponseSchema
from app.shared.errors import UpstreamError


def to_json_schema(schema: ResponseSchema) -> dict[str, Any]:
    """Convert a Pydantic model class or an explicit JSON schema to a dict."""
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    raise TypeError("response_schema must be a Pydantic model class or a JSON schema dict")


def validate_structured_payload(
    payload: dict[str, Any],
    schema: ResponseSchema,
) -> dict[str, Any]:
    """Validate provider JSON against the requested Pydantic schema."""
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        return payload
    try:
        return schema.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise UpstreamError(
            "Provider returned JSON that does not match the requested schema",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def parse_json_payload(text: str, schema: ResponseSchema) -> dict[str, Any]:
    """Parse JSON text, then validate it against the optional Pydantic schema."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UpstreamError(
            "Provider returned invalid JSON",
            details={"position": exc.pos},
        ) from exc
    if not isinstance(payload, dict):
        raise UpstreamError("Provider JSON response must be an object")
    return validate_structured_payload(payload, schema)


def model_from_parsed(value: Any) -> dict[str, Any] | None:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None
