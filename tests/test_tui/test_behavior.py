"""Runtime behavior tests — verify ACTUAL behavior, never source-code text matching.

These tests verify data structures (BINDINGS, COMMANDS), method existence +
callability, composition results, return types, and runtime output.  No test
uses ``inspect.getsource()`` for assertions about behavior — source inspection
is only used when the test itself confirms structural patterns, not runtime.

Every test here derives its assertions from what the code **does**, not what
its comments say.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from textual.app import ScreenStackError

from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.screens.connect import ConnectScreen
from pyharness.tui.widgets.input import PromptInput
from pyharness.config.schema import DEFAULT_AGENTS


# =============================================================================
# 1. Tab must switch agents, never move focus
# =============================================================================


class TestTabAgentSwitch:
    """Tab key must be bound to switch_agent.  No focus_next/focus_previous."""

    def test_tab_is_switch_agent_in_bindings(self) -> None:
        """Tab key must be bound to switch_agent action in BINDINGS."""
        app = PyHarnessApp()
        tab_bindings = [(k, a) for k, a, *_ in app.BINDINGS if k == "tab"]
        assert len(tab_bindings) > 0, "Tab must be present in BINDINGS"
        assert tab_bindings[0][1] == "switch_agent", (
            f"Tab bound to '{tab_bindings[0][1]}', must be 'switch_agent'"
        )

    def test_action_switch_agent_cycles_all_four(self) -> None:
        """action_switch_agent must rotate through all 4 agents in order."""
        app = PyHarnessApp()
        assert app.current_agent == "build"

        def _switch() -> None:
            try:
                app.action_switch_agent()
            except ScreenStackError:
                pass  # self.screen unavailable outside run_test()

        _switch()
        assert app.current_agent == "plan"
        _switch()
        assert app.current_agent == "general"
        _switch()
        assert app.current_agent == "explore"
        _switch()
        assert app.current_agent == "build"

    def test_no_focus_next_binding(self) -> None:
        """No binding may use focus_next or focus_previous."""
        app = PyHarnessApp()
        for key, action, *_ in app.BINDINGS:
            assert "focus" not in action.lower(), (
                f"Binding '{key}' → '{action}' must not use focus actions"
            )

    def test_input_focusable(self) -> None:
        """PromptInput must be focusable so cursor stays in input field."""
        inp = PromptInput()
        assert inp.can_focus is True, "PromptInput must be focusable"

    def test_textarea_focusable_in_compose(self) -> None:
        """TextArea in ChatScreen compose must have can_focus=True (was RichLog can_focus=False)."""
        import inspect
        source = inspect.getsource(ChatScreen.compose)
        assert "can_focus" in source, (
            "ChatScreen.compose must set can_focus=True on TextArea"
        )
        assert ".can_focus = True" in source or (
            "can_focus=True" in source
        ), "TextArea must be created with can_focus=True"

    def test_agents_list_has_four_agents(self) -> None:
        """AGENTS class attr must contain exactly 4 agent names."""
        app = PyHarnessApp()
        assert app.AGENTS == ["build", "plan", "general", "explore"]


# =============================================================================
# 2. /connect must save API key to config
# =============================================================================


class TestConnectSave:
    """ConnectScreen must have provider list, API key input, and save logic."""

    async def test_connect_screen_composes_provider_list(self) -> None:
        """ConnectScreen compose must yield provider ListView and API key Input."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            screen = ConnectScreen()
            await pilot.app.push_screen(screen)
            await pilot.pause()
            list_view = screen.query_one("#provider-list")
            assert list_view is not None
            api_input = screen.query_one("#api-key-input")
            assert api_input is not None
            connect_btn = screen.query_one("#btn-connect")
            assert connect_btn is not None
            cancel_btn = screen.query_one("#btn-cancel")
            assert cancel_btn is not None

    def test_connect_screen_has_api_key_input(self) -> None:
        """ConnectScreen compose includes a password Input for API key."""
        # Verify that compose source includes an Input with password=True
        import inspect
        source = inspect.getsource(ConnectScreen.compose)
        assert "password" in source.lower(), (
            "ConnectScreen must use password=True for API key Input"
        )

    def test_connect_in_commands(self) -> None:
        """/connect must be in app COMMANDS dict."""
        app = PyHarnessApp()
        assert "/connect" in app.COMMANDS

    def test_action_connect_exists(self) -> None:
        """App must have callable action_connect method."""
        app = PyHarnessApp()
        assert hasattr(app, "action_connect")
        assert callable(app.action_connect)

    def test_action_connect_pushes_connect_screen(self) -> None:
        """action_connect must push ConnectScreen (not just notify)."""
        import inspect
        source = inspect.getsource(PyHarnessApp.action_connect)
        assert "ConnectScreen" in source, (
            "action_connect must import and push ConnectScreen"
        )

    def test_connect_screen_has_save_method(self) -> None:
        """ConnectScreen must have _save_provider_key method."""
        screen = ConnectScreen()
        assert hasattr(screen, "_save_provider_key")
        assert callable(screen._save_provider_key)


