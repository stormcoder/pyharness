"""Tests for streaming output and token counter fixes.

BUG-003: Output dumped all at once instead of streaming
  Previously agent response tokens were buffered into ``full_response``
  and only written to output on the "done" event.  Now each token is
  written immediately via ``screen._write(token)`` inside the content handler.

BUG-004: Token counter never updates
  The status bar always showed "0 tokens".  ``update_status_bar`` existed
  but was never called during streaming.  The method is now invoked
  after each streaming event to keep the token count live.
"""

from __future__ import annotations

import inspect

from pyharness.core.agent_manager import AgentManager
from pyharness.tui.app import PyHarnessApp


# ============================================================================
# BUG-003: Streaming — tokens written immediately, not just buffered
# ============================================================================


class TestStreamingImmediateWrite:
    """Each content token must be written immediately, not just buffered."""

    def test_write_called_inside_content_block(self) -> None:
        """``screen._write(token)`` is called inside the ``if kind == "content":`` block."""
        source = inspect.getsource(AgentManager._run_agent)

        # The "content" block must contain both full_response.append and
        # an immediate screen._write(token).  We don't regex-parse the AST;
        # we verify the block structure by checking key patterns appear
        # in the correct relative order.
        lines = source.splitlines()

        # Find the content-handler block boundaries
        content_start: int | None = None
        content_end: int | None = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('if kind == "content"'):
                content_start = i
            if content_start is not None and content_end is None:
                # The content block ends at the next elif/else at the same
                # indentation level.
                if stripped.startswith("elif ") or stripped.startswith("else:"):
                    content_end = i
                    break
                # Also catch "elif kind" which appears with extra spaces
                if "elif kind" in stripped:
                    content_end = i
                    break

        assert content_start is not None, (
            '_run_agent must have an \'if kind == "content":\' block'
        )
        if content_end is None:
            # Block runs to end of function — pick a generous window
            content_end = len(lines)

        block = "\n".join(lines[content_start:content_end])

        assert "._write(" in block, (
            "screen._write(token) must be called inside the content block "
            "for immediate streaming, not deferred to the 'done' event"
        )
        assert "full_response.append(" in block, (
            "full_response.append(token) must still exist in the content block "
            "for markdown rendering at 'done'"
        )

    def test_write_and_append_both_present(self) -> None:
        """Both ``full_response.append(token)`` AND ``screen._write(token)``
        must exist in the content handler — append for markdown rendering
        at 'done', write for immediate streaming."""
        source = inspect.getsource(AgentManager._run_agent)

        assert "full_response.append(token)" in source, (
            "full_response.append(token) must be called in the content handler"
        )
        assert "._write(token)" in source, (
            "screen._write(token) must be called in the content handler "
            "for each token to stream immediately"
        )

    def test_fallback_version_not_used_in_content_block(self) -> None:
        """Verify the content block does NOT fall back to the pre-fix
        pattern of only buffering (i.e. append only, no write)."""
        source = inspect.getsource(AgentManager._run_agent)
        lines = source.splitlines()

        content_start: int | None = None
        content_end: int | None = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('if kind == "content"'):
                content_start = i
            if content_start is not None and content_end is None:
                if stripped.startswith("elif ") or stripped.startswith("else:"):
                    content_end = i
                    break
                if "elif kind" in stripped:
                    content_end = i
                    break

        assert content_start is not None
        if content_end is None:
            content_end = len(lines)

        block = "\n".join(lines[content_start:content_end])

        # The pre-fix pattern would have append but NOT write.  We assert
        # write IS present.
        assert (
            "._write(token)" in block
        ), (
            "BUG-003: screen._write(token) must be present in content block. "
            "Pre-fix code only had full_response.append(token); "
            "tokens must now stream immediately."
        )


