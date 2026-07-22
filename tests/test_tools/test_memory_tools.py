"""Tests for :mod:`pyharness.tools.memory_tools` — agent-facing memory tools.

All tools must return graceful "MemPalace not installed" messages when
``mempalace`` is not importable.  The test environment does *not* have
mempalace installed, so every tool returns the install-prompt string.

R3.14-R3.15: Tools are ``async def`` — all invocations use ``await tool.ainvoke()``
to ensure safe operation under a running event loop.
"""

from __future__ import annotations

import asyncio

from pyharness.tools.memory_tools import (
    _MEM_NOT_INSTALLED,
    _format_results,
    mempalace_diary_read,
    mempalace_kg_add,
    mempalace_kg_query,
    mempalace_remember,
    mempalace_search,
    mempalace_search_sessions,
)

# ---------------------------------------------------------------------------
# Helper — validate graceful-degradation pattern
# ---------------------------------------------------------------------------


def _assert_graceful(result: str, tool_name: str) -> None:
    """Assert that *result* contains the graceful degradation message."""
    assert "MemPalace not installed" in result, (
        f"{tool_name} should return the install-prompt message, got:\n{result}"
    )


# ---------------------------------------------------------------------------
# mempalace_search
# ---------------------------------------------------------------------------


async def test_mempalace_search_returns_graceful_message() -> None:
    """``mempalace_search`` returns the install prompt when mempalace is absent."""
    result = await mempalace_search.ainvoke({"query": "auth bug", "limit": 5})
    _assert_graceful(result, "mempalace_search")


async def test_mempalace_search_default_limit() -> None:
    """``mempalace_search`` accepts limit as optional."""
    result = await mempalace_search.ainvoke({"query": "sessions"})
    _assert_graceful(result, "mempalace_search")


# ---------------------------------------------------------------------------
# mempalace_remember
# ---------------------------------------------------------------------------


async def test_mempalace_remember_returns_graceful_message() -> None:
    """``mempalace_remember`` returns the install prompt when mempalace is absent."""
    result = await mempalace_remember.ainvoke(
        {"fact": "AuthMiddleware lives in src/auth/middleware.py"}
    )
    _assert_graceful(result, "mempalace_remember")


# ---------------------------------------------------------------------------
# mempalace_search_sessions
# ---------------------------------------------------------------------------


async def test_mempalace_search_sessions_returns_graceful_message() -> None:
    """``mempalace_search_sessions`` returns the install prompt when mempalace is absent."""
    result = await mempalace_search_sessions.ainvoke({"topic": "auth refactor"})
    _assert_graceful(result, "mempalace_search_sessions")


# ---------------------------------------------------------------------------
# mempalace_diary_read
# ---------------------------------------------------------------------------


async def test_mempalace_diary_read_returns_graceful_message() -> None:
    """``mempalace_diary_read`` returns the install prompt when mempalace is absent."""
    result = await mempalace_diary_read.ainvoke({"agent_name": "build"})
    _assert_graceful(result, "mempalace_diary_read")


async def test_mempalace_diary_read_default_agent() -> None:
    """``mempalace_diary_read`` works with default agent_name."""
    result = await mempalace_diary_read.ainvoke({})
    _assert_graceful(result, "mempalace_diary_read")


# ---------------------------------------------------------------------------
# mempalace_kg_query
# ---------------------------------------------------------------------------


async def test_mempalace_kg_query_returns_graceful_message() -> None:
    """``mempalace_kg_query`` returns the install prompt when mempalace is absent."""
    result = await mempalace_kg_query.ainvoke({"entity": "AuthMiddleware"})
    _assert_graceful(result, "mempalace_kg_query")


# ---------------------------------------------------------------------------
# mempalace_kg_add
# ---------------------------------------------------------------------------


async def test_mempalace_kg_add_valid_input() -> None:
    """``mempalace_kg_add`` handles valid input gracefully without mempalace."""
    result = await mempalace_kg_add.ainvoke({
        "subject": "AuthMiddleware",
        "predicate": "located_in",
        "obj": "src/auth/middleware.py",
    })
    _assert_graceful(result, "mempalace_kg_add")


