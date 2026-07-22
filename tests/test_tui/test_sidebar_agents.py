"""Tests for sidebar AGENTS.md auto-load on mount (regression fix).

The bug: ``Sidebar.refresh_agents_md()`` existed but was *never* called.
The sidebar always showed "Run /init to create AGENTS.md" even when
``AGENTS.md`` existed in the project root.

The fix:
1. ``Sidebar.on_mount`` now calls ``self.refresh_agents_md()``
2. ``ChatScreen.on_mount`` also calls ``sidebar.refresh_agents_md()`` as safety net

These tests verify:
- The method exists and reads the right file (source inspection)
- ``on_mount`` triggers the refresh (source inspection)
- Runtime behaviour shows correct text when AGENTS.md exists
- Runtime behaviour shows correct text when AGENTS.md is absent
- ``ChatScreen.on_mount`` also triggers ``refresh_agents_md`` (source inspection)
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.sidebar import Sidebar
from textual.widgets import Static


# ---------------------------------------------------------------------------
# Source-inspection tests (no runtime needed)
# ---------------------------------------------------------------------------


class TestRefreshAgentsMdMethod:
    """Verify ``Sidebar.refresh_agents_md`` exists, is callable, and reads
    from the correct location."""

    def test_refresh_agents_md_exists_and_callable(self) -> None:
        """``Sidebar.refresh_agents_md`` must be a defined method."""
        assert hasattr(Sidebar, "refresh_agents_md"), (
            "Sidebar.refresh_agents_md method must exist"
        )
        assert callable(getattr(Sidebar, "refresh_agents_md")), (
            "Sidebar.refresh_agents_md must be callable"
        )

    def test_refresh_agents_md_reads_from_cwd(self) -> None:
        """The method must use ``Path.cwd() / "AGENTS.md"`` as its source."""
        source = inspect.getsource(Sidebar.refresh_agents_md)
        assert "Path.cwd()" in source, (
            "refresh_agents_md must read from Path.cwd()"
        )
        assert '"AGENTS.md"' in source or "'AGENTS.md'" in source, (
            "refresh_agents_md must reference AGENTS.md file"
        )

    def test_refresh_agents_md_checks_exists(self) -> None:
        """The method must call ``.exists()`` before reading."""
        source = inspect.getsource(Sidebar.refresh_agents_md)
        assert ".exists()" in source, (
            "refresh_agents_md must call .exists() before reading"
        )

    def test_refresh_agents_md_uses_query_one_agents_content(self) -> None:
        """The method must target ``#agents-content`` Static widget."""
        source = inspect.getsource(Sidebar.refresh_agents_md)
        assert "#agents-content" in source, (
            "refresh_agents_md must query #agents-content widget"
        )


class TestSidebarOnMount:
    """Verify ``Sidebar.on_mount`` calls ``self.refresh_agents_md()``."""

    def test_on_mount_exists(self) -> None:
        """``Sidebar`` must define ``on_mount``."""
        assert hasattr(Sidebar, "on_mount"), (
            "Sidebar must define on_mount"
        )

    def test_on_mount_calls_refresh_agents_md(self) -> None:
        """``Sidebar.on_mount`` source must contain ``refresh_agents_md``."""
        source = inspect.getsource(Sidebar.on_mount)
        assert "refresh_agents_md" in source, (
            "Sidebar.on_mount must call self.refresh_agents_md()"
        )


class TestSidebarComposeHasCorrectIds:
    """The sidebar compose must define the ``#agents-content`` widget that
    ``refresh_agents_md`` writes to."""

    def test_compose_yields_agents_content(self) -> None:
        """``Sidebar.compose`` must yield a Static with id ``agents-content``."""
        source = inspect.getsource(Sidebar.compose)
        assert 'id="agents-content"' in source or "id='agents-content'" in source, (
            "Sidebar.compose must define #agents-content Static widget"
        )

    def test_compose_yields_agents_header(self) -> None:
        """``Sidebar.compose`` must yield an AGENTS.md header."""
        source = inspect.getsource(Sidebar.compose)
        assert "AGENTS.md" in source, (
            "Sidebar.compose must include an AGENTS.md header"
        )


# ---------------------------------------------------------------------------
# Runtime tests (mount widget, exercise refresh)
# ---------------------------------------------------------------------------


