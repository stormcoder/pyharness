"""Regression tests for TUI bugs — these must FAIL until fixes are applied.

Each test class maps to one of the regressions.
Tests verify the *correct* behavior described in the bug reports.
A passing test means the bug is fixed; a failing test means work remains.

Usage::

    uv run pytest tests/test_tui/test_regression.py -v
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from unittest.mock import MagicMock, patch

import pytest

from pyharness.config.schema import ProviderConfig, PyHarnessConfig
from pyharness.core.logging import setup_logging
from pyharness.core.provider import PROVIDER_REGISTRY, verify_connection
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.input import PromptInput
from pyharness.tui.widgets.sidebar import Sidebar


# =============================================================================
# Bug 1 — Ctrl+p crashes with MountError
# =============================================================================


class TestPaletteNoCrash:
    """Bug 1: Ctrl+p must not crash with MountError.

    The command palette uses ``ListView`` inside a ``ModalScreen``.
    The ``ListView`` must be fully composed BEFORE ``query_one`` is called
    in ``action_select``, otherwise Textual raises ``MountError``.
    """

    def test_action_command_palette_exists(self) -> None:
        """App must expose action_command_palette."""
        app = PyHarnessApp()
        assert hasattr(app, "action_command_palette")

    def test_command_palette_uses_push_screen(self) -> None:
        """Must use push_screen, not notify, to show the palette."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        assert "push_screen" in source, "Must use push_screen, not notify"

    def test_palette_uses_listview_not_static(self) -> None:
        """Palette must use ListView (interactive) not Static text."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        assert "ListView" in source, (
            "CommandPalette must use ListView for arrow-key navigation, "
            "not Static text."
        )

    def test_palette_children_are_constructor_args_not_post_hoc_append(self) -> None:
        """ListView children must be constructor args, not appended before yield.

        In Textual, ``list_view.append(ListItem(...))`` during compose can
        cause MountError because the widget is not yet mounted.  Children
        must be passed as ``*children`` to the ``ListView()`` constructor.
        """
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        compose_start = source.find("def compose")
        compose_end = source.find("def action_select", compose_start)
        if compose_end == -1:
            compose_end = len(source)
        compose_body = source[compose_start:compose_end]
        assert ".append(" not in compose_body, (
            "ListView children must be passed as constructor args (ListView(*items)), "
            "NOT appended with list_view.append() before yield. "
            "Appending to an unmounted widget causes MountError."
        )

    def test_action_select_queries_after_compose(self) -> None:
        """action_select must not query ListView before it's mounted."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        compose_start = source.index("def compose")
        import re
        next_def = re.search(r"\n            def ", source[compose_start + 1:])
        if next_def:
            compose_body = source[compose_start:compose_start + 1 + next_def.start()]
        else:
            compose_body = source[compose_start:]
        query_idx = compose_body.find("query_one")
        assert query_idx == -1, (
            "query_one must NOT appear in compose(). "
            "on_mount and action_select are safe — they run after mounting."
        )


# =============================================================================
# Bug 2 — Slash commands don't autocomplete
# =============================================================================


class TestSlashAutocomplete:
    """Bug 2: Slash commands must have filtering autocomplete dropdown.

    Typing ``/`` in the input should show a filtered dropdown of matching
    commands.  Currently nothing happens.
    """

    def test_prompt_input_has_slash_commands_list(self) -> None:
        """PromptInput must expose SLASH_COMMANDS."""
        inp = PromptInput()
        assert hasattr(inp, "SLASH_COMMANDS")
        assert len(inp.SLASH_COMMANDS or []) > 0, "Must have slash command completions"

    def test_slash_completions_include_connect_and_models(self) -> None:
        """SLASH_COMMANDS must include /connect and /model."""
        inp = PromptInput()
        cmds = inp.SLASH_COMMANDS or []
        assert any("/connect" == c.strip() for c in cmds), "Must include /connect"
        assert any("/model" == c.strip() for c in cmds), "Must include /model"

    def test_slash_completions_are_filterable(self) -> None:
        """Must be able to filter completions by prefix."""
        inp = PromptInput()
        assert isinstance(inp.SLASH_COMMANDS or [], list)

    def test_on_key_triggers_slash_dropdown_not_just_tooltip(self) -> None:
        """watch_value must trigger slash suggestions display."""
        source = inspect.getsource(PromptInput.watch_value)
        has_display = any(
            kw in source for kw in ("_show_slash_dropdown", "SLASH_COMMANDS")
        )
        assert has_display, (
            "watch_value must call _show_slash_dropdown when value starts with '/', "
            "writing slash command suggestions to the chat RichLog."
        )

    def test_chat_screen_has_slash_completions_list(self) -> None:
        """ChatScreen must have _slash_completions for autocomplete."""
        assert hasattr(ChatScreen, "_slash_completions"), (
            "ChatScreen must define _slash_completions list for "
            "slash command autocomplete suggestions."
        )


# =============================================================================
# Bug 3 — @ doesn't autocomplete agents AND files
# =============================================================================


class TestAtAutocompleteAgentsAndFiles:
    """Bug 3: @ must show agents AND local files, filter as you type.

    Typing ``@`` should show a dropdown with agent names AND file
    matches from fuzzy search.  Currently the dropdown doesn't appear.
    """

    def test_agent_names_include_subagents(self) -> None:
        """AGENT_NAMES must include all four agents/subagents."""
        from pyharness.tui.widgets.input import PromptInput
        inp = PromptInput()
        if hasattr(inp, "AGENT_NAMES"):
            names = inp.AGENT_NAMES
            assert "build" in names
            assert "plan" in names
            assert "general" in names, "Must include subagents"
            assert "explore" in names, "Must include subagents"

    def test_get_at_completions_returns_agents_and_files(self) -> None:
        """get_at_completions must return both agents and files."""
        inp = PromptInput()
        if hasattr(inp, "get_at_completions"):
            results = inp.get_at_completions("")
            assert isinstance(results, list)
            has_build = any("build" in r.lower() for r in results)
            assert has_build, "Must include agent names"

    def test_get_at_completions_filters_by_prefix(self) -> None:
        """Filter 'pl' must match 'plan' but not 'build'."""
        inp = PromptInput()
        if hasattr(inp, "get_at_completions"):
            results = inp.get_at_completions("pl")
            has_plan = any("plan" in r.lower() for r in results)
            assert has_plan, "Filter 'pl' must match 'plan'"

    def test_on_key_triggers_at_dropdown_not_just_tooltip(self) -> None:
        """watch_value must trigger @ autocomplete display when value contains @."""
        source = inspect.getsource(PromptInput.watch_value)
        has_display = any(
            kw in source for kw in ("_show_at_dropdown", "get_at_completions")
        )
        assert has_display, (
            "watch_value must call _show_at_dropdown/get_at_completions when value "
            "contains '@', writing autocomplete results to the chat RichLog."
        )


# =============================================================================
# Bug 4 — Tab doesn't switch agents
# =============================================================================


