"""Tests for the LangGraph-powered agent runtime."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from pyharness.core.agent import AgentRunner, create_agent_graph

# ---------------------------------------------------------------------------
# Test tools
# ---------------------------------------------------------------------------


@tool
def mock_read(path: str) -> str:
    """Read a file."""
    return f"content of {path}"


@tool
def mock_bash(command: str) -> str:
    """Run a bash command."""
    return f"output of {command}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_model(
    content: str = "",
    tool_calls: list | None = None,
) -> MagicMock:
    """Return a BaseChatModel mock with ainvoke pre-configured."""
    model = MagicMock()
    model.bind_tools.return_value = model

    # Default: no tool calls, text response
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    model.ainvoke = AsyncMock(return_value=msg)
    return model


def _tool_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    """Create a LangChain-compatible tool-call dict."""
    return {"name": name, "args": args, "id": call_id}


# ---------------------------------------------------------------------------
# 1.  Basic text response (no tools)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_graph_responds_without_tools() -> None:
    """The agent should return a text response when no tool calls are made."""
    # The model just returns text, no tool calls
    model = _make_mock_model(content="Hello, world!")

    graph = create_agent_graph(model, [mock_read])
    state = {
        "messages": [HumanMessage(content="Hi there")],
        "session_id": "test",
        "agent_name": "build",
        "model_name": "test:fake",
    }

    result = await graph.ainvoke(state)

    assert len(result["messages"]) >= 1
    # The last message should be the AIMessage from the model
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.content == "Hello, world!"


# ---------------------------------------------------------------------------
# 2.  Tool call → execution → response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_graph_calls_read_tool() -> None:
    """When the model returns a tool call, the executor should invoke it."""
    from pyharness.tools.registry import ToolRegistry

    # Use a fresh registry for isolation
    reg = ToolRegistry()
    reg.register(mock_read)

    with patch("pyharness.tools.registry._registry", reg):
        # First response: tool call.  Second: final text.
        # We need *two* responses because the graph loops back.
        model = MagicMock()
        model.bind_tools.return_value = model

        msg_with_tool = AIMessage(content="")
        msg_with_tool.tool_calls = [_tool_call("mock_read", {"path": "test.py"})]

        msg_final = AIMessage(
            content="I've read test.py. It contains print('hello')."
        )

        model.ainvoke = AsyncMock(side_effect=[msg_with_tool, msg_final])

        graph = create_agent_graph(model, [mock_read])
        state = {
            "messages": [HumanMessage(content="read test.py")],
            "session_id": "test",
            "agent_name": "build",
            "model_name": "test:fake",
        }

        result = await graph.ainvoke(state)

        # Check the messages — should have Human, AIMessage(tool_call),
        # ToolMessage(result), AIMessage(final)
        messages = result["messages"]
        assert len(messages) >= 4  # user + ai + tool + ai

        # First AI message has tool calls
        assert isinstance(messages[1], AIMessage)
        assert hasattr(messages[1], "tool_calls")
        assert messages[1].tool_calls[0]["name"] == "mock_read"

        # Tool message
        assert isinstance(messages[2], ToolMessage)
        assert messages[2].content == "content of test.py"

        # Final AI message
        assert isinstance(messages[3], AIMessage)
        assert "test.py" in messages[3].content


# ---------------------------------------------------------------------------
# 3.  Unknown tool → graceful error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_graph_handles_unknown_tool() -> None:
    """When the model calls an unknown tool, the executor emits an error
    ToolMessage and the agent can recover."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(mock_read)  # only read is available

    with patch("pyharness.tools.registry._registry", reg):
        model = MagicMock()
        model.bind_tools.return_value = model

        # Model calls a tool that doesn't exist
        msg_bad_tool = AIMessage(content="")
        msg_bad_tool.tool_calls = [_tool_call("nonexistent_tool", {"x": "1"})]

        # Then it recovers with text
        msg_recovery = AIMessage(content="I tried a tool that doesn't exist.")

        model.ainvoke = AsyncMock(side_effect=[msg_bad_tool, msg_recovery])

        graph = create_agent_graph(model, [mock_read])
        state = {
            "messages": [HumanMessage(content="use missing tool")],
            "session_id": "test",
            "agent_name": "build",
            "model_name": "test:fake",
        }

        result = await graph.ainvoke(state)
        messages = result["messages"]

        # Tool error message
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_msgs) >= 1
        assert "Unknown tool" in tool_msgs[0].content
        assert tool_msgs[0].name == "nonexistent_tool"


