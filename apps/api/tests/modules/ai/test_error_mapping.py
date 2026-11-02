from __future__ import annotations

import httpx
import pytest
import respx
from google.genai import errors as genai_errors

from app.modules.ai.infrastructure.errors import map_provider_exception
from app.modules.ai.infrastructure.ollama_llm import OllamaLLM
from app.modules.ai.infrastructure.resilient import ResilientLLM
from app.shared.errors import (
    AuthenticationError,
    BadRequestError,
    RateLimitedError,
    UpstreamError,
    UpstreamTimeoutError,
)
from app.shared.resilience.circuit_breaker import CircuitBreaker


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://provider.test/v1/chat")
    response = httpx.Response(status_code, request=request, text="provider error")
    return httpx.HTTPStatusError("provider error", request=request, response=response)


@pytest.mark.parametrize(
    ("status_code", "expected_type", "retryable"),
    [
        (429, RateLimitedError, True),
        (400, BadRequestError, False),
        (401, AuthenticationError, False),
        (403, AuthenticationError, False),
        (500, UpstreamError, True),
        (503, UpstreamError, True),
    ],
)
def test_http_status_mapping(
    status_code: int,
    expected_type: type[Exception],
    retryable: bool,
) -> None:
    mapped = map_provider_exception("test", _http_status_error(status_code))

    assert isinstance(mapped, expected_type)
    assert mapped.retryable is retryable


def test_timeout_and_transport_are_retryable() -> None:
    request = httpx.Request("POST", "http://provider.test/v1/chat")

    timeout = map_provider_exception("test", httpx.ReadTimeout("slow", request=request))
    transport = map_provider_exception("test", httpx.ConnectError("down", request=request))

    assert isinstance(timeout, UpstreamTimeoutError)
    assert timeout.retryable is True
    assert isinstance(transport, UpstreamError)
    assert transport.retryable is True


def test_gemini_api_error_status_mapping() -> None:
    rate_limited = genai_errors.APIError(
        429,
        {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}},
    )
    unauthorized = genai_errors.APIError(
        401,
        {"error": {"message": "invalid key", "status": "UNAUTHENTICATED"}},
    )

    assert isinstance(map_provider_exception("gemini", rate_limited), RateLimitedError)
    assert isinstance(map_provider_exception("gemini", unauthorized), AuthenticationError)


@respx.mock
async def test_ollama_429_is_mapped_and_retried_by_wrapper() -> None:
    route = respx.post("http://ollama.test/api/chat").mock(
        side_effect=[
            httpx.Response(429, json={"error": "too many requests"}),
            httpx.Response(
                200,
                json={"message": {"content": "respuesta"}, "model": "llama-test"},
            ),
        ]
    )
    inner = OllamaLLM(base_url="http://ollama.test", model="llama-test", timeout_s=1.0)
    wrapper = ResilientLLM(
        inner,
        name="ollama-test",
        timeout_s=1.0,
        max_retries=1,
        base_delay_s=0.001,
        max_delay_s=0.005,
        breaker=CircuitBreaker("ollama-test"),
    )

    result = await wrapper.generate("hola", "sistema")

    assert result.text == "respuesta"
    assert route.call_count == 2


@respx.mock
async def test_ollama_timeout_is_mapped() -> None:
    respx.post("http://ollama.test/api/chat").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    inner = OllamaLLM(base_url="http://ollama.test", model="llama-test", timeout_s=1.0)

    with pytest.raises(UpstreamTimeoutError):
        await inner.generate("hola")