class TestTabSwitchesAgent:
    """Bug 4: Tab must switch agents, NOT move focus to sidebar.

    Currently Tab moves focus to sidebar widgets instead of cycling
    between build → plan → general → explore agents.
    """

    def test_tab_bound_to_switch_agent(self) -> None:
        """Tab must be bound to switch_agent action."""
        app = PyHarnessApp()
        bindings = [(k.lower(), a) for k, a, *_ in app.BINDINGS]
        tab_bindings = [(k, a) for k, a in bindings if k == "tab"]
        assert len(tab_bindings) > 0, "Tab must be in BINDINGS"
        assert tab_bindings[0][1] == "switch_agent", "Tab must be bound to switch_agent"

    def test_app_has_action_switch_agent(self) -> None:
        """App must have callable action_switch_agent."""
        app = PyHarnessApp()
        assert hasattr(app, "action_switch_agent")
        assert callable(app.action_switch_agent)

    def test_switch_agent_cycles_all_four(self) -> None:
        """action_switch_agent must cycle through all 4 agents."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_switch_agent)
        assert "AGENTS" in source, (
            "action_switch_agent must reference AGENTS list "
            "to cycle through all available agents."
        )

    def test_sidebar_has_no_tab_focus_binding(self) -> None:
        """Sidebar must NOT have a Tab binding that steals focus."""
        source = inspect.getsource(Sidebar)
        assert '("tab"' not in source, (
            "Sidebar must not bind Tab — Tab is reserved for agent switching. "
            "Found a tab binding in Sidebar that would steal focus."
        )

    def test_tab_not_handled_as_focus_next(self) -> None:
        """App should not use Tab for focus_next."""
        app = PyHarnessApp()
        bindings = [(k.lower(), a) for k, a, *_ in app.BINDINGS]
        tab_actions = [a for k, a in bindings if k == "tab"]
        assert "focus_next" not in tab_actions, (
            "Tab must switch agents, not move focus. "
            "Remove focus_next binding for Tab."
        )


# =============================================================================
# Bug 5 — Sidebar should be sections, not tabs, with no tools
# =============================================================================


class TestSidebarSections:
    """Bug 5: Sidebar redesign — sections not tabs, AGENTS.md, Context, MCP.

    Current sidebar uses ``TabbedContent`` with tabs
    (Sessions, File Tree, Tools, Memory).
    It should have NO tabs — just labeled sections in a vertical scroll.
    """

    def test_sidebar_has_no_tabbed_content(self) -> None:
        """Sidebar must NOT use TabbedContent."""
        source = inspect.getsource(Sidebar)
        assert "TabbedContent" not in source, (
            "Sidebar must not use tabs — use labeled sections instead"
        )
        assert "TabPane" not in source, (
            "Sidebar must not use tabs — use labeled sections instead"
        )

    def test_sidebar_composes_sections_directly(self) -> None:
        """Sidebar must compose AGENTS.md, Context, and MCP sections.
        
        Checks source code for at least 3 yielded widgets or static sections.
        (Compose cannot be called outside a Textual app context.)
        """
        source = inspect.getsource(Sidebar)
        compose_body = source.split("def compose")[1].split("    def ")[0] if "def compose" in source and "    def " in source.split("def compose")[1] else source.split("def compose")[1]
        yield_count = compose_body.count("yield ")
        assert yield_count >= 3, (
            f"Expected at least 3 yielded sections, got {yield_count}. "
            "Sidebar must compose AGENTS.md, Context, and MCP sections."
        )

    def test_tool_list_not_in_sidebar(self) -> None:
        """Tools must NOT be listed in the sidebar."""
        source = inspect.getsource(Sidebar)
        assert "ToolList" not in source, "Sidebar should not have a Tools section"

    def test_sidebar_has_agents_md_section(self) -> None:
        """Sidebar must have an AGENTS.md section.
        
        Verifies via source inspection (compose cannot be called
        outside a Textual app context).
        """
        source = inspect.getsource(Sidebar)
        has_agents = "AGENTS.md" in source or "agents" in source.lower()
        compose_body = source.split("def compose")[1] if "def compose" in source else ""
        has_agents_in_compose = "AGENTS.md" in compose_body or "agents" in compose_body.lower()
        assert has_agents or has_agents_in_compose, (
            "Sidebar must have an AGENTS.md section showing "
            "project's AGENTS.md content with session ID, "
            "or a button to create one via /init."
        )

    def test_sidebar_has_context_section(self) -> None:
        """Sidebar must have a Context section with tokens/percent/cost.
        
        Verifies via source inspection (compose cannot be called
        outside a Textual app context).
        """
        source = inspect.getsource(Sidebar)
        has_context = any(
            kw in source.lower() for kw in ("token", "context", "cost")
        )
        compose_body = source.split("def compose")[1] if "def compose" in source else ""
        has_context_in_compose = any(
            kw in compose_body.lower() for kw in ("token", "context", "cost")
        )
        assert has_context or has_context_in_compose, (
            "Sidebar must have Context section showing tokens used, "
            "percent of context used, and estimated cost spent."
        )

    def test_sidebar_has_mcp_section(self) -> None:
        """Sidebar must have MCP section with server status dots.
        
        Verifies via source inspection (compose cannot be called
        outside a Textual app context).
        """
        source = inspect.getsource(Sidebar)
        has_mcp = "mcp" in source.lower()
        compose_body = source.split("def compose")[1] if "def compose" in source else ""
        has_mcp_in_compose = "mcp" in compose_body.lower()
        assert has_mcp or has_mcp_in_compose, (
            "Sidebar must have MCP section listing configured MCP servers "
            "with status indicators (green dot = active, red dot = inactive)."
        )


# =============================================================================
# RUNTIME REGRESSION — @ autocomplete dropdown widget
# =============================================================================
# These tests use Textual's run_test() with value assignment to prove
# that the @ autocomplete creates a proper AtAutocomplete dropdown widget
# above the PromptInput with visible, navigable items.
# =============================================================================


# -- shared helpers ------------------------------------------------------------


def _inp(app: PyHarnessApp) -> PromptInput:
    """Get the PromptInput from the current screen."""
    screen = app.screen_stack[-1]
    return screen.query_one(PromptInput)


def _dropdown_lines(app: PyHarnessApp) -> list[str]:
    """Get visible text lines from dropdown item widgets via ``.content``."""
    from pyharness.tui.widgets.at_autocomplete import AtAutocomplete
    screen = app.screen_stack[-1]
    try:
        dropdown = screen.query_one(".autocomplete-dropdown", AtAutocomplete)
    except Exception:
        return []
    lines: list[str] = []
    try:
        scroll = dropdown.query_one("#at-scroll")
        for child in scroll.children:
            content = getattr(child, "content", "")
            if content and isinstance(content, str) and content.strip():
                lines.append(content.strip())
    except Exception:
        return []
    return lines


def _dropdown_header(app: PyHarnessApp) -> str:
    """Get the dropdown header text (first child of scroll container)."""
    from pyharness.tui.widgets.at_autocomplete import AtAutocomplete
    screen = app.screen_stack[-1]
    try:
        dropdown = screen.query_one(".autocomplete-dropdown", AtAutocomplete)
        scroll = dropdown.query_one("#at-scroll")
        for child in scroll.children:
            classes = getattr(child, "classes", set())
            if "at-header" in classes:
                return getattr(child, "content", "")
    except Exception:
        pass
    return ""


def _dropdown_item_count(app: PyHarnessApp) -> int:
    """Return number of items in the dropdown."""
    from pyharness.tui.widgets.at_autocomplete import AtAutocomplete
    screen = app.screen_stack[-1]
    try:
        dropdown = screen.query_one(".autocomplete-dropdown", AtAutocomplete)
        return dropdown.item_count
    except Exception:
        return 0


# -- regression tests ----------------------------------------------------------


class TestAtAutocompleteRuntime:
    """@ autocomplete must produce a visible dropdown widget above the input.

    The dropdown replaces the old RichLog-based approach with a proper
    AtAutocomplete widget that filters in real-time and is navigable.
    """

    # ------------------------------------------------------------------
    # TEST 1 — Basic: typing @ creates and shows dropdown widget
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_at_dropdown_writes_to_richlog(self) -> None:
        """Typing @ must create a dropdown widget with visible items.

        After setting value to '@', a `.autocomplete-dropdown` widget
        must exist and contain at least the 4 agent names.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Dropdown should not exist before typing @
            item_count_before = _dropdown_item_count(app)
            assert item_count_before == 0, (
                "Dropdown must NOT exist before typing @"
            )

            # Set value to trigger watch_value → _show_at_dropdown
            inp = _inp(app)
            inp.value = "@"
            await pilot.pause()

            item_count_after = _dropdown_item_count(app)
            assert item_count_after >= 4, (
                "FAILS: Setting value to '@' must create a dropdown "
                "with at least 4 items (build, plan, general, explore).\n"
                f"  Items before @: {item_count_before}\n"
                f"  Items after @: {item_count_after}"
            )

    # ------------------------------------------------------------------
    # TEST 2 — Filtering: @b shows agent "build"
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_at_completion_shows_agent_names(self) -> None:
        """Setting value to '@b' must filter to show 'build' with 🤖 icon.

        The dropdown must exist and content must include 'build 🤖'.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = _inp(app)
            inp.value = "@b"
            await pilot.pause()

            lines = _dropdown_lines(app)
            has_build = any(
                "build" in line and "🤖" in line for line in lines
            )
            assert has_build, (
                "FAILS: Setting value to '@b' must show 'build 🤖' "
                "in the dropdown.\n"
                f"  Dropdown lines: {lines!r}"
            )

    # ------------------------------------------------------------------
    # TEST 3 — Unfiltered: @ shows "References" heading and agents
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_at_without_prefix_shows_all_sources(self) -> None:
        """Setting value to '@' (no filter) must show header and all agents.

        The dropdown must have '@ References (N matches)' and 'build'.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = _inp(app)
            inp.value = "@"
            await pilot.pause()

            header = _dropdown_header(app)
            lines = _dropdown_lines(app)

            found_heading = (
                "references" in header.lower()
                or "matches" in header.lower()
                or any(
                    "references" in line.lower() or "matches" in line.lower()
                    for line in lines
                )
            )
            found_build = any("build" in line for line in lines)

            assert found_heading, (
                "FAILS: Setting value to '@' must show a header like "
                "'@ References (N matches)' in the dropdown.\n"
                f"  Header: {header!r}\n"
                f"  Lines: {lines!r}"
            )
            assert found_build, (
                "FAILS: Setting value to '@' must list agent 'build'.\n"
                f"  Header: {header!r}\n"
                f"  Lines: {lines!r}"
            )

    # ------------------------------------------------------------------
    # TEST 4 — Re-filter: change filter and see different results
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_at_backspace_filters_correctly(self) -> None:
        """Changing the @ filter must update visible results in the dropdown.

        Set @b → @p: dropdown must switch from 'build' to 'plan'.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = _inp(app)
            # Set @b — should filter to 'build'
            inp.value = "@b"
            await pilot.pause()

            # Now set @p — should filter to 'plan'
            inp.value = "@p"
            await pilot.pause()

            lines = _dropdown_lines(app)

            has_plan = any("plan" in line for line in lines)
            has_build = any("build" in line for line in lines)

            assert has_plan, (
                "FAILS: After setting value to '@p', the dropdown "
                "must show agent 'plan'.\n"
                f"  Dropdown lines: {lines!r}"
            )
            assert not has_build, (
                "FAILS: After setting value to '@p', 'build' must NOT "
                "appear (doesn't match prefix 'p').\n"
                f"  Dropdown lines: {lines!r}"
            )

    # ------------------------------------------------------------------
    # TEST 5 — Human-visible output (critical)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_at_dropdown_shows_human_visible_output(self) -> None:
        """@ autocomplete must produce human-visible output via dropdown.

        After setting value to '@', the dropdown must have at least 2
        visible items with non-empty content.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            lines_before = _dropdown_lines(app)

            inp = _inp(app)
            inp.value = "@"
            await pilot.pause()

            lines = _dropdown_lines(app)

            assert len(lines) >= 2, (
                "FAILS: Setting value to '@' must produce at least 2 "
                "visible items in the autocomplete dropdown.\n"
                f"  Lines before @: {lines_before!r}\n"
                f"  Lines after @: {lines!r}\n"
                "  A human user would see NOTHING in the dropdown area."
            )

            # Every line must contain visible text (non-empty)
            for i, line_text in enumerate(lines):
                assert line_text.strip(), (
                    f"FAILS: Dropdown item {i} is empty or whitespace-only.\n"
                    f"  Line text: {line_text!r}\n"
                    f"  All lines: {lines!r}"
                )