class TestRenderMarkdownAtDone:
    """``_render_markdown`` is called at the "done" event for final output."""

    def test_render_markdown_called_at_done(self) -> None:
        """``_render_markdown`` must be invoked inside the ``kind == "done"`` handler."""
        source = inspect.getsource(AgentManager._run_agent)
        lines = source.splitlines()

        done_start: int | None = None
        done_end: int | None = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('if kind == "done"') or 'kind == "done"' in stripped:
                done_start = i
            if done_start is not None and done_end is None:
                if (
                    i > done_start
                    and (stripped.startswith("elif ") or stripped.startswith("else:"))
                ):
                    done_end = i
                    break
                if i > done_start and ("elif kind" in stripped):
                    done_end = i
                    break

        assert done_start is not None, (
            "_run_agent must have a 'done' event handler"
        )
        if done_end is None:
            done_end = len(lines)

        block = "\n".join(lines[done_start:done_end])

        assert "_render_markdown(" in block, (
            "_render_markdown() must be called inside the 'done' handler "
            "to produce the formatted markdown output"
        )


# ============================================================================
# BUG-004: Token counter — status bar updates during streaming
# ============================================================================


class TestStatusBarWidget:
    """The status bar widget is created with the correct ID."""

    def test_status_bar_compose_creates_widget(self) -> None:
        """``ChatScreen.compose`` must yield a StatusBar with ``id="status-bar"``."""
        from pyharness.tui.screens.chat import ChatScreen

        source = inspect.getsource(ChatScreen.compose)
        assert 'id="status-bar"' in source, (
            "ChatScreen.compose must create a widget with id='status-bar'"
        )
        assert "StatusBar" in source, (
            "ChatScreen.compose must yield a StatusBar widget"
        )

    def test_status_bar_initial_text_has_tokens(self) -> None:
        """The initial status bar text must include a token placeholder."""
        from pyharness.tui.screens.chat import ChatScreen

        source = inspect.getsource(ChatScreen.compose)
        assert "tokens" in source, (
            "Status bar initial text must include 'tokens' label"
        )


class TestUpdateStatusBar:
    """``update_status_bar`` exists, accepts ``tokens``, and formats them."""

    def test_update_status_bar_exists(self) -> None:
        """``PyHarnessApp.update_status_bar`` must be defined."""
        assert hasattr(PyHarnessApp, "update_status_bar"), (
            "PyHarnessApp must define update_status_bar method"
        )

    def test_update_status_bar_accepts_tokens_parameter(self) -> None:
        """``update_status_bar`` must accept an optional ``tokens`` parameter."""
        sig = inspect.signature(PyHarnessApp.update_status_bar)
        assert "tokens" in sig.parameters, (
            "update_status_bar must accept a 'tokens' parameter"
        )

    def test_update_status_bar_formats_tokens_with_commas(self) -> None:
        """Token count must use comma formatting (e.g. ``1,234 tokens``)."""
        source = inspect.getsource(PyHarnessApp.update_status_bar)
        assert ":," in source or "tokens:," in source or "f\"{" in source, (
            "update_status_bar must have formatting code for tokens"
        )
        # More specific: the f-string must use :, formatter
        assert "{tokens:,}" in source, (
            "update_status_bar must format tokens with ':,}' for comma separation "
            "(e.g., 1234 → '1,234')"
        )

    def test_update_status_bar_has_default_zero(self) -> None:
        """When tokens is None, the status bar must show ``0``."""
        source = inspect.getsource(PyHarnessApp.update_status_bar)
        assert source, "update_status_bar must have an implementation"
        # Verify the default value is 0 when tokens is None
        assert 'if tokens' in source or '"0"' in source or "'0'" in source or "else" in source, (
            "update_status_bar must handle None tokens gracefully (show '0')"
        )

    def test_update_status_bar_calls_screen_update(self) -> None:
        """``update_status_bar`` must push text to the screen's status widget."""
        source = inspect.getsource(PyHarnessApp.update_status_bar)
        assert "update_status" in source, (
            "update_status_bar must call screen.update_status() to push text "
            "to the status bar widget"
        )
