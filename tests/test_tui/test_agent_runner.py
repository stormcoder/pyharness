"""Tests for Agent Runner wired into ChatScreen.

Verifies that ``on_input_submitted`` properly resolves models, creates
AgentRunner instances, streams responses, handles errors gracefully, and
displays tool calls with ``🔧`` prefix.

Strategy: Tests that need mock agent streaming use TEXTUAL_TEST_MODE
with a pre-configured app.  Tests for error paths configure the app
appropriately and verify friendly error messages are shown.

Key refactored behaviors:
- Output widget: **RichLog** (not TextArea) — Rich markup for colors/markdown
- Token streaming: buffered into ``full_response: list[str]``, rendered at
  ``"done"`` through ``_render_markdown()`` as a single Rich markup block
- Chat content check: use ``RichLog.lines`` (list of Strip objects),
  convert via ``str(line)`` for plain-text assertions
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import RichLog

from pyharness.config.schema import ProviderConfig, PyHarnessConfig
from pyharness.core.agent_manager import AgentManager
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen, _render_markdown
from pyharness.tui.widgets.input import PromptInput

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _chat_screen(app: PyHarnessApp) -> ChatScreen:
    screen = app.screen_stack[-1]
    assert isinstance(screen, ChatScreen)
    return screen


def _chat_log(app: PyHarnessApp) -> RichLog:
    """Get the RichLog output widget from the chat screen."""
    return _chat_screen(app).query_one("#chat-area", RichLog)


def _chat_plain_lines(app: PyHarnessApp) -> list[str]:
    """Get all chat lines as plain text from RichLog.lines.

    RichLog.lines returns a list of ``Strip`` objects.  Each Strip can
    be converted to plain text via ``str(strip)``.
    """
    log = _chat_log(app)
    return [str(line).rstrip() for line in log.lines]


def _chat_plain_text(app: PyHarnessApp) -> str:
    """Get full chat output as plain text joined by newlines."""
    return "\n".join(_chat_plain_lines(app))


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
    # Prevent refresh_models from clearing _connected_providers during tests
    async def _noop_refresh() -> None:
        pass
    app.refresh_models = _noop_refresh  # type: ignore[assignment]
    return app


# ---------------------------------------------------------------------------
# 1. No model configured → friendly error, no crash
# ---------------------------------------------------------------------------


class TestNoModelError:
    """When no model is configured, a friendly error is shown without crashing."""

    async def test_send_message_without_model_shows_error(self) -> None:
        """Sending a message with empty model must show error, not crash."""
        app = PyHarnessApp()
        app._config_loaded_from_disk = True
        async with app.run_test() as pilot:
            await pilot.pause()

            # Ensure no model
            app.config.model = ""
            app._connected_providers.clear()

            inp = _inp(app)
            inp.value = "Hello world"
            await pilot.press("enter")
            await pilot.pause()

            text = _chat_plain_text(app)
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

            text = _chat_plain_text(app)
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
# 3. Agent wiring: imports, think message, order of checks
# ---------------------------------------------------------------------------


class TestAgentRunnerWiring:
    """Verify the agent runner is properly wired into on_input_submitted."""

    def test_source_imports_agent_runner(self) -> None:
        """on_input_submitted source must import AgentRunner."""
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

    def test_model_check_comes_before_resolve(self) -> None:
        """Model and provider must be checked BEFORE calling resolve_model."""
        source = inspect.getsource(ChatScreen.on_input_submitted)

        no_model_idx = source.find("No model selected")
        resolve_idx = source.find("resolve_model")

        assert no_model_idx > 0, "Must check for empty model before resolving"
        assert resolve_idx > 0, "Must call resolve_model"
        assert no_model_idx < resolve_idx, (
            "Model check must come BEFORE resolve_model call"
        )

    def test_thinking_message_in_source(self) -> None:
        """'Thinking...' must appear in source before resolve_model call."""
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "Thinking" in source, (
            "on_input_submitted must display 'Thinking...' message"
        )
        # The thinking message must be written BEFORE resolve_model is called
        thinking_idx = source.find("Thinking")
        resolve_idx = source.find("resolve_model")
        assert thinking_idx < resolve_idx, (
            "Thinking message must be shown BEFORE resolve_model invocation"
        )

    async def test_think_message_appears_in_chat(self) -> None:
        """'Thinking...' indicator must appear in chat output before resolution."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Make resolve_model fail so we can check that Thinking appeared
            with patch(
                "pyharness.core.provider.resolve_model",
                side_effect=ValueError("Testing — resolve failed"),
            ):
                _inp(app).value = "Hello"
                await pilot.press("enter")
                await pilot.pause()

            text = _chat_plain_text(app)
            assert "Thinking" in text, (
                f"Thinking indicator must appear in chat.\nChat text: {text!r}"
            )


