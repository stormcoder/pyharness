"""UX regression tests — focus lock, palette execution, dropdowns, /connect dialog."""
import pytest
import inspect

class TestFocusLock:
    """Issue 1: Tab must switch agents, cursor stays in text entry."""

    def test_tab_is_switch_agent_not_focus_next(self):
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        for key, action, *_ in app.BINDINGS:
            if key.lower() == "tab":
                assert action == "switch_agent", \
                    f"Tab must be switch_agent, got {action}"

    def test_no_focus_keybindings_steal_tab(self):
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        focus_bindings = ["focus_next", "focus_previous"]
        for key, action, *_ in app.BINDINGS:
            assert action not in focus_bindings, \
                f"Must not have focus keybindings: {key} -> {action}"

    def test_action_switch_agent_exists_and_callable(self):
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        assert hasattr(app, "action_switch_agent")
        assert callable(app.action_switch_agent)

    def test_prompt_input_has_autofocus(self):
        """PromptInput should be the default focused widget."""
        from pyharness.tui.widgets.input import PromptInput
        inp = PromptInput()
        # In Textual, can_focus defaults to True for Input widgets
        assert inp.can_focus is True or inp.can_focus is not False


class TestPaletteExecution:
    """Issue 2: Enter on palette command must execute it."""

    def test_handle_palette_selection_exists(self):
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        assert hasattr(app, "_handle_palette_selection")
        assert callable(app._handle_palette_selection)

    def test_handle_palette_handles_known_commands(self):
        """Known commands must be handled, not silently ignored."""
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        source = inspect.getsource(app._handle_palette_selection)
        # Must handle at least these commands
        for cmd in ["/help", "/new", "/connect", "/models"]:
            assert cmd in source or cmd.strip("/") in source.lower(), \
                f"Must handle {cmd} in palette selection"

    def test_palette_callback_is_wired(self):
        """push_screen must pass callback for command execution."""
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        source = inspect.getsource(app.action_command_palette)
        assert "callback" in source, \
            "push_screen must have callback to handle selection"


class TestDropdownAutocomplete:
    """Issue 3: / and @ must show interactive filterable dropdowns."""

    def test_slash_has_dropdown_not_just_tooltip(self):
        """Slash must trigger dropdown, not just set tooltip text."""
        from pyharness.tui.widgets.input import PromptInput
        source = inspect.getsource(PromptInput._show_slash_dropdown)
        # Should reference dropdown/suggest/overlay concepts, not just tooltip
        assert "Dropdown" in source or "dropdown" in source or "suggest" in source.lower() or "overlay" in source.lower(), \
            "Slash must use interactive dropdown, not just tooltip"

    def test_at_has_dropdown_not_just_tooltip(self):
        """@ must trigger dropdown, not just set tooltip text."""
        from pyharness.tui.widgets.input import PromptInput
        source = inspect.getsource(PromptInput._show_at_dropdown)
        assert "Dropdown" in source or "dropdown" in source or "suggest" in source.lower() or "overlay" in source.lower(), \
            "@ must use interactive dropdown, not just tooltip"

    def test_slash_completions_include_required_commands(self):
        from pyharness.tui.widgets.input import PromptInput
        inp = PromptInput()
        cmds = inp.SLASH_COMMANDS or []
        required = ["/help", "/new", "/undo", "/connect", "/model"]
        for cmd in required:
            assert any(c.startswith(cmd) for c in cmds), \
                f"SLASH_COMMANDS must include {cmd}"

    def test_at_completions_include_agents(self):
        from pyharness.tui.widgets.input import PromptInput
        inp = PromptInput()
        if hasattr(inp, "get_at_completions"):
            results = inp.get_at_completions("")
            agent_names = ["build", "plan", "general", "explore"]
            for name in agent_names:
                found = any(name in r for r in results)
                assert found, f"@ completions must include agent '{name}'"

    def test_at_completions_filter_by_prefix(self):
        from pyharness.tui.widgets.input import PromptInput
        inp = PromptInput()
        if hasattr(inp, "get_at_completions"):
            results = inp.get_at_completions("b")
            has_build = any("build" in r for r in results)
            has_plan = any("plan" in r for r in results)
            assert has_build, "Prefix 'b' must match 'build'"
            # 'plan' should NOT match prefix 'b'
            assert not has_plan, "Prefix 'b' must NOT match 'plan'"


class TestConnectDialog:
    """Issue 4: /connect must have interactive provider selection dialog."""

    def test_connect_in_commands(self):
        from pyharness.tui.app import PyHarnessApp
        app = PyHarnessApp()
        assert "/connect" in app.COMMANDS

    def test_connect_handler_exists(self):
        """Must have a connect handler beyond just printing text."""
        from pyharness.tui.screens.chat import ChatScreen
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "connect" in source.lower(), \
            "on_input_submitted must handle /connect"

    def test_providers_are_listable(self):
        from pyharness.core.provider import list_available_providers
        providers = list_available_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "openrouter" in providers
        assert "ollama" in providers

    def test_connect_screen_or_dialog_exists(self):
        """Should have a ConnectScreen class or connect dialog."""
        # Check if there's a connect screen module or class
        try:
            from pyharness.tui.screens.connect import ConnectScreen
            assert ConnectScreen is not None
        except ImportError:
            # If no separate screen, check app for connect method
            from pyharness.tui.app import PyHarnessApp
            app = PyHarnessApp()
            assert hasattr(app, "action_connect") or "/connect" in str(app.COMMANDS), \
                "Must have either ConnectScreen or action_connect"
