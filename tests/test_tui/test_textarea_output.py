"""Tests for RichLog chat output (formatted rendering + _write helper)."""

import inspect

from pyharness.tui.screens.chat import ChatScreen, _render_markdown


class TestChatAreaRichLog:
    """Chat output must use RichLog for formatted markdown rendering."""

    def test_compose_uses_richlog(self):
        """ChatScreen.compose must create a RichLog widget."""
        source = inspect.getsource(ChatScreen.compose)
        assert "RichLog" in source, "ChatScreen.compose must use RichLog"

    def test_richlog_has_focus_disabled(self):
        """RichLog must have can_focus=False to prevent tab stealing."""
        source = inspect.getsource(ChatScreen.compose)
        assert "can_focus = False" in source, "RichLog must have can_focus=False"

    def test_richlog_has_markup_enabled(self):
        """RichLog must have markup=True for Rich markup rendering."""
        source = inspect.getsource(ChatScreen.compose)
        assert "markup=True" in source, "RichLog must have markup=True"

    def test_write_method_exists(self):
        """ChatScreen must have a _write helper method."""
        assert hasattr(ChatScreen, "_write"), "ChatScreen must have _write method"


class TestMarkdownRenderer:
    """_render_markdown converts markdown text to Rich-renderable output."""

    def test_render_markdown_plain_text(self):
        """Plain text passes through unchanged."""
        result = _render_markdown("Hello world")
        assert "Hello world" in result

    def test_render_markdown_returns_string(self):
        """_render_markdown always returns a string."""
        result = _render_markdown("test")
        assert isinstance(result, str)

    def test_render_markdown_empty(self):
        """Empty string returns empty string."""
        assert _render_markdown("") == ""

    def test_render_markdown_whitespace(self):
        """Whitespace-only returns unchanged."""
        assert _render_markdown("   ") == "   "