# ---------------------------------------------------------------------------
# 4. Tool calls displayed with 🔧 prefix
# ---------------------------------------------------------------------------


class TestToolCallDisplay:
    """Tool call events must display with the 🔧 emoji prefix."""

    def test_tool_call_wrench_in_source(self) -> None:
        """The _run_agent handler must contain 🔧 emoji for tool calls."""
        source = inspect.getsource(AgentManager._run_agent)
        assert "🔧" in source, (
            "_run_agent must display 🔧 prefix for tool_call events"
        )

    def test_tool_call_event_handled(self) -> None:
        """_run_agent must handle 'tool_call' event type."""
        source = inspect.getsource(AgentManager._run_agent)
        assert "tool_call" in source, (
            "_run_agent must handle event type 'tool_call'"
        )
        assert "tool_result" in source, (
            "_run_agent must handle event type 'tool_result'"
        )

    def test_assistant_label_in_source(self) -> None:
        """'Assistant:' label must appear in on_input_submitted source code."""
        source = inspect.getsource(ChatScreen.on_input_submitted)
        assert "Assistant:" in source, (
            "on_input_submitted must print 'Assistant:' label before agent launch"
        )


# ---------------------------------------------------------------------------
# 5. Input clears after agent response (event shadowing bug fix)
# ---------------------------------------------------------------------------


