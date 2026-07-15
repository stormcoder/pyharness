"""Tests for :mod:`pyharness.core.memory` — MemPalace wrapper.

These tests verify graceful degradation when ``mempalace`` is not installed.
Integration tests with a real MemPalace are in the conftest's ``storemem``
fixture (requires optional dependency).
"""

from __future__ import annotations

import pytest

from pyharness.config.schema import MemoryConfig
from pyharness.core.memory import (
    MemorySearchResult,
    MemoryStore,
    WakeUpContext,
    get_memory_store,
    reset_memory_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_config(**kwargs) -> MemoryConfig:
    """Create a MemoryConfig with defaults overridden by *kwargs*."""
    defaults = {
        "enabled": True,
        "wing": "test_project",
    }
    defaults.update(kwargs)
    return MemoryConfig(**defaults)


# ---------------------------------------------------------------------------
# Test: available flag
# ---------------------------------------------------------------------------


def test_memory_store_available_flag() -> None:
    """``available`` property reflects whether mempalace is importable."""
    store = MemoryStore(config=_new_config(), project_name="test")
    # mempalace is not a project dependency — it must not be available
    # in the test environment unless explicitly installed.
    assert store.available is False
    assert store.initialized is False


# ---------------------------------------------------------------------------
# Test: initialize is no-op without mempalace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_store_initialize_noop_without_mempalace() -> None:
    """``initialize()`` does not crash when mempalace is not installed."""
    store = MemoryStore(config=_new_config(), project_name="test")
    await store.initialize()
    # Should still be uninitialized — gracefully
    assert store.initialized is False
    # Calling initialize again is also safe
    await store.initialize()
    assert store.initialized is False


# ---------------------------------------------------------------------------
# Test: wake_up returns empty context when unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_up_returns_empty_when_unavailable() -> None:
    """``wake_up()`` returns an empty WakeUpContext when MemPalace is absent."""
    store = MemoryStore(config=_new_config(), project_name="test")
    ctx = await store.wake_up()

    assert isinstance(ctx, WakeUpContext)
    assert len(ctx.related_sessions) == 0
    assert len(ctx.kg_facts) == 0
    assert len(ctx.diary_entries) == 0
    assert "(MemPalace not installed)" in ctx.briefing


# ---------------------------------------------------------------------------
# Test: to_system_preamble formats correctly
# ---------------------------------------------------------------------------


def test_to_system_preamble_formats_correctly() -> None:
    """``to_system_preamble()`` renders markdown with KG facts and sessions."""
    ctx = WakeUpContext(
        kg_facts=[
            {"subject": "AuthMiddleware", "predicate": "located_in", "object": "src/auth/middleware.py"},
            {"subject": "SessionStore", "predicate": "uses", "object": "aiosqlite"},
        ],
        related_sessions=[
            MemorySearchResult(content="Fixed auth bug in commit abc123", score=0.95),
            MemorySearchResult(content="Refactored session store to use WAL mode", score=0.88),
            MemorySearchResult(content="Added provider configuration", score=0.82),
            MemorySearchResult(content="Initial commit", score=0.75),
        ],
        diary_entries=[
            {"content": "SESSION:2026-07-14|built.memory.store|★★★"},
        ],
        briefing="Loaded context",
    )

    preamble = ctx.to_system_preamble()

    assert "## Knowledge Graph Facts" in preamble
    assert "AuthMiddleware → located_in → src/auth/middleware.py" in preamble
    assert "SessionStore → uses → aiosqlite" in preamble
    assert "## Related Past Sessions" in preamble
    assert "Fixed auth bug in commit abc123" in preamble
    assert "Refactored session store to use WAL mode" in preamble
    # 4th session is beyond the [3] truncation threshold — it should not appear
    assert "Initial commit" not in preamble
    assert "## Agent Diary" in preamble
    assert "SESSION:2026-07-14" in preamble


# ---------------------------------------------------------------------------
# Test: preamble with only KG facts
# ---------------------------------------------------------------------------


def test_to_system_preamble_kg_only() -> None:
    """Preamble handles only knowledge graph facts (no sessions or diary)."""
    ctx = WakeUpContext(
        kg_facts=[{"subject": "X", "predicate": "uses", "object": "Y"}],
    )
    preamble = ctx.to_system_preamble()

    assert "## Knowledge Graph Facts" in preamble
    assert "## Related Past Sessions" not in preamble
    assert "## Agent Diary" not in preamble


# ---------------------------------------------------------------------------
# Test: preamble when empty
# ---------------------------------------------------------------------------


def test_to_system_preamble_empty() -> None:
    """Empty context produces an empty preamble string."""
    ctx = WakeUpContext()
    assert ctx.to_system_preamble() == ""


# ---------------------------------------------------------------------------
# Test: search returns empty when unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_empty_when_unavailable() -> None:
    """``search()`` returns an empty list when mempalace is absent."""
    store = MemoryStore(config=_new_config(), project_name="test")
    results = await store.search("test query")
    assert results == []


# ---------------------------------------------------------------------------
# Test: index / remember are no-ops when unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_and_remember_noop_without_mempalace() -> None:
    """``index()`` and ``remember()`` are safe no-ops without mempalace."""
    store = MemoryStore(config=_new_config(), project_name="test")
    # Should not raise
    await store.index("some content")
    await store.remember("some fact")
    await store.diary_write("build", "test entry")
    results = await store.diary_read("build")
    assert results == []


# ---------------------------------------------------------------------------
# Test: kg_query returns empty when unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_query_returns_empty_when_unavailable() -> None:
    """``kg_query()`` returns an empty list without mempalace."""
    store = MemoryStore(config=_new_config(), project_name="test")
    results = await store.kg_query("AuthMiddleware")
    assert results == []


# ---------------------------------------------------------------------------
# Test: kg_add returns status dict when unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_add_returns_status_when_unavailable() -> None:
    """``kg_add()`` returns an 'unavailable' status dict without mempalace."""
    store = MemoryStore(config=_new_config(), project_name="test")
    result = await store.kg_add("A", "uses", "B")
    assert result["status"] == "unavailable"
    assert "MemPalace not installed" in result["reason"]


# ---------------------------------------------------------------------------
# Test: search_sessions delegates to search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_sessions_delegates() -> None:
    """``search_sessions()`` delegates to ``search()`` with the topic."""
    store = MemoryStore(config=_new_config(), project_name="test")
    results = await store.search_sessions("auth bug", limit=5)
    assert results == []


# ---------------------------------------------------------------------------
# Test: singleton
# ---------------------------------------------------------------------------


def test_get_memory_store_singleton() -> None:
    """``get_memory_store()`` returns the same instance on repeated calls."""
    reset_memory_store()
    s1 = get_memory_store("test", _new_config())
    s2 = get_memory_store("test")
    assert s1 is s2
    reset_memory_store()


# ---------------------------------------------------------------------------
# Test: WakeUpContext default briefing is empty
# ---------------------------------------------------------------------------


def test_wakeup_context_default_briefing() -> None:
    """Default WakeUpContext has an empty briefing string."""
    ctx = WakeUpContext()
    assert ctx.briefing == ""


# ---------------------------------------------------------------------------
# Test: MemorySearchResult fields
# ---------------------------------------------------------------------------


def test_memory_search_result_fields() -> None:
    """MemorySearchResult stores all five fields correctly."""
    r = MemorySearchResult(
        content="test content",
        score=0.95,
        wing="test_project",
        room="sessions",
        drawer_id="abc123",
    )
    assert r.content == "test content"
    assert r.score == 0.95
    assert r.wing == "test_project"
    assert r.room == "sessions"
    assert r.drawer_id == "abc123"


# ---------------------------------------------------------------------------
# Test: module-level MEM_PALACE_AVAILABLE is False in test env
# ---------------------------------------------------------------------------


def test_mem_palace_available_is_boolean() -> None:
    """MEM_PALACE_AVAILABLE is a boolean — False in test env."""
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    assert isinstance(MEM_PALACE_AVAILABLE, bool)
    assert MEM_PALACE_AVAILABLE is False  # mempalace is not in deps


# ---------------------------------------------------------------------------
# Test: close is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_is_noop() -> None:
    """``close()`` does not raise when mempalace is absent."""
    store = MemoryStore(config=_new_config(), project_name="test")
    await store.close()
    # Should not raise
