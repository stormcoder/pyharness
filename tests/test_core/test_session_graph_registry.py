"""Tests for R2.4-R2.5 — SessionGraphRegistry caches compiled graphs per session."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from pyharness.core.session_graph_registry import SessionGraphRegistry


@tool
def _test_tool(x: str) -> str:
    """A test tool."""
    return x


def _make_mock_model() -> MagicMock:
    """Return a mock BaseChatModel."""
    model = MagicMock()
    model.bind_tools.return_value = model
    return model


class TestSessionGraphRegistry:
    """R2.4-R2.5 — graph registry caches and invalidates per-session."""

    def test_get_or_create_returns_graph(self) -> None:
        """get_or_create returns a compiled graph for a new session."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        graph = registry.get_or_create("sess-1", model, [_test_tool])
        assert graph is not None

    def test_get_or_create_caches(self) -> None:
        """get_or_create returns the same graph instance on second call."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        g1 = registry.get_or_create("sess-1", model, [_test_tool])
        g2 = registry.get_or_create("sess-1", model, [_test_tool])
        assert g1 is g2

    def test_different_sessions_different_graphs(self) -> None:
        """Different session IDs get different graph instances."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        g1 = registry.get_or_create("sess-a", model, [_test_tool])
        g2 = registry.get_or_create("sess-b", model, [_test_tool])
        assert g1 is not g2

    def test_invalidate_removes_cache(self) -> None:
        """invalidate() removes the cached graph for a session."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        g1 = registry.get_or_create("sess-1", model, [_test_tool])
        registry.invalidate("sess-1")
        g2 = registry.get_or_create("sess-1", model, [_test_tool])
        assert g1 is not g2  # new graph created after invalidation

    def test_invalidate_nonexistent_noop(self) -> None:
        """invalidate() on unknown session_id does not raise."""
        registry = SessionGraphRegistry()
        registry.invalidate("nonexistent")  # Must not raise

    def test_invalidate_all_clears_everything(self) -> None:
        """invalidate_all() removes all cached graphs."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        g1 = registry.get_or_create("sess-a", model, [_test_tool])
        g2 = registry.get_or_create("sess-b", model, [_test_tool])
        registry.invalidate_all()
        g3 = registry.get_or_create("sess-a", model, [_test_tool])
        g4 = registry.get_or_create("sess-b", model, [_test_tool])
        assert g1 is not g3
        assert g2 is not g4

    def test_contains(self) -> None:
        """The __contains__ check works for cached sessions."""
        registry = SessionGraphRegistry()
        model = _make_mock_model()
        assert "sess-1" not in registry
        registry.get_or_create("sess-1", model, [_test_tool])
        assert "sess-1" in registry
        assert "sess-2" not in registry
        registry.invalidate("sess-1")
        assert "sess-1" not in registry