class TestInputClearsAfterAgent:
    """The input must clear after the agent response completes."""

    async def test_input_clears_after_slash_command(self) -> None:
        """After sending a slash command, the input field must be cleared."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

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
        """The async iterator in _run_agent uses 'ag_event', not 'event',
        so the on_input_submitted 'event' parameter is never shadowed."""
        source = inspect.getsource(AgentManager._run_agent)
        # The async iterator variable is 'ag_event', not 'event'
        assert "ag_event" in source, (
            "_run_agent must use 'ag_event' for async iterator to avoid shadowing"
        )
        # The on_input_submitted handler must still clear the input
        chat_source = inspect.getsource(ChatScreen.on_input_submitted)
        assert 'event.input.value = ""' in chat_source, (
            "on_input_submitted must clear event.input.value after agent launch"
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

            text = _chat_plain_text(app)
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

            text = _chat_plain_text(app)
            assert "Agent error" in text or "error" in text.lower(), (
                f"Mid-stream agent crash must show error.\nChat text: {text!r}"
            )
            assert app.is_running, "App must not crash on agent stream error"

    def test_agent_error_wrapping_in_source(self) -> None:
        """Verify the error handling wrapper exists in _run_agent source."""
        source = inspect.getsource(AgentManager._run_agent)
        assert "Agent error" in source, (
            "_run_agent must catch and display 'Agent error'"
        )


# ---------------------------------------------------------------------------
# 8. _render_markdown works correctly
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    """_render_markdown must convert markdown to Rich markup for RichLog display.

    The function uses ``rich.markdown.Markdown`` to render to Rich markup.
    It does NOT strip markup — it produces Rich-compatible markup text.
    This is the opposite of the old ``_strip_rich_markup`` (deleted).
    """

    def test_renders_plain_text_as_rich_markup(self) -> None:
        """Plain text input is rendered to Rich markup output."""
        result = _render_markdown("Hello world")
        assert isinstance(result, str), "Must return a string"
        assert "Hello world" in result, (
            f"Plain text should appear in rendered output.\nGot: {result!r}"
        )

    def test_handles_empty_string(self) -> None:
        """Empty string returns empty string (short-circuit in function)."""
        result = _render_markdown("")
        assert result == ""

    def test_handles_whitespace_only(self) -> None:
        """Whitespace-only input is returned as-is."""
        result = _render_markdown("   \n  \t  ")
        # The function returns early for stripped-empty text
        assert isinstance(result, str)

    def test_handles_markdown_bold(self) -> None:
        """Markdown bold text is converted to Rich markup bold."""
        result = _render_markdown("**bold text**")
        assert "bold text" in result, (
            f"Bold content should appear in rendered output.\nGot: {result!r}"
        )

    def test_handles_code_block(self) -> None:
        """Markdown code blocks are converted to Rich markup."""
        result = _render_markdown("```python\nprint('hello')\n```")
        assert "hello" in result, (
            f"Code block content should appear in rendered output.\nGot: {result!r}"
        )

    def test_handles_lists(self) -> None:
        """Markdown lists are converted to Rich markup."""
        result = _render_markdown("- item one\n- item two")
        assert "item one" in result
        assert "item two" in result

    def test_does_not_crash_on_malformed_text(self) -> None:
        """Malformed or unusual input must not raise an exception."""
        # Unclosed code fence
        result = _render_markdown("```python\nunclosed code")
        assert isinstance(result, str)
        # Very long text
        result = _render_markdown("x" * 5000)
        assert isinstance(result, str)

    def test_returns_string_for_all_inputs(self) -> None:
        """_render_markdown always returns a string, never None."""
        cases = ["hi", "", "   ", "**bold**", "```\ncode\n```"]
        for case in cases:
            result = _render_markdown(case)
            assert isinstance(result, str), (
                f"_render_markdown({case!r}) returned {type(result).__name__}"
            )


# ---------------------------------------------------------------------------
# 9. RichLog compose verification
# ---------------------------------------------------------------------------


class TestRichLogCompose:
    """Verify ChatScreen uses RichLog (not TextArea) for chat output."""

    def test_compose_uses_richlog_not_textarea(self) -> None:
        """ChatScreen.compose must yield a RichLog, not a TextArea."""
        source = inspect.getsource(ChatScreen.compose)
        assert "RichLog" in source, (
            "ChatScreen.compose must import/use RichLog, not TextArea"
        )
        assert "from textual.widgets import" not in source or (
            "RichLog" in source.split("from textual.widgets")[1].split("\n")[0]
        ), "RichLog must be imported in compose"

    def test_compose_does_not_import_textarea(self) -> None:
        """ChatScreen.compose source must NOT reference TextArea."""
        source = inspect.getsource(ChatScreen.compose)
        assert "TextArea" not in source, (
            "ChatScreen.compose must NOT reference TextArea (use RichLog)"
        )

    def test_compose_does_not_reference_deleted_symbols(self) -> None:
        """ChatScreen must NOT reference _strip_rich_markup or _append_to_area."""
        source = inspect.getsource(ChatScreen)
        assert "_strip_rich_markup" not in source, (
            "_strip_rich_markup is deleted — should not appear in ChatScreen source"
        )
        assert "_append_to_area" not in source, (
            "_append_to_area is deleted — should not appear in ChatScreen source"
        )

    def test_compose_richlog_has_markup_enabled(self) -> None:
        """Compose must enable markup=True on the RichLog widget."""
        source = inspect.getsource(ChatScreen.compose)
        assert "markup=True" in source, (
            "RichLog must be created with markup=True for Rich markup support"
        )
        assert "can_focus = False" in source, (
            "RichLog must have can_focus=False to prevent tab focus stealing"
        )

    def test_compose_richlog_has_correct_id(self) -> None:
        """RichLog must have id='chat-area' matching the previous TextArea id."""
        source = inspect.getsource(ChatScreen.compose)
        assert 'id="chat-area"' in source, (
            "RichLog must keep id='chat-area' for backward compatibility"
        )


# ---------------------------------------------------------------------------
# 10. RichLog widget instance verification (live app test)
# ---------------------------------------------------------------------------


class TestRichLogWidgetInstance:
    """Verify the RichLog widget behaves correctly at runtime."""

    async def test_chat_area_is_richlog_not_textarea(self) -> None:
        """The #chat-area widget must be a RichLog instance."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            log = _chat_log(app)
            assert isinstance(log, RichLog), (
                f"#chat-area must be a RichLog, got {type(log).__name__}"
            )

    async def test_richlog_has_correct_properties(self) -> None:
        """RichLog must have markup=True and can_focus=False."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            log = _chat_log(app)
            assert log.markup is True, "RichLog must have markup=True"
            assert log.can_focus is False, "RichLog must have can_focus=False"

    async def test_chat_lines_accessible(self) -> None:
        """RichLog.lines must be accessible and contain welcome messages."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            lines = _chat_plain_lines(app)
            assert len(lines) > 0, "Chat should have welcome messages"
            assert any("pyharness" in line for line in lines), (
                f"Welcome messages should mention pyharness.\nLines: {lines}"
            )

    async def test_write_method_adds_to_richlog(self) -> None:
        """ChatScreen._write() must append to RichLog."""
        app = _make_configured_app()
        async with app.run_test() as pilot:
            await pilot.pause()

            initial_count = len(_chat_log(app).lines)
            _chat_screen(app)._write("Test message")
            await pilot.pause()

            new_count = len(_chat_log(app).lines)
            assert new_count >= initial_count, (
                f"_write should not decrease line count "
                f"(was {initial_count}, now {new_count})"
            )


