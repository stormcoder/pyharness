"""Tests for the system prompt module, including the ``is_trivial_greeting``
classifier and the default system prompt content."""

from __future__ import annotations

import pytest

from pyharness.core.system_prompt import DEFAULT_SYSTEM_PROMPT, is_trivial_greeting


# ---------------------------------------------------------------------------
# Trivial greeting classifier
# ---------------------------------------------------------------------------

# Common casual greetings that an agent should recognise and respond to
# conversationally instead of firing off tools.
_TRIVIAL_GREETINGS = [
    "hello",
    "Hello!",
    "hi",
    "Hi there",
    "hey",
    "hey!",
    "how are you",
    "How are you doing?",
    "what's up",
    "whats up",
    "sup",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "o/",
    "hey there",
    "hiya",
]


@pytest.mark.parametrize("greeting", _TRIVIAL_GREETINGS)
def test_is_trivial_greeting_returns_true(greeting: str) -> None:
    """Messages like 'hello', 'hi', 'hey' must be classified as trivial."""
    assert is_trivial_greeting(greeting), (
        f"'{greeting}' should be classified as a trivial greeting"
    )


# Messages that are NOT casual greetings — these should be handled with tools
# if the model decides they need exploration.
_PROJECT_MESSAGES = [
    "fix the bug in session.py",
    "write a function",
    "read the spec",
    "explore the codebase",
    "what does AgentRunner do?",
    "show me the git log",
    "run the tests",
    "I need a new endpoint for users",
    "add a feature to the TUI",
    "refactor the provider bridge",
    "how many sessions are active?",
    "check the config schema",
    "what tools are available?",
    "update SPEC.md",
    "review my code",
]


@pytest.mark.parametrize("message", _PROJECT_MESSAGES)
def test_is_trivial_greeting_returns_false(message: str) -> None:
    """Project-related messages must NOT be classified as trivial greetings."""
    assert not is_trivial_greeting(message), (
        f"'{message}' should NOT be classified as a trivial greeting"
    )


# Quick regression: empty strings and whitespace-only should not crash and are
# not greetings.
def test_is_trivial_greeting_handles_empty() -> None:
    """Empty / whitespace input should not crash and should return False."""
    assert not is_trivial_greeting("")
    assert not is_trivial_greeting("   ")


# ---------------------------------------------------------------------------
# Default system prompt
# ---------------------------------------------------------------------------


def test_default_system_prompt_is_non_empty_string() -> None:
    """DEFAULT_SYSTEM_PROMPT must be a non-empty string."""
    assert DEFAULT_SYSTEM_PROMPT, "DEFAULT_SYSTEM_PROMPT must not be empty"
    assert isinstance(DEFAULT_SYSTEM_PROMPT, str)
    assert len(DEFAULT_SYSTEM_PROMPT.strip()) > 0


def test_default_system_prompt_defines_identity() -> None:
    """The default prompt must mention 'pyharness' to establish product
    identity, and define the agent's role."""
    content = DEFAULT_SYSTEM_PROMPT.lower()
    assert "pyharness" in content, (
        "DEFAULT_SYSTEM_PROMPT must mention 'pyharness'"
    )
    has_role = (
        "coding assistant" in content
        or "terminal coding agent" in content
        or "ai coding" in content
    )
    assert has_role, (
        "DEFAULT_SYSTEM_PROMPT must define the agent role"
    )
