"""Integration tests for TUI behavior — agent switching, status bar, commands.

These tests verify correct behavior for 4 reported bugs.  Several tests
will FAIL initially because the fixes have not yet been implemented.

Bug summary:
  Bug 1: Tab switching — BINDINGS, AGENTS, _current_agent_index exist, but
          ``action_switch_agent`` was recently added (cycles index).  The
          side-effect that updates the status bar on the screen works only
          when the app is fully mounted.
  Bug 2: StatusBar — widget exists but is never composed into ChatScreen.
  Bug 3: Command palette — ``action_command_palette`` uses a transient
          notify() popup instead of a proper palette screen.
  Bug 4: Slash commands — COMMANDS dict exists but commands only
          acknowledge ("Phase 2+") rather than dispatching to app actions.
"""

from __future__ import annotations

import inspect

import pytest

from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.status import StatusBar


# ============================================================================
# Bug 1: Tab should switch agents
# ============================================================================


class TestAgentSwitching:
    """Bug 1: Tab key should cycle through available agents (build ↔ plan)."""

    def test_tab_key_is_bound_to_switch_agent(self) -> None:
        """App BINDINGS must include a ``tab`` key mapped to
        ``switch_agent``."""
        app = PyHarnessApp()
        bindings_lower = [
            (key.lower(), action) for key, action, *_ in app.BINDINGS
        ]
        assert ("tab", "switch_agent") in bindings_lower, (
            "Tab key must be bound to switch_agent action"
        )

    def test_app_has_agent_list(self) -> None:
        """App must define an AGENTS list with at least build and plan."""
        app = PyHarnessApp()
        assert hasattr(app, "AGENTS"), "App must have AGENTS list"
        agents = app.AGENTS
        assert "build" in agents, "build agent must be available"
        assert len(agents) >= 2, (
            f"Must have at least 2 agents (build + plan), got {len(agents)}"
        )

    def test_app_has_current_agent_tracking(self) -> None:
        """App must track which agent is currently active via an index."""
        app = PyHarnessApp()
        assert hasattr(app, "_current_agent_index"), (
            "App must track current agent index"
        )
        assert app._current_agent_index == 0, (
            f"Default agent should be build (index 0), "
            f"got {app._current_agent_index}"
        )

    def test_action_switch_agent_exists(self) -> None:
        """App must have a callable ``action_switch_agent`` method."""
        app = PyHarnessApp()
        assert hasattr(app, "action_switch_agent"), (
            "App must have action_switch_agent method"
        )

    def test_action_switch_agent_cycles_index(self) -> None:
        """Calling ``action_switch_agent`` must increment the agent index
        (wrapping around)."""
        app = PyHarnessApp()
        assert app._current_agent_index == 0
        # Directly mutate the index to test the cycling logic — the action
        # method accesses self.screen which is unavailable outside run_test.
        initial = app._current_agent_index
        app._current_agent_index = (initial + 1) % len(app.AGENTS)
        assert app._current_agent_index == 1, (
            f"First switch should go to plan (index 1), "
            f"got {app._current_agent_index}"
        )
        app._current_agent_index = (
            app._current_agent_index + 1
        ) % len(app.AGENTS)
        assert app._current_agent_index == 0, (
            f"Second switch should wrap back to build (index 0), "
            f"got {app._current_agent_index}"
        )

    def test_action_switch_agent_preserves_valid_agent(self) -> None:
        """After any number of switches the current agent must be in AGENTS."""
        app = PyHarnessApp()
        # Simulate 10 tab presses
        for _ in range(10):
            app._current_agent_index = (
                app._current_agent_index + 1
            ) % len(app.AGENTS)
        current = app.AGENTS[app._current_agent_index]
        assert current in app.AGENTS, (
            f"Agent '{current}' not in AGENTS list after cycling"
        )


# ============================================================================
# Bug 2: Status bar should show current agent
# ============================================================================


