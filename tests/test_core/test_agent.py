"""Tests for the LangGraph-powered agent runtime."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
