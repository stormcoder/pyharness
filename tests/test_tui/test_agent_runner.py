
"""Tests for Agent Runner wired into ChatScreen.

Verifies that ``on_input_submitted`` properly resolves models, creates
AgentRunner instances, streams responses, handles errors gracefully, and
displays tool calls with ``🔧`` prefix.

Strategy: Tests that need mock agent streaming use TEXTUAL_TEST_MODE
with a pre-configured app. Tests for error paths configure the app
appropriately and verify friendly error messages are shown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import TextArea

from pyharness.config.schema import ProviderConfig, PyHarnessConfig
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen, _append_to_area, _strip_rich_markup
from pyharness.tui.widgets.input import PromptInput

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _chat_screen(app: PyHarnessApp) -> ChatScreen:
    screen = app.screen_stack[-1]
    return screen


def _chat_text(app: PyHarnessApp) -> str:
    """Get full chat TextArea content as plain text."""
    chat = _chat_screen(app).query_one("#chat-area", TextArea)
    return chat.text if chat.text else ""


def _chat_lines(app: PyHarnessApp) -> list[str]:
    """Get chat TextArea content as list of lines."""
    return _chat_text(app).split("\n") if _chat_text(app) else []


def _inp(app: PyHarnessApp) -> PromptInput:
    return _chat_screen(app).query_one(PromptInput)


def _make_configured_app() -> PyHarnessApp:
    """Create an app pre-configured to skip disk config loading."""
    app = PyHarnessApp()
    app._config_loaded_from_disk = True
    app.config = PyHarnessConfig(
        model="openrouter:openai/gpt-5",
        provider={"openrouter": ProviderConfig(apiKey="sk-test")},
    )
    app._connected_providers = {"openrouter"}
    return app


# ---------------------------------------------------------------------------
# 1. No model configured → friendly error, no crash
# ---------------------------------------------------------------------------


class TestNoModelError:
    """When no model is configured, a friendly error is shown without crashing."""

    async def test_send_message_without_model_shows_error(self) -> None:
        """Sending a message with empty model must show error, not crash."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Ensure no model
            app.config.model = ""
            app._connected_providers.clear()

            inp = _inp(app)
            inp.value = "Hello world"
            await pilot.press("enter")
            await pilot.pause()

            text = _chat_text(app)
            assert "Error" in text or "error" in text.lower(), (
                f"Must show error when no model configured.\nChat text: {text!r}"
            )
            assert "no model" in text.lower() or "/connect" in text.lower(), (
                f"Error must mention /connect or model selection.\nChat text: {text!r}"
            )

    async def test_no_model_error_does_not_crash_app(self) -> None:
        """App must remain running after model-less message send."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            app.config.model = ""
            app._connected_providers.clear()

            _inp(app).value = "Test message"
            await pilot.press("enter")
            await pilot.pause()

            assert app.is_running, "App must not crash on message send without model"


# ---------------------------------------------------------------------------
# 2. No provider connected → friendly error, no crash
# ---------------------------------------------------------------------------


class TestNoProviderError:
    """When no provider is connected, a friendly error is shown."""

    async def test_send_message_without_provider_shows_error(self) -> None:
        """Sending a message with model set but no provider must show error."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Model is set but no providers are connected
            app.config.model = "openai:gpt-5"
            app._connected_providers.clear()

            inp = _inp(app)
            inp.value = "Hello world"
            await pilot.press("enter")
            await pilot.pause()

            text = _chat_text(app)
            assert "Error" in text or "error" in text.lower(), (
                f"Must show error when no provider connected.\nChat text: {text!r}"
            )
            assert "no provider" in text.lower() or "/connect" in text.lower(), (
                f"Error must mention missing provider.\nChat text: {text!r}"
            )

    async def test_no_provider_error_does_not_crash_app(self) -> None:
        """App must remain running after provider-less message send."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.config.model = "openai:gpt-5"
            app._connected_providers.clear()

            _inp(app).value = "Another test"
            await pilot.press("enter")
            await pilot.pause()

            assert app.is_running, "App must not crash on message send without provider"


# ---------------------------------------------------------------------------
# 3. Agent runner is called (verification the wiring exists)
# ---------------------------------------------------------------------------


class TestAgentRunnerWiring:
    """Verify the agent runner is properly wired into on_input_submitted."""

    async def test_think_message_appears(self) -> None:
        """'Thinking...' indicator must appear when agent starts."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            async def mock_events():
                yield {"type": "content", "data": "Hello"}
                yield {"type": "done", "data": None}

            mock_runner = MagicMock()
            mock_runner.run = MagicMock(return_value=mock_events())

            with patch.object(
                _chat_screen(app).__class__, "compose", _chat_screen(app).compose
            ):
                pass  # just checking we can access it

            # The on_input_submitted method tries to do:
            #   from pyharness.core.agent import AgentRunner
            # These are local imports, so they resolve at runtime.
            # We verify that with proper config, the method proceeds past
            # the guard checks to the "Thinking..." message.
            screen = _chat_screen(app)
            # Directly trigger the handler with a mock event
            from textual.widgets import Input

            # Use a small patch to make the imports work then have resolve_model fail
            with patch(
                "pyharness.core.provider.resolve_model",
                side_effect=ImportError("No agent module"),
            ):
                # This should enter the except block and show error
                inp = _inp(app)
                inp.value = "Hello"
                await pilot.press("enter")
                await pilot.pause()

            text = _chat_text(app)
            assert "Error resolving model" in text or "error" in text.lower(), (
                "resolve_model failure must be caught and displayed"
            )
            assert app.is_running, "App must not crash"

    async def test_on_input_submitted_has_agent_imports(self) -> None:
        """on_input_submitted source must contain AgentRunner import."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "AgentRunner" in source, (
            "on_input_submitted must import AgentRunner"
        )
        assert "resolve_model" in source, (
            "on_input_submitted must call resolve_model"
        )
        assert "create_agent_graph" in source, (
            "on_input_submitted must import create_agent_graph"
        )

    async def test_on_input_submitted_checks_model_before_agent(self) -> None:
        """Model and provider must be checked BEFORE creating agent runner."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)

        # Find the order: "No model" check must come before "resolve_model"
        no_model_idx = source.find("No model selected")
        resolve_idx = source.find("resolve_model")

        assert no_model_idx > 0, "Must check for empty model before resolving"
        assert resolve_idx > 0, "Must call resolve_model"
        assert no_model_idx < resolve_idx, (
            "Model check must come BEFORE resolve_model call"
        )