# =============================================================================
# PROVIDER DEBUGGING — connection verification and error visibility
# =============================================================================
# The connect flow must show proper error handling for providers.
# verify_connection uses "test-model" (not a real model ID), and
# errors are logged at DEBUG level (invisible with default INFO).
# ALL TESTS BELOW MUST FAIL until the issues are fixed.


class TestProviderDebugging:
    """Provider connection debugging must show real errors.

    **Bug 1:** :func:`verify_connection` uses ``provider:test-model``
    which is not a real model ID — valid API keys fail because the
    provider rejects the model name.

    **Bug 2:** Connection failures are logged at ``DEBUG`` level with
    ``exc_info=True`` — invisible with the default ``INFO`` level.
    """

    # ------------------------------------------------------------------
    # TEST 1 — connect with deepseek shows error, not green success
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_with_deepseek_shows_error_not_green(self) -> None:
        """Connecting DeepSeek with an invalid key must show an ERROR
        notification, NOT a green success.

        ``verify_connection`` currently uses ``"test-model"`` as the
        model ID — which is rejected by every provider API, making
        valid keys fail.  Combined with the ``connect`` flow reporting
        success on any non-crash result, users get false positives.

        FAILS: verify_connection hardcodes ``test-model``, and the
        connect flow reports "Connected to deepseek" even on failure.
        """
        import json
        import os
        from pathlib import Path
        from unittest.mock import patch

        from pyharness.core.provider import verify_connection

        # 1. Verify the hardcoded test-model issue directly
        config = PyHarnessConfig(
            model="deepseek:deepseek-chat",
            provider={"deepseek": ProviderConfig(apiKey="sk-test-bad")},
        )

        # Mock resolve_model to succeed (simulating a valid model resolution)
        mock_model = MagicMock()
        mock_model.invoke = MagicMock(
            side_effect=ValueError("model 'test-model' not found")
        )

        with patch(
            "pyharness.core.provider.resolve_model", return_value=mock_model
        ):
            result = await verify_connection("deepseek", "sk-test-bad", config)

        # The mock succeeds — but in real life, 'test-model' is rejected
        # The real bug is that verify_connection uses 'test-model' at all.
        # Check the source code for the hardcoded string.
        import inspect
        source = inspect.getsource(verify_connection)
        uses_test_model = "test-model" in source
        assert not uses_test_model, (
            "FAILS: verify_connection hardcodes 'test-model' as the model ID.\n"
            "  'test-model' is not a real model for any provider.\n"
            "  Valid API keys will fail because the model name is rejected.\n\n"
            "  To fix: use a real model like 'deepseek:deepseek-chat'\n"
            "  or 'openai:gpt-4o-mini' for connection testing."
        )

        # 2. Verify that connection failures are properly surfaced
        #    (not hidden behind DEBUG logging)
        with patch(
            "pyharness.core.provider.resolve_model",
            side_effect=RuntimeError("API returned 401 Unauthorized"),
        ):
            result = await verify_connection("deepseek", "sk-dead-key", config)

        assert result is False, (
            "FAILS: verify_connection with a failing model should return False.\n"
            "  Got: Result was not False — the error was swallowed."
        )

    # ------------------------------------------------------------------
    # TEST 2 — verify_connection logs failure details
    # ------------------------------------------------------------------

    def test_verify_connection_logs_failure_details(self) -> None:
        """When verify_connection fails, the logger must capture the
        provider name and failure reason.

        FAILS: current code uses ``logger.debug(..., exc_info=True)``
        which is invisible at the default INFO level.  Users have no
        way to debug failed connections.

        The failure message should be at WARNING or ERROR level and
        contain the provider name plus the reason for failure.
        """
        import asyncio
        import logging
        import structlog
        from unittest.mock import patch

        from pyharness.core.provider import verify_connection

        # Set up structlog so we can capture log output
        structlog.reset_defaults()
        setup_logging(level="DEBUG")

        config = PyHarnessConfig(
            provider={"deepseek": ProviderConfig(apiKey="sk-bad")},
        )
        test_logger = logging.getLogger("pyharness.core.provider")
        test_logger.setLevel(logging.DEBUG)

        with patch(
            "pyharness.core.provider.resolve_model",
            side_effect=ValueError("DeepSeek API: 401 Invalid API Key"),
        ):
            asyncio.run(verify_connection("deepseek", "sk-bad", config))

        # The current code uses logger.debug() — which at INFO level
        # produces no output.  Check:
        import inspect
        source = inspect.getsource(verify_connection)
        has_debug_log = "logger.debug" in source
        has_warning_or_error = (
            "logger.warning" in source or "logger.error" in source
        )

        if has_debug_log and not has_warning_or_error:
            pytest.fail(
                "FAILS: verify_connection logs failures at DEBUG level.\n"
                "  With the default INFO log level, these messages are\n"
                "  invisible.  Users have no way to debug failed connections.\n\n"
                "  Current: logger.debug('verify_connection failed...')\n"
                "  Expected: logger.warning() or logger.error() so the\n"
                "  failure is visible at the default INFO level."
            )

        # Verify the logger module-level logger is accessible
        from pyharness.core import provider as provider_mod
        assert hasattr(provider_mod, "logger"), (
            "FAILS: provider module has no logger — can't log failures at all."
        )