class TestSidebarRuntimeAgentsMdFound:
    """Runtime: when AGENTS.md exists, the sidebar shows 'found:'."""

    async def test_sidebar_shows_found_when_file_exists(self) -> None:
        """Create a temp dir with AGENTS.md, mount Sidebar, refresh,
        and assert the rendered text contains 'found:' (not 'Run /init')."""
        from pyharness.tui.app import PyHarnessApp

        with tempfile.TemporaryDirectory() as td:
            agents_path = Path(td) / "AGENTS.md"
            agents_path.write_text("# Test Project\n\nThis is a test project.\n")

            app = PyHarnessApp()
            async with app.run_test() as pilot:
                sidebar = Sidebar(id="test-sidebar")
                await pilot.app.mount(sidebar)
                await pilot.pause()

                # Redirect Path.cwd() to our temp directory
                with patch("pathlib.Path.cwd", return_value=Path(td)):
                    sidebar.refresh_agents_md()

                await pilot.pause()

                content = sidebar.query_one("#agents-content", Static)
                text = str(content.content)

                assert "found:" in text, (
                    f"#agents-content must contain 'found:' when AGENTS.md exists. "
                    f"Got: {text!r}"
                )
                assert "Run /init" not in text, (
                    f"#agents-content must NOT contain 'Run /init' when AGENTS.md exists. "
                    f"Got: {text!r}"
                )

    async def test_sidebar_on_mount_loads_agents_md(self) -> None:
        """When Sidebar is mounted with an AGENTS.md in cwd, on_mount must
        populate the agents-content with found message."""
        from pyharness.tui.app import PyHarnessApp

        with tempfile.TemporaryDirectory() as td:
            agents_path = Path(td) / "AGENTS.md"
            agents_path.write_text("# Project Alpha\n\nDescription here.\n")

            app = PyHarnessApp()
            async with app.run_test() as pilot:
                sidebar = Sidebar(id="test-sidebar")

                with patch("pathlib.Path.cwd", return_value=Path(td)):
                    await pilot.app.mount(sidebar)
                    await pilot.pause()

                # on_mount should have triggered refresh_agents_md()
                content = sidebar.query_one("#agents-content", Static)
                text = str(content.content)

                assert "found:" in text, (
                    f"Sidebar.on_mount must populate agents-content when "
                    f"AGENTS.md exists. Got: {text!r}"
                )
                assert "Run /init" not in text, (
                    f"Sidebar.on_mount must NOT show 'Run /init' when "
                    f"AGENTS.md exists. Got: {text!r}"
                )


class TestSidebarRuntimeAgentsMdMissing:
    """Runtime: when AGENTS.md is missing, the sidebar shows 'Run /init'."""

    async def test_sidebar_shows_init_when_no_file(self) -> None:
        """Create an empty temp dir, mount Sidebar, refresh,
        and assert the rendered text contains 'Run /init'."""
        from pyharness.tui.app import PyHarnessApp

        with tempfile.TemporaryDirectory() as td:
            # No AGENTS.md in this directory
            assert not (Path(td) / "AGENTS.md").exists()

            app = PyHarnessApp()
            async with app.run_test() as pilot:
                sidebar = Sidebar(id="test-sidebar")
                await pilot.app.mount(sidebar)
                await pilot.pause()

                with patch("pathlib.Path.cwd", return_value=Path(td)):
                    sidebar.refresh_agents_md()

                await pilot.pause()

                content = sidebar.query_one("#agents-content", Static)
                text = str(content.content)

                assert "Run /init" in text, (
                    f"#agents-content must contain 'Run /init' when no "
                    f"AGENTS.md exists. Got: {text!r}"
                )
                assert "found:" not in text, (
                    f"#agents-content must NOT contain 'found:' when no "
                    f"AGENTS.md exists. Got: {text!r}"
                )

    async def test_sidebar_on_mount_shows_init_when_no_file(self) -> None:
        """When Sidebar is mounted without AGENTS.md in cwd, on_mount must
        show the 'Run /init' message."""
        from pyharness.tui.app import PyHarnessApp

        with tempfile.TemporaryDirectory() as td:
            assert not (Path(td) / "AGENTS.md").exists()

            app = PyHarnessApp()
            async with app.run_test() as pilot:
                sidebar = Sidebar(id="test-sidebar")

                with patch("pathlib.Path.cwd", return_value=Path(td)):
                    await pilot.app.mount(sidebar)
                    await pilot.pause()

                content = sidebar.query_one("#agents-content", Static)
                text = str(content.content)

                assert "Run /init" in text, (
                    f"Sidebar.on_mount must show 'Run /init' when no "
                    f"AGENTS.md exists. Got: {text!r}"
                )


# ---------------------------------------------------------------------------
# ChatScreen safety-net test
# ---------------------------------------------------------------------------


class TestChatScreenOnMount:
    """Verify ``ChatScreen.on_mount`` also triggers ``refresh_agents_md``."""

    def test_chat_screen_on_mount_calls_refresh(self) -> None:
        """``ChatScreen.on_mount`` source must reference ``refresh_agents_md``."""
        source = inspect.getsource(ChatScreen.on_mount)
        assert "refresh_agents_md" in source, (
            "ChatScreen.on_mount must call sidebar.refresh_agents_md()"
        )