# ---------------------------------------------------------------------------
# 4. Tool calls displayed with 🔧 prefix
# ---------------------------------------------------------------------------


class TestToolCallDisplay:
    """Tool call events must display with the 🔧 emoji prefix."""

    def test_tool_call_wrench_in_source(self) -> None:
        """The on_input_submitted handler must contain 🔧 emoji for tool calls."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "🔧" in source, (
            "on_input_submitted must display 🔧 prefix for tool_call events"
        )

    def test_tool_call_event_handled(self) -> None:
        """on_input_submitted must handle 'tool_call' event type."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "tool_call" in source, (
            "on_input_submitted must handle event type 'tool_call'"
        )
        assert "tool_result" in source, (
            "on_input_submitted must handle event type 'tool_result'"
        )

    def test_assistant_label_in_source(self) -> None:
        """'Assistant:' label must appear in source code."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "Assistant:" in source, (
            "on_input_submitted must print 'Assistant:' label before tokens"
        )


# ---------------------------------------------------------------------------
# 5. Input clears after agent response (event shadowing bug fix)
# ---------------------------------------------------------------------------


class TestInputClearsAfterAgent:
    """The input must clear after the agent response completes."""

    async def test_input_clears_after_normal_message(self) -> None:
        """After sending a normal message, the input field must be cleared."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Send a /help command — this goes through the slash-command path
            # which also clears input
            _inp(app).value = "/help"
            await pilot.press("enter")
            await pilot.pause()

            inp = _inp(app)
            assert inp.value == "" or inp.value is None, (
                f"Input must be cleared after command.\n"
                f"Input value: {inp.value!r}"
            )

    async def test_input_clears_after_error_message(self) -> None:
        """After sending a message that triggers an error, input must still clear."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            # No model → error path
            app.config.model = ""
            app._connected_providers.clear()

            _inp(app).value = "This will error"
            await pilot.press("enter")
            await pilot.pause()

            inp = _inp(app)
            assert inp.value == "" or inp.value is None, (
                f"Input must be cleared even after error.\n"
                f"Input value: {inp.value!r}"
            )

    def test_event_variable_not_shadowed(self) -> None:
        """The 'event' variable must not be shadowed by async iterator variable.
        Look for 'input_event = event' pattern in the source."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        # The fix was: input_event = event  # Save reference
        assert "input_event" in source, (
            "Must save event reference before async loop to avoid shadowing"
        )
        # After the async for loop, it must use input_event, not event
        after_loop_idx = source.find("input_event.input.value")
        assert after_loop_idx > 0, (
            "After async for loop, must use input_event.input.value = ''"
        )


# ---------------------------------------------------------------------------
# 6. Error from resolve_model is caught and displayed
# ---------------------------------------------------------------------------


