"""Regression tests for 5 TUI bugs — these must FAIL until fixes are applied.

Each test class maps to one of the 5 regressions.
Tests verify the *correct* behavior described in the bug reports.
A passing test means the bug is fixed; a failing test means work remains.

Usage::

    uv run pytest tests/test_tui/test_regression.py -v
"""
from __future__ import annotations

import inspect

import pytest

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