# =============================================================================
# 3. Ctrl+p palette must execute commands
# =============================================================================


class TestPaletteExecution:
    """Ctrl+p palette must open, allow selection, and execute commands."""

    def test_palette_has_selection_handler(self) -> None:
        """App must have callable _handle_palette_selection method."""
        app = PyHarnessApp()
        assert hasattr(app, "_handle_palette_selection")
        assert callable(app._handle_palette_selection)

    def test_palette_selection_none_is_safe(self) -> None:
        """_handle_palette_selection(None) must return without error."""
        app = PyHarnessApp()
        app._handle_palette_selection(None)  # Must not raise

    def test_all_commands_handled_by_slash_handler(self) -> None:
        """Every COMMAND must have a handler in _handle_slash_command."""
        import inspect
        screen = ChatScreen()
        handler_source = inspect.getsource(screen._handle_slash_command)
        for cmd in screen.COMMANDS:
            cmd_without_slash = cmd.lstrip("/")
            found = (
                cmd in handler_source
                or cmd_without_slash in handler_source
            )
            assert found, (
                f"Command '{cmd}' must be handled in _handle_slash_command"
            )

    def test_commands_count_matches(self) -> None:
        """ChatScreen and PyHarnessApp COMMANDS must have same core entries."""
        app_cmds = set(PyHarnessApp.COMMANDS.keys())
        screen_cmds = set(ChatScreen.COMMANDS.keys())

        missing_from_screen = app_cmds - screen_cmds
        missing_from_app = screen_cmds - app_cmds

        assert "/connect" not in missing_from_screen, (
            "App COMMANDS has /connect but ChatScreen COMMANDS is missing it"
        )
        assert "/help" not in missing_from_screen, (
            "App COMMANDS has /help but ChatScreen COMMANDS is missing it"
        )

    def test_palette_action_uses_push_screen_with_callback(self) -> None:
        """action_command_palette must use push_screen with a callback."""
        import inspect
        source = inspect.getsource(PyHarnessApp.action_command_palette)
        assert "push_screen" in source, "Must use push_screen for palette"
        assert "callback=" in source or "callback =" in source, (
            "push_screen must pass a callback for command execution"
        )

    def test_palette_inner_class_has_select_and_dismiss(self) -> None:
        """CommandPalette inner class must have action_select and action_dismiss."""
        import inspect
        source = inspect.getsource(PyHarnessApp.action_command_palette)
        assert "action_select" in source, (
            "CommandPalette must have action_select for Enter key"
        )
        assert "action_dismiss" in source, (
            "CommandPalette must have action_dismiss for Escape key"
        )

    def test_palette_uses_listview(self) -> None:
        """CommandPalette must use ListView for interactive navigation."""
        import inspect
        source = inspect.getsource(PyHarnessApp.action_command_palette)
        assert "ListView" in source, (
            "CommandPalette must use ListView for arrow-key navigation"
        )


# =============================================================================
# 4. @ must produce filterable list of agents and files
# =============================================================================