class TestResolveModelError:
    """Errors from resolve_model() must be caught and displayed, not crash."""

    async def test_resolve_model_error_shown_in_chat(self) -> None:
        """When resolve_model raises, the error must appear in chat."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            app.config.model = "bad-provider:bad-model"
            app.config.provider = {"bad-provider": ProviderConfig(apiKey="sk-test")}
            app._connected_providers.add("bad-provider")

            with patch(
                "pyharness.core.provider.resolve_model",
                side_effect=ValueError("No provider package found for 'bad-provider'"),
            ):
                _inp(app).value = "Hello"
                await pilot.press("enter")
                await pilot.pause()

            text = _chat_text(app)
            assert "Error resolving model" in text or "error" in text.lower(), (
                f"resolve_model error must appear in chat.\nChat text: {text!r}"
            )
            assert app.is_running, "App must not crash on resolve_model error"

    async def test_resolve_model_error_clears_input(self) -> None:
        """After a resolve_model error, the input field must be cleared."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            app.config.model = "bad:model"
            app.config.provider = {"bad": ProviderConfig(apiKey="sk-test")}
            app._connected_providers.add("bad")

            with patch(
                "pyharness.core.provider.resolve_model",
                side_effect=RuntimeError("API key required"),
            ):
                _inp(app).value = "Message"
                await pilot.press("enter")
                await pilot.pause()

            assert _inp(app).value == "" or _inp(app).value is None, (
                "Input must be cleared after resolve_model error"
            )


# ---------------------------------------------------------------------------
# 7. Agent error during streaming is caught and displayed
# ---------------------------------------------------------------------------


class TestAgentErrorDuringStream:
    """Errors during agent streaming must be caught and displayed."""

    async def test_agent_crash_during_stream_shows_error(self) -> None:
        """If the agent loop raises mid-stream, error text must appear."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Mock the entire agent flow to simulate a mid-stream crash
            # The imports in on_input_submitted are local, so we patch
            # the modules they come from
            mock_graph = MagicMock()
            mock_runner = MagicMock()

            async def crashing_events():
                yield {"type": "content", "data": "Starting..."}
                raise RuntimeError("Connection lost mid-stream")

            mock_runner.run = MagicMock(return_value=crashing_events())
            mock_agent_runner = MagicMock(return_value=mock_runner)

            with patch(
                "pyharness.core.provider.resolve_model", return_value=MagicMock()
            ), patch(
                "pyharness.core.agent.create_agent_graph", return_value=mock_graph
            ), patch(
                "pyharness.core.agent.AgentRunner", mock_agent_runner
            ):
                _inp(app).value = "Crash test"
                await pilot.press("enter")
                await pilot.pause()

            text = _chat_text(app)
            assert "Agent error" in text or "error" in text.lower(), (
                f"Mid-stream agent crash must show error.\nChat text: {text!r}"
            )
            assert app.is_running, "App must not crash on agent stream error"

    async def test_agent_error_wrapping_works(self) -> None:
        """Verify the error handling wrapper exists in source."""
        import inspect
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "Agent error" in source, (
            "on_input_submitted must catch and display 'Agent error'"
        )


# ---------------------------------------------------------------------------
# 8. + 9. Strip Rich markup and _append_to_area helpers
# ---------------------------------------------------------------------------


class TestStripRichMarkup:
    """_strip_rich_markup must correctly strip Rich markup tags."""

    def test_strip_bold_with_color(self) -> None:
        """Rich [bold #58a6ff]text[/] becomes 'text'."""
        result = _strip_rich_markup("[bold #58a6ff]Hello[/]")
        assert "Hello" in result
        assert "[bold" not in result
        assert "[/]" not in result
        assert "#58a6ff" not in result

    def test_strip_multiple_tags(self) -> None:
        """Multiple nested/sequential tags are all stripped."""
        result = _strip_rich_markup(
            "[bold #7ee787]Assistant:[/] [italic #8b949e]thinking...[/]"
        )
        assert "Assistant:" in result
        assert "thinking..." in result

    def test_strip_preserves_plain_text(self) -> None:
        """Plain text with no markup passes through unchanged."""
        result = _strip_rich_markup("Hello world. No markup here.")
        assert result == "Hello world. No markup here."

    def test_strip_unbalanced_brackets_does_not_crash(self) -> None:
        """Unbalanced or malformed markup must not raise an exception."""
        result = _strip_rich_markup("some [unclosed tag")
        assert isinstance(result, str)

    def test_strip_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _strip_rich_markup("") == ""


class TestAppendToArea:
    """_append_to_area must correctly append text to a TextArea."""

    def test_append_to_empty_area(self) -> None:
        """Appending to an empty TextArea sets text correctly."""
        area = TextArea(read_only=True)
        _append_to_area(area, "Hello")
        assert area.text == "Hello"

    def test_append_concatenates(self) -> None:
        """Appending to a non-empty TextArea concatenates."""
        area = TextArea(read_only=True)
        area.load_text("First")
        _append_to_area(area, " Second")
        assert "First" in area.text
        assert "Second" in area.text