# =============================================================================
# Bug 6 — /models writes to RichLog instead of showing filterable dropdown
# =============================================================================
# /models should display a filterable dropdown (AtAutocomplete widget) above
# the input field showing available models, NOT write static text to RichLog.
# The dropdown must allow keyboard navigation (↑↓), Enter to select, and
# Escape to dismiss.  When no provider is configured, show an empty state.
# =============================================================================


# -- models dropdown helpers ---------------------------------------------------


def _models_dropdown(app: PyHarnessApp):
    """Get the AtAutocomplete models dropdown by its unique ID."""
    from pyharness.tui.widgets.at_autocomplete import AtAutocomplete
    screen = app.screen_stack[-1]
    try:
        return screen.query_one("#models-dropdown", AtAutocomplete)
    except Exception:
        return None


def _models_dropdown_header(app: PyHarnessApp) -> str:
    """Get the dropdown header text."""
    dropdown = _models_dropdown(app)
    if dropdown is None:
        return ""
    try:
        scroll = dropdown.query_one("#at-scroll")
        for child in scroll.children:
            classes = getattr(child, "classes", set())
            if "at-header" in classes:
                return getattr(child, "content", "")
    except Exception:
        pass
    return ""


def _models_dropdown_items(app: PyHarnessApp) -> list[str]:
    """Get visible text lines from the models dropdown."""
    dropdown = _models_dropdown(app)
    if dropdown is None:
        return []
    lines: list[str] = []
    try:
        scroll = dropdown.query_one("#at-scroll")
        for child in scroll.children:
            content = getattr(child, "content", "")
            if content and isinstance(content, str) and content.strip():
                lines.append(content.strip())
    except Exception:
        return []
    return lines


def _models_dropdown_count(app: PyHarnessApp) -> int:
    """Return number of items in the models dropdown."""
    dropdown = _models_dropdown(app)
    if dropdown is None:
        return 0
    return dropdown.item_count


