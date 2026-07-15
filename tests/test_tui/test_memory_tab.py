"""Tests for the Memory tab widget."""

from __future__ import annotations

import pytest

from pyharness.tui.widgets.memory import MemoryTab


class TestMemoryTab:
    """Memory tab widget tests."""

    def test_memory_tab_imports(self):
        """MemoryTab can be imported and instantiated."""
        tab = MemoryTab()
        assert tab is not None

    def test_memory_tab_composes(self):
        """MemoryTab compose() produces child widgets."""
        tab = MemoryTab()
        children = list(tab.compose())
        assert len(children) > 0
        # Should have 6 static widgets (title + content pairs)
        assert len(children) >= 3

    def test_memory_tab_is_static_subclass(self):
        """MemoryTab is a Static widget."""
        from textual.widgets import Static

        assert issubclass(MemoryTab, Static)

    def test_memory_tab_can_be_instantiated(self):
        """Multiple MemoryTab instances can be created."""
        tab1 = MemoryTab()
        tab2 = MemoryTab()
        assert tab1 is not tab2

    def test_memory_tab_compose_yields_static_widgets(self):
        """All composed children are Static widgets."""
        from textual.widgets import Static

        tab = MemoryTab()
        for child in tab.compose():
            assert isinstance(child, Static)