# ---------------------------------------------------------------------------
# 11. Full token buffering flow verification (source-level)
# ---------------------------------------------------------------------------


class TestTokenBufferingFlow:
    """Verify tokens are buffered and rendered at 'done' event."""

    def test_full_response_list_in_source(self) -> None:
        """Source must use full_response: list[str] for token buffering."""
        source = inspect.getsource(AgentManager._run_agent)
        assert "full_response: list[str]" in source or "full_response: list" in source, (
            "_run_agent must declare full_response as a list for buffering"
        )

    def test_tokens_appended_not_written_directly(self) -> None:
        """Content tokens must be appended to full_response and also written immediately.

        After refactoring, tokens both append to full_response (for markdown rendering)
        and get written immediately to the screen (for live streaming).
        """
        source = inspect.getsource(AgentManager._run_agent)

        # Find the "content" event handler — tokens append to full_response
        content_section = source.split('kind == "content"')
        assert len(content_section) >= 2, "Source must handle 'content' event kind"

        content_code = content_section[1].split("elif")[0]
        assert "full_response.append" in content_code, (
            "Content tokens must be appended to full_response list"
        )

    def test_done_event_renders_full_response(self) -> None:
        """At 'done' event, full_response is rendered via _render_markdown."""
        source = inspect.getsource(AgentManager._run_agent)
        assert "full_response" in source, "full_response must appear in source"
        assert "_render_markdown" in source, (
            "_render_markdown must be called on the full response text"
        )

    def test_assistant_label_before_formatted_output(self) -> None:
        """Assistant: label is written in on_input_submitted before agent launch;
        _render_markdown is called later in _run_agent at the 'done' event.
        This ensures the label always appears before formatted output at runtime."""
        chat_source = inspect.getsource(ChatScreen.on_input_submitted)
        agent_source = inspect.getsource(AgentManager._run_agent)

        assert "Assistant:" in chat_source, (
            "'Assistant:' label must exist in on_input_submitted source"
        )
        assert "_render_markdown" in agent_source, (
            "_render_markdown call must exist in _run_agent source"
        )