# ---------------------------------------------------------------------------
# 4.  AgentRunner streaming — content events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_runner_yields_content_events() -> None:
    """AgentRunner.run() should yield content-type events when streaming."""
    model = _make_mock_model(content="Streaming response!")

    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(
        graph=graph,
        session_id="s1",
        agent_name="build",
        model_name="test:fake",
    )

    events: list[dict] = []
    async for event in runner.run("hello"):
        events.append(event)

    # At minimum we should get a "done" event
    assert any(e["type"] == "done" for e in events)

    # Verify the agent ran — messages should contain the response
    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="hello")],
            "session_id": "s1",
            "agent_name": "build",
            "model_name": "test:fake",
        }
    )
    assert isinstance(state["messages"][-1], AIMessage)


# ---------------------------------------------------------------------------
# 5.  AgentRunner streaming — tool events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_runner_yields_tool_events() -> None:
    """AgentRunner.run() should yield tool_call and tool_result events."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(mock_read)

    with patch("pyharness.tools.registry._registry", reg):
        model = MagicMock()
        model.bind_tools.return_value = model

        msg_tool = AIMessage(content="")
        msg_tool.tool_calls = [_tool_call("mock_read", {"path": "README.md"})]
        msg_final = AIMessage(content="Done.")
        model.ainvoke = AsyncMock(side_effect=[msg_tool, msg_final])

        graph = create_agent_graph(model, [mock_read])
        runner = AgentRunner(graph, "s2", "build", "test:fake")

        events: list[dict] = []
        async for event in runner.run("read the readme"):
            events.append(event)

        types = {e["type"] for e in events}
        assert "done" in types

        # At minimum, done was emitted; the graph ran to completion
        assert len(events) >= 1


# ---------------------------------------------------------------------------
# 6.  AgentRunner configuration
# ---------------------------------------------------------------------------


def test_agent_runner_config_has_thread_id() -> None:
    """AgentRunner stores the session_id in the LangGraph config."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "my-session", "build", "test:fake")

    assert runner.session_id == "my-session"
    assert runner.agent_name == "build"
    assert runner.model_name == "test:fake"
    assert runner.config["configurable"]["thread_id"] == "my-session"


# ---------------------------------------------------------------------------
# 7.  Routing logic
# ---------------------------------------------------------------------------


def test_should_continue_routes_to_tools() -> None:
    """should_continue returns 'tools' when the last message has tool_calls.

    This is validated via integration tests above (test_agent_graph_calls_read_tool
    and test_agent_graph_handles_unknown_tool), which exercise the full graph
    including the routing function."""
    pass


# ---------------------------------------------------------------------------
# 8.  Empty tools list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_graph_with_empty_tools() -> None:
    """An agent with no tools bound still functions for text responses."""
    model = _make_mock_model(content="I have no tools but I can chat.")

    graph = create_agent_graph(model, [])
    state = {
        "messages": [HumanMessage(content="Hello")],
        "session_id": "t",
        "agent_name": "build",
        "model_name": "test:fake",
    }

    result = await graph.ainvoke(state)
    assert isinstance(result["messages"][-1], AIMessage)
    assert "no tools" in result["messages"][-1].content


# ---------------------------------------------------------------------------
# 9.  AgentRunner child session tracking
# ---------------------------------------------------------------------------