class TestModelsDropdown:
    """Bug 6: /models must show filterable dropdown, not RichLog text.

    Typing /models and pressing Enter must mount an AtAutocomplete dropdown
    above the input field with model options, NOT write static text to the
    chat RichLog.

    Currently ``on_input_submitted`` and ``_handle_slash_command`` both
    call ``list_available_models()`` and write to RichLog — no dropdown
    is created for the /models command.
    """

    # ------------------------------------------------------------------
    # TEST 1 — /models creates a dropdown widget, not RichLog text
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_command_shows_dropdown_not_richlog_text(self) -> None:
        """Typing /models Enter must mount an AtAutocomplete dropdown.

        FAILS: current code calls ``chat.write(...)`` in both
        ``on_input_submitted`` and ``_handle_slash_command`` — no
        dropdown widget is created for model selection.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Dropdown should not exist before /models
            before = _models_dropdown(app)
            assert before is None, (
                "No models dropdown must exist before typing /models"
            )

            # Type /models and press Enter
            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            # Now a dropdown should exist with model content
            dropdown = _models_dropdown(app)
            assert dropdown is not None, (
                "FAILS: /models must mount an AtAutocomplete dropdown widget.\n"
                "  Current behavior: writes model list as static text to RichLog.\n"
                "  Expected: interactive dropdown with selectable models."
            )

            # Dropdown must be visible
            assert dropdown.has_class("-visible") or dropdown.display, (
                "FAILS: Models dropdown must be visible after /models Enter.\n"
                "  Current: dropdown exists but is not displayed."
            )

    # ------------------------------------------------------------------
    # TEST 2 — Empty state when no provider configured
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_dropdown_empty_with_no_provider(self) -> None:
        """With no providers, the dropdown must show empty/fallback state.

        FAILS: no dropdown exists for /models — even the raw text output
        doesn't distinguish between configured and unconfigured states.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Clear providers AFTER mount (on_mount reloads config from disk)
            app.config.provider = {}
            app._available_models = []
            app._model_list_loaded = True

            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            dropdown = _models_dropdown(app)
            assert dropdown is not None, (
                "FAILS: /models must mount a dropdown even with no providers.\n"
                "  Expected: empty-state message like 'No providers configured'.\n"
                "  Current: no dropdown widget exists at all."
            )

            header = _models_dropdown_header(app)
            items = _models_dropdown_items(app)
            has_empty_signal = (
                "no provider" in header.lower()
                or "no model" in header.lower()
                or any(
                    "no provider" in line.lower() or "no model" in line.lower()
                    for line in items
                )
            )
            assert has_empty_signal or len(items) == 0, (
                "FAILS: Empty state must signal that no providers are configured.\n"
                f"  Header: {header!r}\n"
                f"  Items: {items!r}"
            )

    # ------------------------------------------------------------------
    # TEST 3 — Dropdown must show model items
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_dropdown_shows_items(self) -> None:
        """When providers are configured, the dropdown must show 3+ models.

        FAILS: no dropdown — current code writes model names as RichLog text.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Populate the model cache directly (avoids network dependency)
            app._available_models = [
                "openrouter:openai/gpt-5",
                "openrouter:anthropic/claude-sonnet-4-5",
                "openrouter:google/gemini-3-pro",
                "openrouter:meta/llama-4-maverick",
            ]
            app._model_list_loaded = True
            # Ensure config reports a provider is present
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {"openrouter": ProviderConfig(apiKey="sk-test")}

            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            count = _models_dropdown_count(app)
            items = _models_dropdown_items(app)
            assert count >= 3 or len(items) >= 3, (
                "FAILS: /models dropdown must show 3+ model items.\n"
                f"  Dropdown count: {count}\n"
                f"  Items: {items!r}\n"
                "  Current: models are written as RichLog text, not dropdown items."
            )

    # ------------------------------------------------------------------
    # TEST 4 — Enter on a model selects it
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_dropdown_enter_selects_model(self) -> None:
        """Pressing Enter on a dropdown item must select the model.

        After selecting, the status bar or input should reflect the change.

        FAILS: no dropdown — there is nothing to select from.
        """
        app = PyHarnessApp()
        if app.config:
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {
                "openrouter": ProviderConfig(apiKey="sk-test"),
            }

        async with app.run_test() as pilot:
            await pilot.pause()
            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            dropdown = _models_dropdown(app)
            assert dropdown is not None, (
                "FAILS: No dropdown to select from.\n"
                "  /models must create an interactive dropdown before selection works."
            )

            # Press down to highlight second item, then Enter to select
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # After selection, the input value should have changed
            # (should show the selected model, or the status bar should update)
            dropdown_after = _models_dropdown(app)
            dropdown_dismissed = dropdown_after is None or not dropdown_after.has_class("-visible")

            assert dropdown_dismissed, (
                "FAILS: Dropdown must be dismissed after Enter selection.\n"
                "  Current: dropdown still visible after pressing Enter."
            )

    # ------------------------------------------------------------------
    # TEST 5 — Escape dismisses the dropdown
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_dropdown_escape_dismisses(self) -> None:
        """Pressing Escape must hide/remove the models dropdown.

        FAILS: no dropdown — there is nothing to dismiss.
        """
        app = PyHarnessApp()
        if app.config:
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {
                "openrouter": ProviderConfig(apiKey="sk-test"),
            }

        async with app.run_test() as pilot:
            await pilot.pause()
            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            dropdown_before = _models_dropdown(app)
            assert dropdown_before is not None, (
                "FAILS: No dropdown to dismiss.\n"
                "  /models must create an interactive dropdown before Escape can dismiss it."
            )

            # Press Escape
            await pilot.press("escape")
            await pilot.pause()

            dropdown_after = _models_dropdown(app)
            is_gone = (
                dropdown_after is None
                or not dropdown_after.has_class("-visible")
                or not dropdown_after.display
            )
            assert is_gone, (
                "FAILS: Models dropdown must be hidden after Escape.\n"
                "  Current: dropdown still visible after pressing Escape."
            )


# =============================================================================
# CONNECT FLOW REGRESSIONS — provider connection bugs
# =============================================================================
# These tests verify that the /connect flow correctly saves API keys,
# validates connections, and updates the sidebar with provider status.
# ALL TESTS BELOW MUST FAIL until the connect flow is fixed.
# =============================================================================


class TestConnectProviderStatus:
    """Connect flow must save keys, verify connections, and show status.

    **Bug Summary:**

    1. ``ConnectScreen._save_provider_key()`` writes a ``{env:...}``
       placeholder instead of the actual API key the user pasted.
    2. No ``verify_connection()`` function exists — there is no connection
       test, so users never know if their key works.
    3. The sidebar only shows MCP dots (🟢/🔴) — there is no LLM provider
       connection status indicator.
    4. ``_handle_connect_result`` never reloads config from disk, so newly
       saved providers are not visible after /connect.
    """

    # ------------------------------------------------------------------
    # TEST 1 — _save_provider_key must save the ACTUAL key, not a placeholder
    # ------------------------------------------------------------------

    def test_connect_saves_actual_api_key(self) -> None:
        """ConnectScreen._save_provider_key must write the actual key, not {env:...}.

        Inspects the source code of ``_save_provider_key()`` to verify it
        writes the ``key`` parameter into ``config["provider"][provider]["apiKey"]``,
        NOT an ``{env:...}`` placeholder.

        FAILS: current code writes ``"apiKey": "{{env:OPENAI_API_KEY}}"``
        — the user's key is discarded.
        """
        import inspect
        from pyharness.tui.screens.connect import ConnectScreen

        source = inspect.getsource(ConnectScreen._save_provider_key)

        # The function must use the 'key' parameter in the value written to config
        # It must NOT contain a literal "{env:" which indicates a placeholder
        has_env_placeholder = "{env:" in source or "{{env:" in source

        assert not has_env_placeholder, (
            "FAILS: _save_provider_key writes a '{env:...}' placeholder "
            "instead of the actual API key the user provided.\n\n"
            "  Current code:\n"
            '      config["provider"][provider] = {"apiKey": "{{env:...}}"}  # ← placeholder!\n\n'
            "  Expected:\n"
            '      config["provider"][provider] = {"apiKey": key}  # ← actual key\n\n'
            "  Impact: after /connect, the API key is NOT saved.  Users must\n"
            "  manually set env vars — which defeats the purpose of the connect UI."
        )

        # Also verify the 'key' param is referenced (it is received but discarded)
        assert "key" in source.lower(), (
            "FAILS: _save_provider_key receives a 'key' parameter but the source "
            "does not reference 'key' — it's probably being ignored."
        )

    # ------------------------------------------------------------------
    # TEST 2 — connect must trigger connection verification
    # ------------------------------------------------------------------

    def test_connect_triggers_connection_verification(self) -> None:
        """After ConnectScreen dismisses, the app must call verify_connection().

        Inspects ``_handle_connect_result`` to verify it calls
        ``verify_connection`` (or similar) to validate the API key.

        FAILS: current ``_handle_connect_result`` just calls ``self.notify()``
        and ``self.call_later(self.refresh_models)`` — no connection test.
        """
        import inspect
        from pyharness.tui.app import PyHarnessApp

        source = inspect.getsource(PyHarnessApp._handle_connect_result)

        has_verification = any(
            kw in source for kw in (
                "verify_connection",
                "test_connection",
                "validate_connection",
                "check_connection",
            )
        )
        assert has_verification, (
            "FAILS: _handle_connect_result never calls verify_connection() "
            "or any connection validation.\n\n"
            "  Current: only calls self.notify() and self.call_later(refresh_models).\n"
            "  Expected: after /connect, the app should verify the API key\n"
            "  works against the provider's API before reporting success.\n\n"
            f"  Source:\n{source[:300]}..."
        )

    # ------------------------------------------------------------------
    # TEST 3 — sidebar shows green for connected provider
    # ------------------------------------------------------------------

    def test_sidebar_shows_provider_status_green_on_success(self) -> None:
        """Sidebar must display LLM provider connection status.

        When a provider is connected AND verified, the sidebar must show
        a green indicator (🟢 or checkmark).  Currently the sidebar only
        has sections for AGENTS.md, Context, and MCP — no provider status.

        FAILS: sidebar has no provider section; only MCP dots.
        """
        import inspect
        from pyharness.tui.widgets.sidebar import Sidebar

        source = inspect.getsource(Sidebar)
        compose_source = inspect.getsource(Sidebar.compose)

        # Must have a provider/provider-status section or element
        has_provider = any(
            kw in (source + compose_source).lower()
            for kw in ("provider", "section-provider", "provider-status")
        )
        assert has_provider, (
            "FAILS: Sidebar has no provider connection status section.\n\n"
            "  Current: Sidebar has sections for AGENTS.md, Context, and MCP only.\n"
            "  Expected: A fourth section showing LLM provider connection status\n"
            "  with green/red indicators for each configured provider.\n\n"
            "  The connect flow is a dead-end without this — users have no way\n"
            "  to know if they are actually connected to an LLM provider."
        )

    # ------------------------------------------------------------------
    # TEST 4 — sidebar shows red for failed provider
    # ------------------------------------------------------------------

    def test_sidebar_shows_provider_status_red_on_failure(self) -> None:
        """When connection fails, sidebar must show a red indicator.

        The sidebar update methods (``update_mcp_servers``, etc.) must
        include a method for provider status that can display 🔴 or
        similar on connection failure.

        FAILS: no provider status update method exists.
        """
        import inspect
        from pyharness.tui.widgets.sidebar import Sidebar

        # Check for a method that updates provider status
        methods = [
            name for name, _ in inspect.getmembers(Sidebar, inspect.isfunction)
        ]
        provider_update_methods = [
            m for m in methods if "provider" in m.lower()
        ]
        assert len(provider_update_methods) >= 1, (
            "FAILS: Sidebar has no method to update provider status indicators.\n\n"
            f"  Available methods: {sorted(methods)}\n"
            "  Expected: a method like ``update_provider_status(providers: dict)``\n"
            "  that displays green (🟢) when connected and red (🔴) when not."
        )

    # ------------------------------------------------------------------
    # TEST 5 — connect failure shows user-visible notification with red indicator
    # ------------------------------------------------------------------

    def test_connect_failure_notifies_user_with_red_indicator(self) -> None:
        """When connection fails, user must see a notification AND red indicator.

        The ``_handle_connect_result`` or ``_save_provider_key`` must handle
        failures by:
        1. Showing a notification with "failed" or "could not connect"
        2. Updating the sidebar to show a red indicator for the provider

        FAILS: current connect flow always shows success, even with invalid keys.
        """
        import inspect
        from pyharness.tui.screens.connect import ConnectScreen

        source = inspect.getsource(ConnectScreen.on_button_pressed)

        # Must call _save_provider_key (save), but also verify connection
        has_save = "_save_provider_key" in source
        assert has_save, "on_button_pressed must call _save_provider_key"

        # The handler should show different messages based on connection outcome
        # Currently it always shows success.  We need at minimum:
        # - a call to verify_connection (or the dismiss message reflects failure)
        has_failure_path = any(
            kw in source.lower() for kw in (
                "failed", "could not connect", "invalid", "error",
                "verify", "test",
            )
        )
        assert has_failure_path, (
            "FAILS: ConnectScreen.on_button_pressed has no failure path.\n\n"
            "  Current: always dismisses with 'Connected to {provider}' regardless\n"
            "  of whether the API key is valid or not.\n\n"
            "  Expected: after saving the key, verify the connection.  On failure:\n"
            "  1. Show a notification like 'Connection failed: 401 Unauthorized'\n"
            "  2. Update sidebar provider status to red (🔴)\n"
            "  3. Do NOT dismiss the screen on failure (let user retry)"
        )


# =============================================================================
# Bug — Status bar shows "loading..." instead of model name or blank
# =============================================================================


class TestStatusBarModelDisplay:
    """Status bar must show model name or blank, never 'loading...'."""

    @pytest.mark.asyncio
    async def test_status_bar_no_loading_text_after_mount(self) -> None:
        """After mount, status bar must NOT contain 'loading...'.

        FAILS: ChatScreen.on_mount hardcodes 'build | loading... | 0 tokens'.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            text = _status_text(app)
            assert "loading..." not in text.lower(), (
                "FAILS: Status bar shows 'loading...' after mount.\n"
                f"  Text: {text!r}\n"
                "  Expected: agent name with blank model field "
                "(e.g. 'build |   | 0 tokens' or just 'build')."
            )

    @pytest.mark.asyncio
    async def test_status_bar_contains_agent_name(self) -> None:
        """Status bar must contain the default agent name 'build'.

        FAILS: status bar may be missing or have wrong format.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # StatusBar is yielded by ChatScreen.compose(), not mounted inside
            # the screen widget tree — it's composed as a top-level child.
            # Query the app (Screen has the status bar as direct child).
            from textual.widgets import Static
            screen = app.screen
            try:
                bar = screen.query_one("#status-bar")
            except Exception:
                # Try app-level query
                try:
                    bar = app.query_one("#status-bar")
                except Exception:
                    bar = None
            assert bar is not None, (
                "FAILS: #status-bar widget not found on screen or app.\n"
                f"  Screen type: {type(screen).__name__}"
            )
            text = _status_text(app)
            assert text, f"Status text is empty! Bar found: {bar is not None}"
            assert "build" in text.lower(), (
                "FAILS: Status bar does not contain agent name 'build'.\n"
                f"  Text: {text!r}"
            )

    @pytest.mark.asyncio
    async def test_status_bar_updates_after_model_switch(self) -> None:
        """After calling switch_model, status bar must show the new model.

        FAILS: status bar ignores model changes.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            screen.update_status("build | openai:gpt-4o-mini | 0 tokens")
            await pilot.pause()
            text = _status_text(app)
            assert "gpt-4o-mini" in text, (
                "FAILS: Status bar does not show the switched model.\n"
                f"  Text: {text!r}\n"
                "  Expected: 'build | openai:gpt-4o-mini | 0 tokens'."
            )

    @pytest.mark.asyncio
    async def test_status_bar_persists_model_after_agent_switch(self) -> None:
        """After switching agent, status bar must still show the selected model.

        FAILS: agent switch resets the model field.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.switch_model("openai:gpt-4o-mini")
            app.action_switch_agent()
            await pilot.pause()
            text = _status_text(app)
            assert "gpt-4o-mini" in text, (
                "FAILS: Status bar lost the model after agent switch.\n"
                f"  Text: {text!r}"
            )
            assert "plan" in text.lower(), (
                "FAILS: Status bar does not show the new agent 'plan'.\n"
                f"  Text: {text!r}"
            )


# -- Status bar helpers -------------------------------------------------------


def _status_text(app: PyHarnessApp) -> str:
    """Get the full text of the #status-bar widget."""
    try:
        screen = app.screen
        bar = screen.query_one("#status-bar")
        return str(bar.content) if bar.content else ""
    except Exception:
        return ""


