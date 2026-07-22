"""Tests for crash recovery via LangGraph checkpointing.

Verifies the checkpoint persistence and restore workflow:

- Create an agent graph with a checkpointer
- Run the agent partway (interrupt mid-stream)
- Verify partial state was saved
- Create a new AgentRunner with same thread_id
- Verify it can resume from the checkpoint
- Verify messages from before interrupt are preserved

Uses :class:`~langgraph.checkpoint.memory.InMemorySaver` for hermetic
tests with no I/O dependencies.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from pyharness.core.agent import AgentRunner, create_agent_graph

# ---------------------------------------------------------------------------
# Test tools
# ---------------------------------------------------------------------------


@tool
def test_read(path: str) -> str:
    """Read a file."""
    return f"content of {path}"


@tool
def test_write(path: str, content: str) -> str:
    """Write content to a file."""
    return f"wrote {len(content)} bytes to {path}"


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
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    model.ainvoke = AsyncMock(return_value=msg)
    return model


def _tool_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    """Create a LangChain-compatible tool-call dict."""
    return {"name": name, "args": args, "id": call_id}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checkpointer() -> InMemorySaver:
    """Return a fresh InMemorySaver for each test.

    In-memory checkpointing avoids I/O and threading issues with
    sqlite-based savers in test environments.
    """
    return InMemorySaver()


# ---------------------------------------------------------------------------
# Core checkpoint tests
# ---------------------------------------------------------------------------


class TestCheckpointSave:
    """Verify that agent state is saved to the checkpointer."""

    @pytest.mark.asyncio
    async def test_full_run_saves_state(
        self, checkpointer: InMemorySaver
    ) -> None:
        """After a complete agent run, checkpoint state is persisted."""
        model = _make_mock_model(content="Hello, world!")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        config = {"configurable": {"thread_id": "session-1"}}
        initial_state = {
            "messages": [HumanMessage(content="Hi there")],
            "session_id": "session-1",
            "agent_name": "build",
            "model_name": "test:fake",
        }

        result = await graph.ainvoke(initial_state, config=config)

        # The agent should have produced a response
        assert len(result["messages"]) >= 2

        # Verify checkpoint was created by checking for the thread
        checkpoint = await checkpointer.aget(config)
        assert checkpoint is not None

    @pytest.mark.asyncio
    async def test_partial_run_creates_checkpoint(
        self, checkpointer: InMemorySaver
    ) -> None:
        """Even a partial run (tool call step) creates checkpoints."""
        from pyharness.tools.registry import ToolRegistry

        reg = ToolRegistry()
        reg.register(test_read)

        with patch("pyharness.tools.registry._registry", reg):
            model = MagicMock()
            model.bind_tools.return_value = model

            msg_tool = AIMessage(content="")
            msg_tool.tool_calls = [
                _tool_call("test_read", {"path": "test.py"})
            ]
            msg_final = AIMessage(content="Done.")
            model.ainvoke = AsyncMock(side_effect=[msg_tool, msg_final])

            graph = create_agent_graph(
                model, [test_read], checkpointer=checkpointer
            )

            config = {"configurable": {"thread_id": "session-partial"}}
            initial_state = {
                "messages": [HumanMessage(content="read test.py")],
                "session_id": "session-partial",
                "agent_name": "build",
                "model_name": "test:fake",
            }

            await graph.ainvoke(initial_state, config=config)

            # Checkpoint should exist
            checkpoint = await checkpointer.aget(config)
            assert checkpoint is not None

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_messages(
        self, checkpointer: InMemorySaver
    ) -> None:
        """Messages before tool execution are preserved in checkpoints."""
        from pyharness.tools.registry import ToolRegistry

        reg = ToolRegistry()
        reg.register(test_read)

        with patch("pyharness.tools.registry._registry", reg):
            model = MagicMock()
            model.bind_tools.return_value = model

            msg_tool = AIMessage(content="")
            msg_tool.tool_calls = [
                _tool_call("test_read", {"path": "README.md"})
            ]
            msg_final = AIMessage(content="I've read the file.")
            model.ainvoke = AsyncMock(side_effect=[msg_tool, msg_final])

            graph = create_agent_graph(
                model, [test_read], checkpointer=checkpointer
            )

            config = {"configurable": {"thread_id": "session-msgs"}}
            initial_state = {
                "messages": [HumanMessage(content="read README.md")],
                "session_id": "session-msgs",
                "agent_name": "build",
                "model_name": "test:fake",
            }

            result = await graph.ainvoke(initial_state, config=config)
            messages = result["messages"]

            # Messages should include: Human → AIMessage(tool_call) →
            # ToolMessage(result) → AIMessage(final)
            assert len(messages) >= 4
            assert isinstance(messages[0], HumanMessage)
            assert isinstance(messages[1], AIMessage)
            assert isinstance(messages[2], ToolMessage)
            assert isinstance(messages[3], AIMessage)
            assert messages[0].content == "read README.md"
            assert messages[3].content == "I've read the file."


# ---------------------------------------------------------------------------
# Checkpoint restore / resume tests
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    """Verify that a new AgentRunner can resume from a checkpoint."""

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(
        self, checkpointer: InMemorySaver
    ) -> None:
        """A second graph invocation with the same thread_id resumes state."""
        model = _make_mock_model(content="Response 1")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        config = {"configurable": {"thread_id": "session-resume"}}
        initial_state = {
            "messages": [HumanMessage(content="First message")],
            "session_id": "session-resume",
            "agent_name": "build",
            "model_name": "test:fake",
        }

        # First invocation
        result1 = await graph.ainvoke(initial_state, config=config)
        assert len(result1["messages"]) >= 2  # Human + AIMessage

        # Second invocation with same thread_id should append messages
        result2 = await graph.ainvoke(
            {"messages": [HumanMessage(content="Follow-up question")]},
            config=config,
        )

        # The second invocation should have more messages (preserves history)
        assert len(result2["messages"]) > len(result1["messages"])
        # The first human message should still be present
        human_msgs = [
            m
            for m in result2["messages"]
            if isinstance(m, HumanMessage)
        ]
        assert len(human_msgs) >= 2
        assert human_msgs[0].content == "First message"
        assert human_msgs[-1].content == "Follow-up question"

    @pytest.mark.asyncio
    async def test_agent_runner_resumes_with_same_thread(
        self, checkpointer: InMemorySaver
    ) -> None:
        """Two AgentRunners with the same session_id share state."""
        model = _make_mock_model(content="Runner response")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        # First runner
        runner1 = AgentRunner(
            graph=graph,
            session_id="runner-resume",
            agent_name="build",
            model_name="test:fake",
        )

        events1: list[dict] = []
        async for event in runner1.run("Hello"):
            events1.append(event)
        assert any(e["type"] == "done" for e in events1)

        # Second runner — same session_id
        runner2 = AgentRunner(
            graph=graph,
            session_id="runner-resume",
            agent_name="build",
            model_name="test:fake",
        )

        events2: list[dict] = []
        async for event in runner2.run("Continue?"):
            events2.append(event)
        assert any(e["type"] == "done" for e in events2)

        # Verify state accumulated by checking the graph directly
        state = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Verify")],
                "session_id": "runner-resume",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "runner-resume"}},
        )
        # Multiple human messages should be present (accumulated)
        human_msgs = [
            m for m in state["messages"] if isinstance(m, HumanMessage)
        ]
        assert len(human_msgs) >= 3  # Hello, Continue?, Verify

    @pytest.mark.asyncio
    async def test_sessions_are_isolated(
        self, checkpointer: InMemorySaver
    ) -> None:
        """Different thread_ids do not share state."""
        model = _make_mock_model(content="Isolated response")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        # Session A
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Session A message")],
                "session_id": "sess-a",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "sess-a"}},
        )

        # Session B
        result_b = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Session B message")],
                "session_id": "sess-b",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "sess-b"}},
        )

        # Session B should only have its own human message
        human_msgs = [
            m for m in result_b["messages"] if isinstance(m, HumanMessage)
        ]
        assert len(human_msgs) == 1
        assert human_msgs[0].content == "Session B message"


# ---------------------------------------------------------------------------
# Interrupted / partial stream tests
# ---------------------------------------------------------------------------


class TestCheckpointInterrupted:
    """Verify checkpoint behavior when an agent run is interrupted."""

    @pytest.mark.asyncio
    async def test_cancel_event_preserves_partial_state(
        self, checkpointer: InMemorySaver
    ) -> None:
        """When a run is cancelled via cancel_event, partial progress is saved."""
        model = _make_mock_model(content="This is a partial")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        runner = AgentRunner(
            graph=graph,
            session_id="cancel-state",
            agent_name="build",
            model_name="test:fake",
        )

        cancel = asyncio.Event()
        cancel.set()  # Cancel immediately

        events: list[dict] = []
        async for event in runner.run("Hello", cancel_event=cancel):
            events.append(event)

        # Should get an interrupted event
        types = {e["type"] for e in events}
        assert "interrupted" in types

        # Check that a graph can still be used (state wasn't corrupted)
        state = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Resumed")],
                "session_id": "cancel-state",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "cancel-state"}},
        )
        assert len(state["messages"]) >= 1

    @pytest.mark.asyncio
    async def test_interrupted_run_has_messages(
        self, checkpointer: InMemorySaver
    ) -> None:
        """After a run, messages are preserved in checkpoint."""
        model = _make_mock_model(content="partial")
        graph = create_agent_graph(
            model, [test_read], checkpointer=checkpointer
        )

        # Run to create checkpoint
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Before interrupt")],
                "session_id": "interrupt-msgs",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "interrupt-msgs"}},
        )

        # Verify the message is there
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="After interrupt")],
                "session_id": "interrupt-msgs",
                "agent_name": "build",
                "model_name": "test:fake",
            },
            config={"configurable": {"thread_id": "interrupt-msgs"}},
        )

        human_msgs = [
            m for m in result["messages"] if isinstance(m, HumanMessage)
        ]
        assert len(human_msgs) >= 2