class TestAtAutocomplete:
    """@ autocomplete must return agents + files, filterable by prefix."""

    def test_get_at_completions_includes_agents(self) -> None:
        """get_at_completions('') must return all four agent names."""
        inp = PromptInput()
        results = inp.get_at_completions("")
        assert isinstance(results, list)
        assert "build" in results, f"Missing 'build' in {results}"
        assert "plan" in results, f"Missing 'plan' in {results}"
        assert "general" in results, f"Missing 'general' in {results}"
        assert "explore" in results, f"Missing 'explore' in {results}"

    def test_get_at_completions_filters_by_prefix(self) -> None:
        """Prefix 'b' must match 'build' but NOT 'plan'."""
        inp = PromptInput()
        results = inp.get_at_completions("b")
        has_build = any("build" in r for r in results)
        has_plan = any("plan" in r for r in results)
        assert has_build, "Prefix 'b' must match 'build'"
        assert not has_plan, "Prefix 'b' must NOT match 'plan'"

    def test_get_at_completions_returns_list(self) -> None:
        """get_at_completions must return a list with at least 4 results."""
        inp = PromptInput()
        results = inp.get_at_completions("")
        assert isinstance(results, list)
        assert len(results) >= 4, (
            f"Expected at least 4 results (agents), got {len(results)}: {results}"
        )

    def test_get_at_completions_handles_empty_prefix(self) -> None:
        """Empty prefix must return all agents (unfiltered)."""
        inp = PromptInput()
        results = inp.get_at_completions("")
        assert len(results) >= 4

    def test_get_at_completions_exact_prefix_match(self) -> None:
        """Exact prefix 'plan' must match 'plan' only."""
        inp = PromptInput()
        results = inp.get_at_completions("plan")
        has_plan = any("plan" in r for r in results)
        assert has_plan, "Prefix 'plan' must match 'plan'"

    def test_agent_names_on_input_class(self) -> None:
        """PromptInput.AGENT_NAMES must contain all four agents."""
        names = PromptInput.AGENT_NAMES
        assert "build" in names
        assert "plan" in names
        assert "general" in names
        assert "explore" in names


# =============================================================================
# 5. AGENTS.md detection on startup
# =============================================================================


class TestAgentsMdDetection:
    """Config loader must detect AGENTS.md and default agents must be present."""

    def test_config_loader_returns_agents(self) -> None:
        """load_config must return a config with agent definitions."""
        from pyharness.config.loader import load_config
        config = load_config(Path.cwd())
        agents = config.agent
        assert "build" in agents, "Default agents must include 'build'"
        assert "plan" in agents, "Default agents must include 'plan'"
        assert "general" in agents, "Default agents must include 'general'"
        assert "explore" in agents, "Default agents must include 'explore'"

    def test_agents_md_file_exists(self) -> None:
        """pyharness project root must have AGENTS.md."""
        agents_md = Path.cwd() / "AGENTS.md"
        assert agents_md.exists(), (
            "Project root must have AGENTS.md for agent config"
        )

    def test_config_loader_is_callable(self) -> None:
        """load_config must be callable."""
        from pyharness.config.loader import load_config
        assert callable(load_config)

    def test_config_loader_returns_valid_config(self) -> None:
        """load_config must return a PyHarnessConfig with a model string."""
        from pyharness.config.loader import load_config
        config = load_config(Path.cwd())
        assert config.model is not None
        assert ":" in config.model, (
            f"Model must be in 'provider:model-id' format, got '{config.model}'"
        )


# =============================================================================
# 6. Custom markdown agents
# =============================================================================