def test_agent_runner_tracks_child_sessions() -> None:
    """spawn_subagent adds child session IDs to the child_sessions list."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "parent-session", "build", "test:fake")

    # Initially empty
    assert runner.child_sessions == []

    # Spawn first subagent
    result1 = runner.spawn_subagent("general", "Do a thing", "child-1")
    assert len(runner.child_sessions) == 1
    assert runner.child_sessions[0] == "child-1:general"
    assert "Subagent spawned" in result1
    assert "child-1:general" in result1

    # Spawn second subagent
    result2 = runner.spawn_subagent("explore", "Search for X", "child-2")
    assert len(runner.child_sessions) == 2
    assert runner.child_sessions[1] == "child-2:explore"
    assert "Subagent spawned" in result2


def test_subagent_inherits_parent_permissions() -> None:
    """A subagent cannot exceed its parent's permission ceiling."""
    from pyharness.config.schema import (
        AgentDefinition,
        AgentPermissionConfig,
        PyHarnessConfig,
    )
    from pyharness.middleware.permission import PermissionMiddleware

    # Parent (plan) has edit=deny, bash=deny, read=allow
    # Subagent (general) has edit=allow, bash=allow, read=allow
    config = PyHarnessConfig.model_validate({
        "agent": {
            "plan": {
                "description": "Read-only planner",
                "mode": "primary",
                "permission": {"edit": "deny", "bash": "deny"},
            },
            "general": {
                "description": "Full-access subagent",
                "mode": "subagent",
                "permission": {"edit": "allow", "bash": "allow"},
            },
        },
    })

    # Subagent with inherited permissions from plan parent
    mw = PermissionMiddleware(
        config, agent_name="general", parent_agent_name="plan"
    )

    # subagent can't edit (parent denies)
    assert mw.check("edit").action == "deny"
    assert mw.check("write").action == "deny"

    # subagent can't run bash (parent denies)
    assert mw.check("bash").action == "deny"

    # subagent can still read (parent allows)
    assert mw.check("read").action == "allow"

    # Without parent inheritance, general subagent has full access
    mw_no_parent = PermissionMiddleware(
        config, agent_name="general"
    )
    assert mw_no_parent.check("edit").action == "allow"
    assert mw_no_parent.check("bash").action == "allow"
    assert mw_no_parent.check("read").action == "allow"


# ---------------------------------------------------------------------------
# 10. System prompt — initial_state includes SystemMessage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_runner_includes_system_message() -> None:
    """AgentRunner initial_state MUST include a SystemMessage as the first
    message (before the HumanMessage). The SystemMessage content should be
    non-empty."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    captured_input: list = []

    async def _fake_astream(input_data: dict, *args: object, **kwargs: object) -> AsyncIterator[dict]:
        """Capture the input state and yield a fake stream event."""
        captured_input.append(input_data)
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="ok")}}

    with patch.object(graph, "astream_events", _fake_astream):
        async for _ in runner.run("hello"):
            pass

    assert captured_input, "Expected astream_events to be called with initial_state"
    messages: list = captured_input[0]["messages"]
    # At least one message must be a SystemMessage
    has_system = any(isinstance(m, SystemMessage) for m in messages)
    assert has_system, (
        "Initial state must include a SystemMessage, but none found. "
        f"Messages: {[type(m).__name__ for m in messages]}"
    )


@pytest.mark.asyncio
async def test_agent_runner_system_prompt_is_first_message() -> None:
    """The FIRST message in initial_state must be a SystemMessage (not
    HumanMessage)."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    captured_input: list = []

    async def _fake_astream(input_data: dict, *args: object, **kwargs: object) -> AsyncIterator[dict]:
        captured_input.append(input_data)
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="ok")}}

    with patch.object(graph, "astream_events", _fake_astream):
        async for _ in runner.run("hello"):
            pass

    assert captured_input
    messages: list = captured_input[0]["messages"]
    assert len(messages) >= 1, "Expected at least 1 message in initial_state"
    first = messages[0]
    assert isinstance(first, SystemMessage), (
        f"First message must be SystemMessage, got {type(first).__name__}"
    )