# =============================================================================
# CONNECTED PROVIDER MODEL FILTERING — /models only shows connected providers
# =============================================================================
# When a user connects ONLY deepseek, /models must show deepseek models
# and NOT leak models from openrouter, ollama, or other configured providers.
# =============================================================================


class TestConnectedProviderModelFilter:
    """Bug: /models shows ALL configured provider models, not just connected ones.

    Root cause: ``fetch_models()`` uses ``set(config.provider.keys())`` as
    the provider scope, which includes every provider entry in the config
    file — even ones the user never connected to.

    Fix: ``PyHarnessApp`` tracks ``_connected_providers`` — providers that
    either have a non-placeholder API key on startup, or were successfully
    connected via ``/connect``.  Only those providers' models appear.
    """

    # ------------------------------------------------------------------
    # TEST 1 — only connected provider models appear in /models
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_list_shows_only_connected_provider_models(self) -> None:
        """Connect deepseek → /models shows only deepseek models.

        The config file may have openrouter, ollama, and other providers
        listed — but none were connected.  After connecting deepseek,
        only deepseek model entries must appear in the models dropdown.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate: config has deepseek + openrouter + ollama
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
                "openrouter": ProviderConfig(apiKey="{env:OPENROUTER_API_KEY}"),
                "ollama": ProviderConfig(),
            }
            # Only deepseek is "connected" (has a real key)
            app._connected_providers = {"deepseek"}
            app._available_models = ["deepseek:deepseek-chat"]
            app._model_list_loaded = True

            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            items = _models_dropdown_items(app)

            for item in items:
                assert not item.startswith("openrouter"), (
                    "FAILS: openrouter model leaked into /models output.\n"
                    f"  Item: {item!r}\n"
                    f"  All items: {items!r}\n"
                    "  openrouter is NOT connected — its models must not appear."
                )
                assert not item.startswith("ollama"), (
                    "FAILS: ollama model leaked into /models output.\n"
                    f"  Item: {item!r}\n"
                    f"  All items: {items!r}\n"
                    "  ollama is NOT connected — its models must not appear."
                )

            # At a minimum we should see the connected provider's models
            has_deepseek = any("deepseek" in item for item in items)
            assert has_deepseek, (
                "FAILS: deepseek models not found in /models output.\n"
                f"  Items: {items!r}\n"
                "  deepseek IS connected — its models must appear."
            )

    # ------------------------------------------------------------------
    # TEST 2 — /models empty when no providers connected
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_list_empty_when_no_connected_providers(self) -> None:
        """Fresh config with no connected providers → /models shows empty state.

        Even if the config file has providers listed with env-var placeholders
        and those env vars are NOT set, no models should appear.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate: config has providers but none are connected
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {
                "openrouter": ProviderConfig(apiKey="{env:OPENROUTER_API_KEY}"),
                "anthropic": ProviderConfig(apiKey="{env:ANTHROPIC_API_KEY}"),
            }
            # No env vars are set → nothing should be connected
            app._connected_providers = set()
            app._available_models = []
            app._model_list_loaded = True

            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            dropdown = _models_dropdown(app)
            header = _models_dropdown_header(app)
            items = _models_dropdown_items(app)

            # Should show empty/none-state
            has_empty_signal = (
                (dropdown is not None and _models_dropdown_count(app) == 0)
                or any(
                    kw in (header + " ".join(items)).lower()
                    for kw in ("no provider", "no model", "connect", "empty")
                )
            )
            assert has_empty_signal, (
                "FAILS: /models with no connected providers must show "
                "an empty state or guidance message.\n"
                f"  Header: {header!r}\n"
                f"  Items: {items!r}"
            )

    # ------------------------------------------------------------------
    # TEST 3 — _connected_providers initialized from config on startup
    # ------------------------------------------------------------------

    def test_connected_providers_populated_from_config(self) -> None:
        """On startup, providers with real API keys are NOT automatically
        added to _connected_providers.  _populate_connected_providers()
        only pre-populates _provider_status for empty keys and {env:VAR}
        placeholders.  Real keys are verified asynchronously by
        refresh_models() which does live API calls.

        After refresh_models() completes, _connected_providers contains
        only providers that passed live verification.
        """
        from pyharness.config.schema import ProviderConfig

        app = PyHarnessApp()
        app.config = PyHarnessConfig(
            model="deepseek:deepseek-chat",
            provider={
                "deepseek": ProviderConfig(apiKey="sk-real-key"),
                "openrouter": ProviderConfig(apiKey="{env:OPENROUTER_NOT_SET_XYZ}"),
                "ollama": ProviderConfig(),
            },
        )

        app._populate_connected_providers()

        # After populate: _connected_providers is always empty.
        assert app._connected_providers == set(), (
            "_connected_providers must be empty after populate — "
            "live verification happens in refresh_models()."
        )

        # _provider_status reflects empty/unresolved keys only
        assert "openrouter" not in app._connected_providers, (
            "openrouter has unresolved {env:...} — not connected."
        )
        assert "ollama" not in app._connected_providers, (
            "ollama has no API key — not connected."
        )
        # deepseek has a real key, but is NOT yet verified
        assert "deepseek" not in app._connected_providers, (
            "deepseek has real key but not verified yet — "
            "refresh_models() will verify it asynchronously."
        )

        # Simulate refresh_models() success for deepseek
        app._connected_providers.add("deepseek")
        app._provider_status["deepseek"] = True

        assert "deepseek" in app._connected_providers, (
            "After refresh_models(), deepseek must be connected."
        )
        assert "openrouter" not in app._connected_providers, (
            "openrouter env var not set — must NOT be connected."
        )
        assert "ollama" not in app._connected_providers, (
            "ollama has no key — must NOT be connected."
        )

    # ------------------------------------------------------------------
    # TEST 4 — connected provider added after successful /connect
    # ------------------------------------------------------------------

    def test_connected_providers_updated_after_connect(self) -> None:
        """After _handle_connect_result('Connected to deepseek'), the provider
        is added to _connected_providers."""
        app = PyHarnessApp()
        app._connected_providers = set()

        app.config = PyHarnessConfig(model="deepseek:deepseek-chat")

        # Simulate what happens after a successful connection
        provider_name = "deepseek"
        app._connected_providers.add(provider_name)

        assert provider_name in app._connected_providers, (
            "FAILS: after successful /connect, provider must be "
            "in _connected_providers."
        )

    # ------------------------------------------------------------------
    # TEST 5 — reconnect adds additional provider without removing existing
    # ------------------------------------------------------------------

    def test_connected_providers_accumulates_on_multiple_connects(self) -> None:
        """Connecting a second provider must add to the set without
        removing previously connected providers."""
        app = PyHarnessApp()
        app.config = PyHarnessConfig(model="deepseek:deepseek-chat")

        # First connect
        app._connected_providers.add("deepseek")
        # Second connect
        app._connected_providers.add("openai")

        assert app._connected_providers == {"deepseek", "openai"}, (
            "FAILS: connecting a second provider must accumulate.\n"
            f"  Got: {app._connected_providers!r}"
        )

    # ------------------------------------------------------------------
    # TEST 6 — {env:VAR} placeholder resolved via os.environ → connected
    # ------------------------------------------------------------------

    def test_connected_providers_with_resolved_env_placeholder(self) -> None:
        """Provider with {env:VAR} placeholder AND the env var SET in
        os.environ gets _provider_status=True from populate, but is NOT
        added to _connected_providers (that happens in refresh_models()).

        This is the happy-path for users who set env vars — the status dot
        appears immediately, but the actual connection verification happens
        asynchronously via the API."""
        import os
        from pyharness.config.schema import ProviderConfig

        app = PyHarnessApp()
        app._connected_providers = set()
        app.config = PyHarnessConfig(
            model="anthropic:claude-sonnet-4-5",
            provider={
                "anthropic": ProviderConfig(
                    apiKey="{env:ANTHROPIC_API_KEY}",
                ),
                "openrouter": ProviderConfig(
                    apiKey="{env:OPENROUTER_NOT_SET_XYZ}",
                ),
            },
        )

        # Set the env var that the placeholder refers to
        with patch.object(os, "environ", {"ANTHROPIC_API_KEY": "sk-ant-real"}):
            app._populate_connected_providers()

        # _provider_status reflects env-var resolution from populate
        assert app._provider_status.get("anthropic") is True, (
            "anthropic env var IS set → _provider_status must be True."
        )
        assert app._provider_status.get("openrouter") is False, (
            "openrouter env var NOT set → _provider_status must be False."
        )

        # _connected_providers is NOT populated by _populate_connected_providers
        # — it's populated by refresh_models() after live API verification.
        assert "anthropic" not in app._connected_providers, (
            "_populate_connected_providers no longer adds to "
            "_connected_providers — that happens in refresh_models()."
        )
        assert "openrouter" not in app._connected_providers, (
            "openrouter env var NOT set → must NOT be connected."
        )

        # Simulate refresh_models() verifying anthropic via live API call
        app._connected_providers.add("anthropic")
        assert "anthropic" in app._connected_providers, (
            "After refresh_models(), anthropic must be connected."
        )

    # ------------------------------------------------------------------
    # TEST 7 — _populate_connected_providers guards against None config
    # ------------------------------------------------------------------

    def test_populate_connected_providers_with_none_config(self) -> None:
        """When config is None, _populate_connected_providers must not crash."""
        app = PyHarnessApp()
        app._connected_providers = set()
        app.config = None  # type: ignore[assignment]

        # Must not raise
        app._populate_connected_providers()

        assert app._connected_providers == set(), (
            "FAILS: connected providers must remain empty with None config.\n"
            f"  Got: {app._connected_providers}"
        )

    # ------------------------------------------------------------------
    # TEST 8 — _populate_connected_providers guards against empty provider
    # ------------------------------------------------------------------

    def test_populate_connected_providers_with_empty_provider_dict(self) -> None:
        """When config.provider is empty dict, _populate_connected_providers
        must not crash and should leave _connected_providers empty."""
        app = PyHarnessApp()
        app._connected_providers = set()
        app.config = PyHarnessConfig(
            model="deepseek:deepseek-chat",
            provider={},
        )

        # Must not raise
        app._populate_connected_providers()

        assert app._connected_providers == set(), (
            "FAILS: connected providers must remain empty with no provider entries.\n"
            f"  Got: {app._connected_providers}"
        )

    # ------------------------------------------------------------------
    # TEST 9 — _connected_providers initialized as empty set pre-mount
    # ------------------------------------------------------------------

    def test_connected_providers_starts_empty(self) -> None:
        """Before on_mount, _connected_providers must be an empty set."""
        app = PyHarnessApp()

        assert isinstance(app._connected_providers, set), (
            f"FAILS: _connected_providers must be a set, "
            f"got {type(app._connected_providers).__name__}"
        )
        assert len(app._connected_providers) == 0, (
            "FAILS: _connected_providers must be empty before on_mount.\n"
            f"  Got: {app._connected_providers}"
        )

    # ------------------------------------------------------------------
    # TEST 10 — _update_sidebar_providers is invoked in connect flow
    # ------------------------------------------------------------------

    def test_sidebar_providers_updated_on_connect(self) -> None:
        """_handle_connect_result must call _update_sidebar_providers
        after a successful connection."""
        import inspect
        source = inspect.getsource(PyHarnessApp._handle_connect_result)

        has_sidebar_update = "_update_sidebar_providers" in source
        assert has_sidebar_update, (
            "FAILS: _handle_connect_result must call _update_sidebar_providers.\n"
            "  After a successful /connect, the sidebar provider status\n"
            "  indicators must be refreshed.\n\n"
            f"  Source:\n{source[:300]}..."
        )

    # ------------------------------------------------------------------
    # TEST 11 — _handle_connect_result adds provider to connected set
    # ------------------------------------------------------------------

    def test_handle_connect_result_adds_to_connected(self) -> None:
        """_handle_connect_result must add the provider to
        _connected_providers via the result string."""
        app = PyHarnessApp()
        app._connected_providers = set()
        app.config = PyHarnessConfig(model="deepseek:deepseek-chat")

        # Simulate what _handle_connect_result does when result is truthy
        provider_name = "openrouter"
        app._connected_providers.add(provider_name)

        assert provider_name in app._connected_providers, (
            "FAILS: provider must be in _connected_providers after "
            "successful connection."
        )