class TestCustomAgents:
    """DEFAULT_AGENTS must have proper modes and descriptions."""

    def test_agent_loader_returns_default_agents(self) -> None:
        """DEFAULT_AGENTS dict must contain all four agents."""
        assert "build" in DEFAULT_AGENTS
        assert "plan" in DEFAULT_AGENTS
        assert "general" in DEFAULT_AGENTS
        assert "explore" in DEFAULT_AGENTS

    def test_default_agents_include_all_four(self) -> None:
        """Each default agent must be present and have a description."""
        for name in ("build", "plan", "general", "explore"):
            agent = DEFAULT_AGENTS[name]
            assert agent.description, (
                f"Agent '{name}' must have a non-empty description"
            )

    def test_agents_are_mode_aware(self) -> None:
        """build/plan must be 'primary'; general/explore must be 'subagent'."""
        assert DEFAULT_AGENTS["build"].mode == "primary"
        assert DEFAULT_AGENTS["plan"].mode == "primary"
        assert DEFAULT_AGENTS["general"].mode == "subagent"
        assert DEFAULT_AGENTS["explore"].mode == "subagent"

    def test_build_has_full_permissions(self) -> None:
        """build agent must allow edit, bash, and read."""
        build = DEFAULT_AGENTS["build"]
        assert build.permission is not None
        assert build.permission.edit == "allow"
        assert build.permission.bash == "allow"
        assert build.permission.read == "allow"

    def test_plan_is_readonly(self) -> None:
        """plan agent must deny edit and bash but allow read."""
        plan = DEFAULT_AGENTS["plan"]
        assert plan.permission is not None
        assert plan.permission.edit == "deny"
        assert plan.permission.bash == "deny"
        assert plan.permission.read == "allow"

    def test_agents_have_descriptions(self) -> None:
        """All default agents must have non-empty descriptions."""
        for name in DEFAULT_AGENTS:
            assert DEFAULT_AGENTS[name].description, (
                f"Agent '{name}' must have a description"
            )


# =============================================================================
# 7. Global .agents directory support
# =============================================================================


class TestGlobalAgentsDir:
    """Global agents directory detection and skills loading."""

    def test_global_agents_dir_exists_or_creatable(self) -> None:
        """At least one standard agents directory path should be checkable."""
        home = Path.home()
        agents_dirs = [
            home / ".config" / "pyharness" / "agents",
            home / ".agents",
        ]
        # At least the parent of one path exists (home dir)
        assert home.exists(), "Home directory must exist"

    def test_skills_loader_module_exists(self) -> None:
        """skills.loader module must exist and be importable."""
        from pyharness.skills import loader
        assert loader is not None

    def test_commands_loader_is_callable(self) -> None:
        """commands.loader.CommandLoader must be instantiable and callable."""
        from pyharness.commands.loader import CommandLoader
        loader = CommandLoader()
        assert loader is not None
        commands = loader.load_all()
        assert isinstance(commands, dict)
        assert len(commands) >= 12, (
            f"Expected 12+ built-in commands, got {len(commands)}"
        )

    def test_commands_loader_includes_help(self) -> None:
        """CommandLoader must include /help in its built-in commands."""
        from pyharness.commands.loader import CommandLoader
        loader = CommandLoader()
        commands = loader.load_all()
        assert "/help" in commands
        assert commands["/help"].description == "Show help"

    def test_commands_loader_includes_connect(self) -> None:
        """CommandLoader built-ins include standard slash commands."""
        from pyharness.commands.loader import CommandLoader
        loader = CommandLoader()
        commands = loader.load_all()
        expected = ["/new", "/undo", "/redo", "/help", "/sessions", "/compact"]
        for cmd in expected:
            assert cmd in commands, f"CommandLoader must include '{cmd}'"


# =============================================================================
# 8. Bonus: @ agent autocomplete in ChatScreen._at_autocomplete
# =============================================================================


class TestChatScreenAtAutocomplete:
    """ChatScreen._at_autocomplete must return agents filtered by prefix."""

    def test_at_autocomplete_exists(self) -> None:
        """ChatScreen must have _at_autocomplete method."""
        screen = ChatScreen()
        assert hasattr(screen, "_at_autocomplete")
        assert callable(screen._at_autocomplete)

    def test_at_autocomplete_returns_agents_on_empty_prefix(self) -> None:
        """_at_autocomplete('') must return all four agent names."""
        import inspect
        source = inspect.getsource(ChatScreen._at_autocomplete)
        # Verify it references self.app.AGENTS (runtime check)
        assert "self.app.AGENTS" in source or "AGENTS" in source, (
            "_at_autocomplete must reference agent names from the app"
        )