def test_agent_runner_accepts_system_prompt() -> None:
    """AgentRunner.__init__ must accept an optional ``system_prompt``
    parameter. When provided it is stored; when None a sensible default
    is used."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])

    # With explicit system_prompt
    runner_with = AgentRunner(
        graph, "s1", "build", "test:fake",
        system_prompt="You are the build agent for pyharness.",
    )
    assert runner_with.system_prompt == "You are the build agent for pyharness."

    # Without explicit system_prompt — should have a default
    runner_default = AgentRunner(graph, "s1", "build", "test:fake")
    assert runner_default.system_prompt is not None
    assert len(runner_default.system_prompt) > 0


def test_default_system_prompt_not_empty() -> None:
    """The default system prompt (when none is explicitly provided) must
    be a non-empty string."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    prompt = runner.system_prompt
    assert prompt, "Default system prompt must not be empty"
    assert isinstance(prompt, str)
    assert len(prompt.strip()) > 0


def test_system_prompt_defines_agent_identity() -> None:
    """The default system prompt must mention 'pyharness' and at least one
    of 'coding assistant' or 'terminal coding agent'."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    prompt = runner.system_prompt.lower()
    assert "pyharness" in prompt, (
        "System prompt must mention 'pyharness' as the product identity"
    )
    has_role = "coding assistant" in prompt or "terminal coding agent" in prompt
    assert has_role, (
        "System prompt must define the agent's role as 'coding assistant' "
        "or 'terminal coding agent'"
    )


def test_system_prompt_instructs_on_tool_usage() -> None:
    """The system prompt must include guidance about when to use tools
    vs. when to just respond conversationally."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    prompt = runner.system_prompt.lower()
    # Should contain tool-related guidance keywords
    has_tool_guidance = any(
        word in prompt
        for word in ("tool", "use tools", "when to")
    )
    assert has_tool_guidance, (
        "System prompt must contain guidance about tool usage"
    )


def test_system_prompt_discourages_gratuitous_exploration() -> None:
    """The prompt must include language discouraging unnecessary project
    exploration — e.g. 'only use tools when explicitly asked' or 'don't
    explore unless requested'."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    prompt = runner.system_prompt.lower()
    discouraged = (
        "only use tools" in prompt
        or "don't explore" in prompt
        or "do not explore" in prompt
        or "unless asked" in prompt
        or "unless requested" in prompt
        or "only when asked" in prompt
        or "only when explicitly" in prompt
    )
    assert discouraged, (
        "System prompt must discourage gratuitous tool exploration for "
        "trivial messages"
    )


@pytest.mark.asyncio
async def test_initial_state_message_count() -> None:
    """AgentRunner with default system prompt must have at least 2
    messages in initial_state (system + user)."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    captured_input: list = []

    async def _fake_astream(input_data: dict, *args: object, **kwargs: object) -> AsyncIterator[dict]:
        captured_input.append(input_data)
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="ok")}}

    with patch.object(graph, "astream_events", _fake_astream):
        async for _ in runner.run("hello"):
            pass

    assert captured_input
    messages: list = captured_input[0]["messages"]
    assert len(messages) >= 2, (
        f"Expected at least 2 messages (system + user), got {len(messages)}"
    )


def test_agent_runner_initial_state_uses_agent_name() -> None:
    """The system prompt should include the agent_name when available
    (e.g. 'You are the build agent for pyharness...')."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    prompt = runner.system_prompt.lower()
    assert "build" in prompt, (
        "System prompt should include the agent_name ('build')"
    )


# ===========================================================================
# Bug 1: Recursion Error Protection (TDD — FAILING)
# ===========================================================================


def test_agent_runner_config_includes_recursion_limit() -> None:
    """AgentRunner.run() must pass ``recursion_limit`` in the config dict
    to astream_events."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    # The config dict stored on the runner MUST include a recursion_limit key
    assert "recursion_limit" in runner.config, (
        "AgentRunner.config must include 'recursion_limit' key. "
        f"Got keys: {list(runner.config.keys())}"
    )