async def test_mempalace_kg_add_with_special_characters() -> None:
    """``mempalace_kg_add`` handles subject/obj with special characters."""
    result = await mempalace_kg_add.ainvoke({
        "subject": "error handling",
        "predicate": "uses",
        "obj": "SentryIntegration v2.0",
    })
    _assert_graceful(result, "mempalace_kg_add")


# ---------------------------------------------------------------------------
# _format_results helper
# ---------------------------------------------------------------------------


def test_format_results_empty() -> None:
    """``_format_results`` returns 'No results' for empty list."""
    assert _format_results([]) == "No results found."


def test_format_results_single() -> None:
    """``_format_results`` formats a single result correctly."""
    results = [{"content": "Found auth bug", "score": 0.95}]
    formatted = _format_results(results)
    assert "1 result" in formatted
    assert "Found auth bug" in formatted
    assert "0.950" in formatted


def test_format_results_without_score() -> None:
    """``_format_results`` handles results without a score field."""
    results = [{"content": "Some content"}]
    formatted = _format_results(results)
    assert "Some content" in formatted
    assert "score" not in formatted


def test_format_results_truncation() -> None:
    """``_format_results`` truncates at max_items and shows remainder count."""
    results = [{"content": f"item {i}", "score": 0.9} for i in range(20)]
    formatted = _format_results(results, max_items=3)
    assert "item 0" in formatted
    assert "item 1" in formatted
    assert "item 2" in formatted
    assert "item 3" not in formatted
    assert "17 more" in formatted


# ---------------------------------------------------------------------------
# Tools are callable and return strings
# ---------------------------------------------------------------------------


def test_all_memory_tools_are_callable() -> None:
    """Every tool in ALL_MEMORY_TOOLS has an ``ainvoke`` method.

    R3.14-R3.15: Async tools use ``ainvoke``, not ``invoke``.
    """
    from pyharness.tools.memory_tools import ALL_MEMORY_TOOLS

    for t in ALL_MEMORY_TOOLS:
        assert hasattr(t, "ainvoke"), f"{t.name} should have an ainvoke method"
        assert callable(t.ainvoke), f"{t.name}.ainvoke should be callable"


def test_all_memory_tools_are_langchain_tools() -> None:
    """Every tool in ALL_MEMORY_TOOLS is a LangChain BaseTool."""
    from langchain_core.tools import BaseTool

    from pyharness.tools.memory_tools import ALL_MEMORY_TOOLS

    for t in ALL_MEMORY_TOOLS:
        assert isinstance(t, BaseTool), (
            f"{t.name} should be a langchain_core.tools.BaseTool"
        )


# ---------------------------------------------------------------------------
# Tool count
# ---------------------------------------------------------------------------


def test_memory_tool_count() -> None:
    """ALL_MEMORY_TOOLS contains exactly 6 tools."""
    from pyharness.tools.memory_tools import ALL_MEMORY_TOOLS

    assert len(ALL_MEMORY_TOOLS) == 6


# ---------------------------------------------------------------------------
# Ensure no mempalace import at module level
# ---------------------------------------------------------------------------


def test_no_mempalace_import_at_module_level() -> None:
    """The memory_tools module must not import mempalace at module level."""
    import pyharness.tools.memory_tools as mod

    # The module must not have 'mempalace' in its globals (aside from strings)
    # A lazy import is done inside each tool function via asyncio.run(_get_store())
    assert "mempalace" not in [name for name in dir(mod) if not name.startswith("_")], (
        "mempalace should not be imported at module level — it's an optional dependency"
    )


# ---------------------------------------------------------------------------
# _MEM_NOT_INSTALLED message
# ---------------------------------------------------------------------------


def test_mem_not_installed_message_includes_install_instructions() -> None:
    """The not-installed message includes pip/uv install instructions."""
    assert "pip install mempalace" in _MEM_NOT_INSTALLED
    assert "uv add mempalace" in _MEM_NOT_INSTALLED