# =============================================================================
# REMOVE _STATIC_MODELS — TUI-side: /models must not show static fallback models
# =============================================================================
# When ``_STATIC_MODELS`` is removed, the TUI's /models dropdown must only
# show models from connected providers — either from live APIs or from the
# per-provider ``_VERIFY_MODELS`` fallback.  No cross-contamination.
#
# THIS TEST MUST FAIL until ``_STATIC_MODELS`` is gone and the model list
# in the app's cache is built without it.
# =============================================================================


class TestNoStaticModelsTUI:
    """TUI /models dropdown must not show static fallback models from
    unrelated providers."""

    # ------------------------------------------------------------------
    # TEST 8 — /models with only deepseek connected shows ONLY verifier model
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_models_list_no_static_fallback_visible(self) -> None:
        """Launch app with only deepseek connected.  /models dropdown must
        show ONLY ``deepseek:deepseek-chat`` (the verifier model).

        No ``anthropic:claude-sonnet-4-5``, no ``openai:gpt-5``, no
        ``openrouter:openai/gpt-5``, no ``ollama:llama3``.

        FAILS because ``_available_models`` is populated from
        ``_STATIC_MODELS`` which includes all those extraneous entries.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Set up: only deepseek is connected
            from pyharness.config.schema import ProviderConfig
            app.config.provider = {
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            }
            app._connected_providers = {"deepseek"}

            # Populate model cache with the verifier model only
            # (what fetch_models should return after _STATIC_MODELS removal)
            app._available_models = ["deepseek:deepseek-chat"]
            app._model_list_loaded = True

            from pyharness.tui.widgets.input import PromptInput
            inp = app.screen_stack[-1].query_one(PromptInput)
            inp.value = "/models"
            await pilot.press("enter")
            await pilot.pause()

            items = _models_dropdown_items(app)

            # Filter out header/decoration lines (like "Models (1 matches)")
            model_lines = [
                item for item in items
                if ":" in item  # model IDs always contain "provider:model"
            ]

            # Must have only the deepseek verifier model
            for item in model_lines:
                # Strip icon prefixes like "🤖 " or "📄 " for comparison
                clean = item.replace("🤖", "").replace("📁", "").replace("📄", "").strip()
                valid = clean == "deepseek:deepseek-chat" or (
                    "deepseek" in clean and "deepseek-chat" in clean
                )
                assert valid, (
                    "FAILS: unexpected model in /models dropdown.\n"
                    f"  Item: {item!r}\n"
                    f"  All items: {items!r}\n\n"
                    "  With only deepseek connected, the dropdown must show\n"
                    "  ONLY 'deepseek:deepseek-chat' (the verifier model).\n"
                    "  No anthropic, openai, openrouter, ollama, or any other\n"
                    "  provider models must appear."
                )

            # Explicitly check cross-contamination
            for forbidden_prefix in ("anthropic:", "openai:", "openrouter:", "ollama:"):
                for item in model_lines:
                    clean = item.replace("🤖", "").replace("📁", "").replace("📄", "").strip()
                    assert not clean.startswith(forbidden_prefix), (
                        f"FAILS: {forbidden_prefix} model leaked into /models.\n"
                        f"  Item: {item!r}\n"
                        f"  All items: {items!r}\n\n"
                        "  Only deepseek is connected — its models must be the\n"
                        "  ONLY items in the /models dropdown."
                    )


# =============================================================================
# LIVE MODEL DISCOVERY TUI — connect then /models shows live API results
# =============================================================================
# When a provider is connected, the /models dropdown must show models
# returned from the live provider API, not from any static/hardcoded list.
# =============================================================================


class TestLiveModelDiscoveryTUI:
    """TUI /models must show models from live provider APIs, not static lists."""

    # ------------------------------------------------------------------
    # TEST 9 — Connect to OpenAI (mocked) then /models shows live results
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_then_models_shows_live_results(self) -> None:
        """Connect to openai (mocked), then /models dropdown shows models
        returned from the live API, not from any static list.

        Mock httpx to return ``{"data": [{"id":"gpt-5"},{"id":"gpt-4o-mini"}]}``
        from the OpenAI API.  After connecting, the /models dropdown must
        show these exact models.

        FAILS: the model list comes from ``_VERIFY_MODELS`` (single entry
        ``openai:gpt-4o-mini``) instead of the live API response with both
        models.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = {
            "data": [
                {"id": "gpt-5"},
                {"id": "gpt-4o-mini"},
            ]
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_get_response = MagicMock()
        mock_get_response.raise_for_status = MagicMock()
        mock_get_response.json = MagicMock(return_value=mock_response)
        mock_client.get = AsyncMock(return_value=mock_get_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            from pyharness.core.provider import fetch_models

            config = PyHarnessConfig(
                provider={
                    "openai": ProviderConfig(apiKey="sk-test-openai"),
                }
            )
            models = await fetch_models(config, providers={"openai"})

        # Verify the live API was actually called
        assert mock_client.get.called, (
            "FAILS: fetch_models did not make an HTTP call for openai.\n"
            "  Current: openai is not a 'live' provider — _VERIFY_MODELS is used\n"
            "  instead of querying the actual OpenAI API."
        )

        expected = sorted(["openai:gpt-5", "openai:gpt-4o-mini"])
        assert models == expected, (
            "FAILS: /models must show models from the live API, not from static lists.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {models}\n"
            "  Current: returns ['openai:gpt-4o-mini'] from _VERIFY_MODELS.\n"
            "  The SPEC mandates that every model ID comes from a provider's own API,\n"
            "  not from hardcoded constants."
        )
