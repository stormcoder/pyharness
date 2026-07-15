"""Tests for the mock / fake LLM provider."""

from __future__ import annotations

import pytest

from pyharness.core.testing import (
    FakeLLMProvider,
    FakeLLMResponse,
    make_echo_provider,
    make_error_provider,
    make_malformed_json_provider,
    make_rate_limited_provider,
)

# ---------------------------------------------------------------------------
# 1.  Scripted streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_streams_scripted_responses() -> None:
    """The provider yields responses in the exact order they were scripted."""
    provider = FakeLLMProvider(
        [
            FakeLLMResponse(
                tool_calls=[{"name": "read", "args": {"path": "test.py"}}],
                finish_reason="tool_calls",
            ),
            FakeLLMResponse(content="I've read the file and it looks good."),
            FakeLLMResponse(content="Anything else?"),
        ]
    )

    results = [
        chunk async for chunk in provider.stream([{"role": "user", "content": "hi"}], [])
    ]

    assert len(results) == 3
    assert results[0].finish_reason == "tool_calls"
    assert results[0].tool_calls == [{"name": "read", "args": {"path": "test.py"}}]
    assert results[0].content == ""
    assert results[1].content == "I've read the file and it looks good."
    assert results[1].finish_reason == "stop"
    assert results[2].content == "Anything else?"


# ---------------------------------------------------------------------------
# 2.  Call recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_records_calls() -> None:
    """Every call to ``stream`` or ``invoke`` is appended to ``provider.calls``."""
    provider = FakeLLMProvider([FakeLLMResponse(content="ok")])

    msgs_a = [{"role": "user", "content": "first call"}]
    msgs_b = [{"role": "user", "content": "second call"}]

    _ = [chunk async for chunk in provider.stream(msgs_a, [])]
    await provider.invoke(msgs_b, [])

    assert provider.call_count == 2
    assert provider.calls[0] == msgs_a
    assert provider.calls[1] == msgs_b


# ---------------------------------------------------------------------------
# 3.  invoke returns last response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_invoke_returns_last() -> None:
    """``invoke`` should return the final scripted response."""
    provider = FakeLLMProvider(
        [
            FakeLLMResponse(content="thinking..."),
            FakeLLMResponse(content="final answer"),
        ]
    )

    result = await provider.invoke([{"role": "user", "content": "?"}], [])
    assert result.content == "final answer"

    # invoke should also record the call
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# 4.  Empty script edge case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_empty_script() -> None:
    """An empty script streams nothing and invoke returns an empty response."""
    provider = FakeLLMProvider([])

    results = [chunk async for chunk in provider.stream([{"role": "user"}], [])]
    assert results == []

    result = await provider.invoke([{"role": "user"}], [])
    assert result.content == ""
    assert result.finish_reason == "stop"
    assert result.tool_calls == []


# ---------------------------------------------------------------------------
# 5.  last_call convenience property
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_last_call() -> None:
    """``last_call`` returns the most recent message list."""
    provider = FakeLLMProvider([FakeLLMResponse(content="a")])

    assert provider.last_call is None  # no calls yet

    _ = [chunk async for chunk in provider.stream([{"role": "user", "content": "x"}], [])]
    assert provider.last_call == [{"role": "user", "content": "x"}]


# ---------------------------------------------------------------------------
# 6.  Echo provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_echo_provider_always_returns_content() -> None:
    """An echo provider responds with the same content every time."""
    provider = make_echo_provider("Hello, world!")

    results_a = [chunk async for chunk in provider.stream([{"role": "user"}], [])]
    assert len(results_a) == 1
    assert results_a[0].content == "Hello, world!"
    assert results_a[0].finish_reason == "stop"

    results_b = [chunk async for chunk in provider.stream([{"role": "user"}], [])]
    assert results_b[0].content == "Hello, world!"


# ---------------------------------------------------------------------------
# 7.  Error provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_error_provider_produces_errors() -> None:
    """The error provider returns responses with ``finish_reason='error'``."""
    provider = make_error_provider(status_code=503, message="Service Unavailable")

    results = [chunk async for chunk in provider.stream([], [])]
    assert len(results) == 1
    assert results[0].finish_reason == "error"
    assert "503" in results[0].content
    assert "Service Unavailable" in results[0].content


# ---------------------------------------------------------------------------
# 8.  Rate-limited provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_rate_limited_provider_signals_rate_limit() -> None:
    """The rate‑limited provider has finish_reason ``rate_limit``."""
    provider = make_rate_limited_provider()

    results = [chunk async for chunk in provider.stream([], [])]
    assert len(results) == 1
    assert results[0].finish_reason == "rate_limit"
    assert "Rate limit" in results[0].content


# ---------------------------------------------------------------------------
# 9.  Malformed-JSON provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_malformed_json_provider_returns_bad_json() -> None:
    """The malformed-JSON provider returns non‑parseable tool‑call content."""
    provider = make_malformed_json_provider()

    results = [chunk async for chunk in provider.stream([], [])]
    assert len(results) == 1
    assert results[0].finish_reason == "tool_calls"
    assert results[0].tool_calls == [{"name": "broken", "args": "not valid json"}]