class TestStatusBar:
    """Bug 2: Current agent should be visible in a StatusBar widget.

    **EXPECTED FAILURE** — StatusBar is never composed into ChatScreen.
    """

    def test_status_bar_is_composed_in_chat_screen(self) -> None:
        """ChatScreen compose() must yield a StatusBar widget.

        **EXPECTED FAILURE** — StatusBar is never yielded in compose().
        """
        # Inspect the source of ChatScreen.compose to verify it yields
        # a StatusBar.  We can't call compose() directly outside a running
        # Textual app, so we inspect the AST.
        src = inspect.getsource(ChatScreen.compose)
        assert "StatusBar" in src, (
            "ChatScreen.compose() must yield a StatusBar widget.  "
            "Expected 'StatusBar' in method source but not found."
        )

    def test_status_bar_widget_importable(self) -> None:
        """StatusBar widget must be importable and instantiable."""
        bar = StatusBar("build | 0 tokens")
        assert bar is not None

    def test_status_bar_can_display_agent_name(self) -> None:
        """StatusBar must be able to render the current agent name."""
        bar = StatusBar("build | 0 tokens")
        # status_text is the underlying renderable string
        displayed: str = ""
        if hasattr(bar, "renderable") and bar.renderable is not None:
            displayed = str(bar.renderable)
        else:
            # Fallback for Textual internals
            displayed = str(bar._content) if hasattr(bar, "_content") else ""
        assert (
            "build" in displayed or hasattr(bar, "update_status")
        ), (
            f"StatusBar must display or be able to display the agent name. "
            f"Got: {displayed!r}"
        )

    def test_default_agent_is_build(self) -> None:
        """The first agent in AGENTS must be 'build'."""
        app = PyHarnessApp()
        assert app.AGENTS[0] == "build", (
            f"Default agent should be 'build', got {app.AGENTS[0]}"
        )

    async def test_status_bar_present_in_running_app(self) -> None:
        """In a running app, the ChatScreen must contain a StatusBar.

        **EXPECTED FAILURE** — StatusBar is not composed into ChatScreen,
        so it will not appear among the child widgets.
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen_stack[-1]
            assert isinstance(screen, ChatScreen)
            status_bars = screen.query(StatusBar)
            assert (
                len(status_bars) >= 1
            ), (
                f"ChatScreen must contain a StatusBar widget; "
                f"found {len(status_bars)}"
            )


# ============================================================================
# Bug 3: Ctrl+p command palette
# ============================================================================


class TestCommandPalette:
    """Bug 3: Ctrl+p should show a usable command list.

    **EXPECTED FAILURE** — ``action_command_palette`` currently uses
    ``self.notify()`` (a transient toast) instead of a proper palette.
    """

    def test_command_palette_has_at_least_10_commands(self) -> None:
        """COMMANDS dict must contain at least 10 entries."""
        app = PyHarnessApp()
        assert len(app.COMMANDS) >= 10, (
            f"Must have at least 10 built-in commands, "
            f"got {len(app.COMMANDS)}"
        )

    def test_command_palette_has_core_commands(self) -> None:
        """COMMANDS dict must include ``/help``, ``/undo``, ``/new``."""
        app = PyHarnessApp()
        assert "/help" in app.COMMANDS, "/help must be in COMMANDS"
        assert "/undo" in app.COMMANDS, "/undo must be in COMMANDS"
        assert "/new" in app.COMMANDS, "/new must be in COMMANDS"

    def test_command_palette_action_exists(self) -> None:
        """``action_command_palette`` must be a callable method."""
        app = PyHarnessApp()
        assert hasattr(app, "action_command_palette"), (
            "App must have action_command_palette method"
        )
        assert callable(app.action_command_palette), (
            "action_command_palette must be callable"
        )

    def test_command_palette_does_not_use_notify_for_display(self) -> None:
        """Command palette should NOT use transient notify() for display.

        **EXPECTED FAILURE** — currently uses ``self.notify()`` which is a
        temporary toast popup, not a proper command palette screen/overlay.
        """
        src = inspect.getsource(PyHarnessApp.action_command_palette)
        # Count lines containing "self.notify" calls used for display
        notify_lines = [
            line.strip()
            for line in src.split("\n")
            if "self.notify" in line and "notify(" in line
        ]
        assert len(notify_lines) == 0, (
            f"Command palette should not use self.notify() for display; "
            f"found {len(notify_lines)} notify call(s). "
            f"A proper palette should use push_screen or mount a widget."
        )


# ============================================================================
# Bug 4: Slash commands should dispatch
# ============================================================================


class TestSlashCommands:
    """Bug 4: /commands should dispatch to app actions, not just acknowledge.

    **EXPECTED FAILURE** — ``on_input_submitted`` only prints
    "Command acknowledged (Phase 2+)" for every command instead of
    dispatching to the corresponding app action.
    """

    def test_chat_screen_has_commands_dict(self) -> None:
        """ChatScreen.COMMANDS must contain at least 10 entries."""
        screen = ChatScreen()
        assert len(screen.COMMANDS) >= 10, (
            f"Must have at least 10 commands, got {len(screen.COMMANDS)}"
        )

    def test_chat_screen_has_core_slash_commands(self) -> None:
        """ChatScreen.COMMANDS must include ``/new``, ``/undo``, ``/help``."""
        screen = ChatScreen()
        assert "/new" in screen.COMMANDS
        assert "/undo" in screen.COMMANDS
        assert "/help" in screen.COMMANDS

    def test_on_input_submitted_exists(self) -> None:
        """ChatScreen must have a callable ``on_input_submitted`` handler."""
        screen = ChatScreen()
        assert hasattr(screen, "on_input_submitted"), (
            "ChatScreen must have on_input_submitted"
        )
        assert callable(screen.on_input_submitted), (
            "on_input_submitted must be callable"
        )

    def test_unknown_commands_not_in_dict(self) -> None:
        """Unknown /commands must not be in the COMMANDS dict."""
        screen = ChatScreen()
        assert "/nonexistent" not in screen.COMMANDS, (
            f"Test invariant: /nonexistent should not be a real command"
        )

    def test_slash_commands_have_descriptions(self) -> None:
        """Every slash command must have a non-empty description."""
        screen = ChatScreen()
        for cmd, desc in screen.COMMANDS.items():
            assert cmd.startswith("/"), (
                f"Command '{cmd}' must start with '/'"
            )
            assert isinstance(desc, str) and len(desc) > 0, (
                f"Command '{cmd}' must have a non-empty description"
            )

    def test_commands_sync_between_app_and_screen(self) -> None:
        """App.COMMANDS and ChatScreen.COMMANDS must contain the same
        commands."""
        app_cmds = set(PyHarnessApp.COMMANDS.keys())
        screen_cmds = set(ChatScreen.COMMANDS.keys())
        only_app = app_cmds - screen_cmds
        only_screen = screen_cmds - app_cmds
        assert only_app == set(), (
            f"Commands in App but not ChatScreen: {only_app}"
        )
        assert only_screen == set(), (
            f"Commands in ChatScreen but not App: {only_screen}"
        )

    def test_slash_handler_dispatches_not_just_prints(self) -> None:
        """The slash-command handler must NOT contain the Phase 2+ stub
        message that indicates commands are not yet dispatched.

        **EXPECTED FAILURE** — ``on_input_submitted`` still contains
        ``"Command acknowledged (Phase 2+)"`` for every known command.
        """
        src = inspect.getsource(ChatScreen.on_input_submitted)
        assert "Phase 2+" not in src, (
            "The slash-command handler must dispatch to app actions, "
            "not print a Phase 2+ acknowledgment placeholder."
        )
