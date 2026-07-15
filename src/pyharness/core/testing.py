"""Test doubles for deterministic testing of the agent loop and TUI.

Provides :class:`FakeLLMProvider` — a scriptable, async LLM provider that
yields pre-programmed responses and records every call for assertions.  Also
includes factory functions for common error / edge‑case providers.

Usage::

    from pyharness.core.testing import FakeLLMProvider, FakeLLMResponse

    provider = FakeLLMProvider([
        FakeLLMResponse(tool_calls=[{"name": "read", "args": {"path": "test.py"}}]),
        FakeLLMResponse(content="I've read the file and it looks good."),
    ])

    async for chunk in provider.stream(messages, tools):
        print(chunk)

    assert len(provider.calls) == 1
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeLLMResponse:
    """A single response chunk from the fake provider."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop", "tool_calls", "error", "rate_limit"


class FakeLLMProvider:
    """A deterministic LLM provider for integration and unit testing.

    The provider is driven by a *script* — a list of
    :class:`FakeLLMResponse` objects that are yielded in order on each
    :meth:`stream` call.  Every invocation of ``stream`` or ``invoke``
    records the messages argument so tests can assert on the conversation
    state.

    Parameters:
        script: Pre-programmed responses to yield.
    """

    def __init__(self, script: list[FakeLLMResponse]) -> None:
        self._script = script
        self._index = 0
        self.calls: list[list[dict[str, Any]]] = []

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any],
        **kwargs: Any,
    ) -> AsyncIterator[FakeLLMResponse]:
        """Stream all scripted responses, recording the call first.

        Args:
            messages: The full message list sent to the LLM.
            tools: Tool definitions available to the agent.

        Yields:
            Each :class:`FakeLLMResponse` in the script.
        """
        self.calls.append(messages)
        for response in self._script:
            self._index += 1
            yield response

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any],
        **kwargs: Any,
    ) -> FakeLLMResponse:
        """Single (non-streaming) invocation — returns the *last* scripted response.

        Args:
            messages: The full message list sent to the LLM.
            tools: Tool definitions available to the agent.

        Returns:
            The final :class:`FakeLLMResponse` in the script, or an empty
            response if the script is empty.
        """
        self.calls.append(messages)
        return self._script[-1] if self._script else FakeLLMResponse()

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    @property
    def last_call(self) -> list[dict[str, Any]] | None:
        """The most recent call's messages, for fine-grained assertions."""
        return self.calls[-1] if self.calls else None

    @property
    def call_count(self) -> int:
        """How many times ``stream`` or ``invoke`` has been called."""
        return len(self.calls)


# ------------------------------------------------------------------
# Provider factories
# ------------------------------------------------------------------


def make_error_provider(
    status_code: int = 500, message: str = "Internal Error"
) -> FakeLLMProvider:
    """Return a provider whose every response signals an error.

    Args:
        status_code: The HTTP status code the error represents.
        message: Human-readable error description.
    """
    return FakeLLMProvider(
        [
            FakeLLMResponse(
                content=f"Error {status_code}: {message}",
                finish_reason="error",
            )
        ]
    )


def make_rate_limited_provider() -> FakeLLMProvider:
    """Return a provider that simulates a rate-limit (429) response."""
    return FakeLLMProvider(
        [
            FakeLLMResponse(
                content="Rate limit exceeded. Try again in 30 seconds.",
                finish_reason="rate_limit",
            )
        ]
    )


def make_malformed_json_provider() -> FakeLLMProvider:
    """Return a provider whose tool‑call content is not valid JSON.

    Useful for testing that the agent gracefully handles malformed
    tool‑call payloads from the LLM.
    """
    return FakeLLMProvider(
        [
            FakeLLMResponse(
                content='{"name": "broken", args: {missing_quotes}}',
                tool_calls=[{"name": "broken", "args": "not valid json"}],
                finish_reason="tool_calls",
            )
        ]
    )


def make_echo_provider(content: str = "Echo response") -> FakeLLMProvider:
    """Return a provider that always replies with the same *content*.

    Args:
        content: The fixed text to return on every invocation.
    """
    return FakeLLMProvider([FakeLLMResponse(content=content)])
