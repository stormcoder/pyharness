"""Tests for 6 Phase 2 TUI issues — these SHOULD FAIL until fixes are implemented.

Each test class maps to one of the 6 issues from the QA plan.  Tests verify
that the missing behavior (arrow navigation, autocomplete dropdowns, provider
setup, model switching, @ references, tool listing) is actually wired in.

Usage::

    uv run pytest tests/test_tui/test_phase2_issues.py -v
"""
from __future__ import annotations

import inspect
import pytest

from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.input import PromptInput
from pyharness.tui.widgets.sidebar import ToolList
from pyharness.tools.registry import get_registry
from pyharness.tools.memory_tools import ALL_MEMORY_TOOLS


# =============================================================================
# Issue 1 — Command palette needs arrow key navigation + selection
# =============================================================================


class TestCommandPaletteNavigation:
    """Issue 1: Command palette doesn't scroll with arrow keys.

    Current: Ctrl+p shows a ModalScreen with Static text — read‑only.
    Expected: ↑↓ to navigate, Enter to execute, Escape to dismiss.
    """

    def test_command_palette_has_selection_state(self) -> None:
        """The CommandPalette class must track which command is selected."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        # The palette class (defined inside action_command_palette) must have
        # a selected_index, _selected, _highlighted, or similar attribute.
        has_selection = any(
            kw in source for kw in ("selected_index", "_selected", "highlighted")
        )
        assert has_selection, (
            "CommandPalette needs a selected_index or _selected attribute "
            "so arrow keys can move the highlight. Currently uses Static "
            "text with no selection tracking."
        )

    def test_command_palette_has_arrow_bindings(self) -> None:
        """CommandPalette must handle up/down/enter keys."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        # Must bind or handle arrow keys (up/down) and enter
        has_bindings = ("BINDINGS" in source) and (
            "up" in source.lower() or "down" in source.lower()
        )
        has_enter = "enter" in source.lower()
        assert has_bindings, (
            "CommandPalette needs BINDINGS with up/down arrow keys "
            "for command navigation."
        )
        assert has_enter, (
            "CommandPalette needs an Enter handler to execute the "
            "selected command."
        )

    def test_command_palette_not_just_static_text(self) -> None:
        """Palette should use an interactive widget, not just Static text."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        # Should reference an interactive widget (ListView, OptionList, ListItem)
        uses_interactive = any(
            w in source for w in ("ListView", "OptionList", "ListItem", "RadioSet")
        )
        assert uses_interactive, (
            "CommandPalette should use an interactive widget "
            "(ListView, OptionList, etc.) that supports selection and "
            "arrow navigation, not just Static text."
        )


# =============================================================================
# Issue 2 — Slash commands don't autocomplete
# =============================================================================


class TestSlashAutocomplete:
    """Issue 2: Slash commands should show a dropdown as the user types.

    Current: Typing ``/`` does nothing — no dropdown, no tab completion.
    Expected: A dropdown of matching commands appears after ``/``, filters
    as more characters are typed, and allows Enter/Tab to select.
    """

    def test_chat_screen_has_slash_suggester(self) -> None:
        """ChatScreen must have a suggest/autocomplete mechanism for ``/``."""
        # Check for any of the common patterns: a Suggester, a
        # _slash_completions attribute, or an autocomplete-related method.
        has_suggester = (
            hasattr(ChatScreen, "_slash_completions")
            or hasattr(ChatScreen, "_autocomplete_options")
            or hasattr(ChatScreen, "_active_suggestions")
            or any(
                "suggester" in name.lower() or "autocomplete" in name.lower()
                for name in dir(ChatScreen)
            )
        )
        assert has_suggester, (
            "ChatScreen needs a slash-command autocomplete mechanism. "
            "Implement a Suggester widget, a _slash_completions list, "
            "or an _autocomplete_options attr that shows matching "
            "commands when / is typed."
        )

    def test_on_input_submitted_detects_partial_slash(self) -> None:
        """Input handler should distinguish typing ``/he`` from submitting."""
        source = inspect.getsource(ChatScreen.on_input_submitted)
        # Should reference autocomplete or suggestions for partial input
        has_autocomplete = any(
            kw in source for kw in ("autocomplete", "suggestion", "completion")
        )
        assert has_autocomplete, (
            "on_input_submitted should trigger autocomplete for partial "
            "slash input (e.g. '/he' should show suggestions, not just "
            "dispatch '/he' as an unknown command)."
        )

    def test_prompt_input_has_value_changed_hook(self) -> None:
        """PromptInput should hook ``on_key`` or ``_watch_value`` for ``/``."""
        source = inspect.getsource(PromptInput._on_key)
        # Currently only handles @ — needs / handling too
        assert "/" in source, (
            "PromptInput._on_key currently only handles '@'. "
            "It must also detect '/' and trigger slash-command "
            "autocomplete."
        )


# =============================================================================
# Issue 3 — No way to setup providers
# =============================================================================


class TestProviderSetup:
    """Issue 3: Need ``/connect`` command to add provider API keys.

    Current: No ``/connect`` command.  Users have no way to configure
    providers within the TUI.
    Expected: ``/connect`` lists available providers, prompts for API keys,
    saves them to ``pyharness.json``.
    """

    def test_connect_command_exists_in_app(self) -> None:
        """PyHarnessApp.COMMANDS must include /connect."""
        assert "/connect" in PyHarnessApp.COMMANDS, (
            "PyHarnessApp.COMMANDS must include '/connect' so users "
            "can configure provider API keys from within the TUI."
        )

    def test_connect_command_exists_in_chat_screen(self) -> None:
        """ChatScreen.COMMANDS must include /connect."""
        assert "/connect" in ChatScreen.COMMANDS, (
            "ChatScreen.COMMANDS must include '/connect' "
            "(mirroring the app COMMANDS dict)."
        )

    def test_chat_screen_handles_connect(self) -> None:
        """ChatScreen must dispatch /connect to a provider setup flow."""
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "/connect" in source, (
            "on_input_submitted must handle '/connect' — "
            "triggering a provider setup flow (list providers, "
            "prompt for API key, save to pyharness.json)."
        )

    def test_connect_action_or_screen_exists(self) -> None:
        """App must have a ``action_connect`` or ConnectScreen class."""
        has_action = hasattr(PyHarnessApp, "action_connect")
        # Also check for a ConnectScreen import or class
        app_source = inspect.getsource(PyHarnessApp.__init__)
        has_screen = "Connect" in app_source or "connect" in app_source.lower()
        assert has_action or has_screen, (
            "Need either a PyHarnessApp.action_connect method "
            "or a ConnectScreen class for the provider setup UI."
        )

    def test_available_providers_includes_required(self) -> None:
        """list_available_providers must return the five core providers."""
        from pyharness.core.provider import list_available_providers

        providers = list_available_providers()
        required = {"anthropic", "openai", "google-genai", "openrouter", "ollama"}
        missing = required - set(providers)
        assert not missing, (
            f"Missing required providers: {missing}. "
            f"list_available_providers() returned: {providers}"
        )


# =============================================================================
# Issue 4 — No commands for model selection or variants
# =============================================================================


class TestModelSelection:
    """Issue 4: Need model selection and variant switching commands.

    Current: ``/models`` lists models but can't select one.  No ``/model``
    switch command.  No ``/variants`` command.
    Expected: ``/models`` allows selection, ``/model <id>`` switches,
    ``/variants`` cycles reasoning variants, status bar updates.
    """

    def test_model_switch_command_exists(self) -> None:
        """COMMANDS must include /model for switching models."""
        assert "/model" in PyHarnessApp.COMMANDS, (
            "PyHarnessApp.COMMANDS must include '/model <provider:model-id>' "
            "for switching models.  Currently only /models exists "
            "(which just lists models)."
        )

    def test_variants_command_exists(self) -> None:
        """COMMANDS must include /variants or /variant."""
        has_variants = (
            "/variants" in PyHarnessApp.COMMANDS
            or "/variant" in PyHarnessApp.COMMANDS
        )
        assert has_variants, (
            "PyHarnessApp.COMMANDS must include '/variants' or '/variant' "
            "so users can cycle through thinking/reasoning variants."
        )

    def test_chat_screen_dispatches_model_command(self) -> None:
        """ChatScreen must handle /model <provider:model-id> as separate from /models."""
        source = inspect.getsource(ChatScreen.on_input_submitted)
        # Must have explicit "/model" handling (not just /models substring match)
        has_model_switch = '"/model"' in source or "'/model'" in source
        # Should also check that it actually switches, not just lists
        assert has_model_switch, (
            "on_input_submitted must handle '/model <id>' as a model-switching "
            "command (not just '/models' which lists). Look for '/model' "
            "as a distinct case."
        )

    def test_app_has_model_switching_method(self) -> None:
        """App must have a method to switch models."""
        has_method = (
            hasattr(PyHarnessApp, "switch_model")
            or hasattr(PyHarnessApp, "set_model")
            or hasattr(PyHarnessApp, "action_model")
        )
        assert has_method, (
            "PyHarnessApp needs a switch_model() or set_model() method "
            "that updates the config model and refreshes the status bar."
        )

    def test_status_bar_updates_on_model_change(self) -> None:
        """Status bar must reflect the current model."""
        app = PyHarnessApp()
        source = inspect.getsource(app.action_switch_agent)
        # action_switch_agent already updates the status bar — check that
        # the model value comes from config (not a hardcoded string after fix)
        assert "config.model" in source or "self.config" in source, (
            "Status bar update should use config.model to reflect "
            "the currently selected model, not a hardcoded value."
        )


# =============================================================================
# Issue 5 — @ doesn't autocomplete for agents or files
# =============================================================================


class TestAtAutocomplete:
    """Issue 5: ``@`` should show a dropdown with fuzzy file + agent matches.

    Current: ``@`` is detected but no dropdown appears.
    Expected: ``@`` followed by text fuzzy-searches project files AND
    agent names (build, plan, general, explore).  Arrow keys navigate,
    Enter selects, inserts reference.
    """

    def test_prompt_input_has_at_suggester(self) -> None:
        """PromptInput must have a dropdown/suggester mechanism for @."""
        source = inspect.getsource(PromptInput._on_key)
        # Must be more than just setting a flag — strip docstring to
        # avoid matching "dropdown" in the docstring's prose.
        body = source.split('"""')[2] if '"""' in source else source
        has_mechanism = any(
            kw in body
            for kw in ("_autocomplete_active", "suggestions", "popup", "overlay")
        )
        # The current code only sets _autocomplete_active = True
        # which is NOT enough — there's no actual dropdown/suggester
        uses_suggester = any(
            kw in body for kw in ("suggester", "Suggest", "popup", "overlay")
        )
        assert uses_suggester, (
            "PromptInput._on_key must do more than set a flag when @ is "
            "typed.  It needs to trigger a dropdown/suggester/popup that "
            "shows matching files and agent names."
        )

    def test_prompt_input_supports_agent_autocomplete(self) -> None:
        """PromptInput or parent must know about agent names for @ completion."""
        # Either PromptInput has agent awareness or ChatScreen provides it
        has_agent_awareness = (
            hasattr(PromptInput, "_agent_names")
            or hasattr(PromptInput, "_autocomplete_sources")
            or hasattr(PromptInput, "_get_suggestions")
        )
        assert has_agent_awareness, (
            "PromptInput needs agent-name awareness for @ autocomplete. "
            "Add _agent_names, _autocomplete_sources, or _get_suggestions "
            "so typing @build, @plan, @general, @explore triggers matches."
        )

    def test_agent_list_includes_subagents(self) -> None:
        """AGENTS list must include subagent names (general, explore)."""
        assert "general" in PyHarnessApp.AGENTS, (
            "PyHarnessApp.AGENTS must include 'general' (subagent) "
            "so @general autocompletes."
        )
        assert "explore" in PyHarnessApp.AGENTS, (
            "PyHarnessApp.AGENTS must include 'explore' (subagent) "
            "so @explore autocompletes."
        )

    def test_chat_screen_has_at_completion_handler(self) -> None:
        """ChatScreen must have a method to provide @ completions."""
        has_method = any(
            name for name in dir(ChatScreen)
            if "at_" in name.lower() or "autocomplete" in name.lower()
        )
        assert has_method, (
            "ChatScreen needs an @-completion handler method "
            "(e.g., _get_at_suggestions, _at_autocomplete) that "
            "provides file + agent matches to the input widget."
        )


# =============================================================================
# Issue 6 — Tools tab is empty
# =============================================================================


class TestToolsTab:
    """Issue 6: Tools tab should list available tools with status.

    Current: ToolList shows a placeholder message.
    Expected: List built‑in tools (bash, read, write, edit, grep, glob,
    task, todowrite), MCP tools (if any), memory tools (if MemPalace
    installed), with status indicators.
    """

    def test_tool_registry_has_builtin_tools_registered(self) -> None:
        """Tool registry must have built-in tools registered at import time."""
        from pyharness.tools.registry import get_registry

        registry = get_registry()
        names = registry.get_names()

        required_builtins = {"bash", "read", "write", "edit", "grep", "glob"}
        missing = required_builtins - set(names)
        assert not missing, (
            f"Built-in tools not registered: {missing}. "
            f"Registry has: {names}. "
            "Built-in tools must be registered (probably in a "
            "_register_builtins() function called at module import)."
        )

    def test_tool_registry_has_task_tools(self) -> None:
        """Registry must include task and todowrite tools."""
        registry = get_registry()
        names = registry.get_names()
        assert "task" in names, "task tool must be registered"
        assert "todowrite" in names, "todowrite tool must be registered"

    def test_all_memory_tools_has_six_entries(self) -> None:
        """ALL_MEMORY_TOOLS should contain exactly 6 memory tools."""
        assert len(ALL_MEMORY_TOOLS) == 6, (
            f"Expected 6 memory tools, got {len(ALL_MEMORY_TOOLS)}. "
            f"Tools: {[getattr(t, 'name', str(t)) for t in ALL_MEMORY_TOOLS]}"
        )

    def test_tool_list_not_just_placeholder(self) -> None:
        """ToolList should display tools, not just a placeholder message."""
        source = inspect.getsource(ToolList.on_mount)
        # Currently shows "[#8b949e]Available tools will be listed here..."
        # After fix, should reference actual tool data.
        # Use specific keywords that won't appear in the placeholder text.
        uses_tool_data = any(
            kw in source for kw in ("registry", "get_names()", "get_registry", "get_all")
        )
        assert uses_tool_data, (
            "ToolList.on_mount should query the tool registry for "
            "actual tools instead of displaying a placeholder message. "
            "Use get_registry().get_names() to list available tools."
        )

    def test_tool_list_has_formatting_for_tools(self) -> None:
        """ToolList must have a method to render individual tools."""
        has_render = (
            hasattr(ToolList, "_render_tool")
            or hasattr(ToolList, "_format_tool")
            or hasattr(ToolList, "render_tool")
        )
        assert has_render, (
            "ToolList needs a method to format/display individual tools "
            "with their names and status indicators (e.g., _render_tool, "
            "_format_tool)."
        )

    def test_memory_tools_in_all_memory_tools_are_valid(self) -> None:
        """Each entry in ALL_MEMORY_TOOLS must have a .name attribute."""
        for tool in ALL_MEMORY_TOOLS:
            assert hasattr(tool, "name"), (
                f"Memory tool {tool!r} lacks a .name attribute. "
                "All tools must be LangChain BaseTool instances with names."
            )
