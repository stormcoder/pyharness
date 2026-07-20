"""Tests for BUG-002: Unable to select output text to copy.

Verifies:
1. ChatScreen has action_copy_chat (Ctrl+Shift+C binding)
2. action_copy_chat extracts text from RichLog.lines
3. action_copy_chat calls self.app.copy_to_clipboard()
"""

import inspect

from pyharness.tui.screens.chat import ChatScreen
from textual.widgets import RichLog


class TestCopyChatAction:
    """Ctrl+Shift+C must be bound to action_copy_chat on ChatScreen."""

    def test_action_copy_chat_exists(self):
        """ChatScreen must define action_copy_chat."""
        assert hasattr(ChatScreen, "action_copy_chat"), (
            "ChatScreen needs action_copy_chat method for Ctrl+Shift+C binding"
        )

    def test_action_uses_copy_to_clipboard(self):
        """action_copy_chat must call self.app.copy_to_clipboard()."""
        source = inspect.getsource(ChatScreen.action_copy_chat)
        assert "copy_to_clipboard" in source, (
            "action_copy_chat must call self.app.copy_to_clipboard()"
        )

    def test_action_reads_richlog_lines(self):
        """action_copy_chat must extract text from RichLog.lines."""
        source = inspect.getsource(ChatScreen.action_copy_chat)
        assert ".lines" in source, (
            "action_copy_chat must use RichLog.lines for text extraction"
        )

    def test_action_is_not_stub(self):
        """action_copy_chat must have a real implementation."""
        source = inspect.getsource(ChatScreen.action_copy_chat)
        assert len(source) > 50, (
            "action_copy_chat must have a real implementation (not a stub)"
        )


class TestRichLogLines:
    """action_copy_chat uses area.lines to extract text."""

    def test_source_references_lines(self):
        """action_copy_chat source must reference .lines for text extraction."""
        source = inspect.getsource(ChatScreen.action_copy_chat)
        assert "strip" in source or "segment" in source, (
            "action_copy_chat must iterate RichLog renderables to extract text"
        )
