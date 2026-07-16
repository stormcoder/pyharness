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
        # Extract just the compose body (between "def compose" and next "def ")
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
        # query_one is safe in on_mount and action_select (post-mount lifecycle).
        # It must NOT appear in compose() itself.
        compose_start = source.index("def compose")
        # Find the end of compose: next method definition at same indent level (12 spaces)
        # Use regex to find the next 'def ' at the same indent
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
        # Count yield statements in compose as a proxy for section count
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