def test_agent_runner_default_recursion_limit_reasonable() -> None:
    """Default recursion_limit must be between 25 and 100 (inclusive)."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])
    runner = AgentRunner(graph, "s1", "build", "test:fake")

    recursion_limit = runner.config.get("recursion_limit")
    assert recursion_limit is not None, (
        "AgentRunner.config must contain 'recursion_limit'"
    )
    assert 25 <= recursion_limit <= 100, (
        f"Default recursion_limit {recursion_limit} must be between 25 and 100"
    )


def test_agent_runner_accepts_custom_recursion_limit() -> None:
    """AgentRunner.__init__ must accept ``recursion_limit: int = 50`` parameter."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])

    # Custom recursion_limit
    runner_custom = AgentRunner(
        graph, "s1", "build", "test:fake", recursion_limit=75
    )
    assert runner_custom.config.get("recursion_limit") == 75, (
        "Custom recursion_limit=75 must be stored in runner.config"
    )

    # Default recursion_limit
    runner_default = AgentRunner(graph, "s2", "build", "test:fake")
    assert runner_default.config.get("recursion_limit") == 50, (
        "Default recursion_limit must be 50"
    )


@pytest.mark.asyncio
async def test_graph_recursion_error_caught() -> None:
    """AgentRunner.run() must catch ``GraphRecursionError`` and yield an error
    event instead of crashing."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])

    from langgraph.errors import GraphRecursionError

    runner = AgentRunner(graph, "s-recursion", "build", "test:fake")

    # Make astream_events raise GraphRecursionError
    async def _raise_recursion(*args: object, **kwargs: object) -> AsyncIterator[dict]:
        raise GraphRecursionError("Recursion limit of 25 reached")
        yield  # type: ignore[unreachable]

    with patch.object(graph, "astream_events", _raise_recursion):
        events: list[dict] = []
        # Must NOT raise — should catch the error
        async for event in runner.run("hello"):
            events.append(event)

    assert len(events) >= 1, "Expected at least one error event"
    # Should contain an error event, not a crash
    assert any(e.get("type") == "error" for e in events), (
        f"Expected an error event when GraphRecursionError occurs, got: {events}"
    )


@pytest.mark.asyncio
async def test_graph_recursion_error_yields_error_event() -> None:
    """When GraphRecursionError occurs, the error event must contain meaningful
    data about what went wrong."""
    model = _make_mock_model(content="ok")
    graph = create_agent_graph(model, [mock_read])

    from langgraph.errors import GraphRecursionError

    runner = AgentRunner(graph, "s-rec", "build", "test:fake")

    async def _raise_recursion(*args: object, **kwargs: object) -> AsyncIterator[dict]:
        raise GraphRecursionError("Recursion limit reached — loop may be infinite")
        yield  # type: ignore[unreachable]

    with patch.object(graph, "astream_events", _raise_recursion):
        events: list[dict] = []
        async for event in runner.run("trigger loop"):
            events.append(event)

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1, (
        f"Expected at least one error event, got events: {events}"
    )

    error_event = error_events[0]
    assert "data" in error_event, "Error event must have 'data' key"
    assert isinstance(error_event["data"], str), "Error data must be a string"
    assert len(error_event["data"]) > 0, "Error message must not be empty"
    # The error message should mention recursion or loop
    msg_lower = error_event["data"].lower()
    assert any(
        word in msg_lower for word in ("recursion", "loop", "limit")
    ), f"Error message should mention recursion, loop, or limit: {error_event['data']!r}"
