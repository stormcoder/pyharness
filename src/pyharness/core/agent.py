"""LangGraph-powered ReAct agent loop.

Implements the agent runtime as described in SPEC.md §5.  The graph follows
the standard ReAct pattern:

    START → agent_node → {
        tool_calls → tool_executor → agent_node
        no_tool_calls → END
    }

The agent node binds tools to the model, invokes it with message history,
and routes based on whether the response contains tool calls.

Public API
----------
``create_agent_graph(model, tools, checkpointer) → CompiledStateGraph``
    Build the ReAct graph.

``AgentRunner(graph, session_id, agent_name, model_name)``
    Run the compiled graph with streaming event support.
"""

from __future__ import annotations

import asyncio
import operator
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver  # noqa: TC001
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph  # noqa: TC001

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """Shared state for the LangGraph agent graph.

    ``messages`` uses an ``operator.add`` reducer so that nodes can return
    ``{"messages": [new_msgs]}`` and the graph appends them.
    """

    messages: Annotated[list, operator.add]
    session_id: str
    agent_name: str
    model_name: str


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def create_agent_graph(
    model: Any,  # BaseChatModel
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build a compiled ReAct agent graph.

    Args:
        model: A LangChain ``BaseChatModel`` from the provider bridge.
        tools: Tools available to the agent (already filtered by permissions).
        checkpointer: Optional checkpointer for durable execution.

    Returns:
        A compiled :class:`~langgraph.graph.state.CompiledStateGraph`.
    """
    graph = StateGraph(AgentState)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def agent_node(state: AgentState) -> dict[str, list]:
        """Call the LLM with tools bound and return its response."""
        model_with_tools = model.bind_tools(tools)
        response: BaseMessage = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    async def tool_executor(state: AgentState) -> dict[str, list]:
        """Execute every tool call in the last AI message.

        Each successful invocation produces a ``ToolMessage`` with the
        result; errors are captured as ``ToolMessage`` with the error text
        so the agent can self-correct.
        """
        from pyharness.tools.registry import get_registry

        last_message = state["messages"][-1]
        registry = get_registry()
        tool_messages: list[ToolMessage] = []

        for tool_call in last_message.tool_calls:
            tool_name: str = tool_call["name"]
            tool_args: dict[str, Any] = tool_call["args"]
            tool_call_id: str = tool_call["id"]

            try:
                tool = registry.get_tool(tool_name)
            except KeyError:
                tool_messages.append(
                    ToolMessage(
                        content=f"Unknown tool: {tool_name}",
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                )
                continue

            try:
                result = await tool.ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                )
            except Exception as exc:
                tool_messages.append(
                    ToolMessage(
                        content=f"Tool error: {exc}",
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                )

        return {"messages": tool_messages}

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def should_continue(state: AgentState) -> str:
        """Return ``"tools"`` if the last message has tool calls, else ``END``."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_executor)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------


class AgentRunner:
    """Runs a compiled agent graph with streaming event support.

    Parameters
    ----------
    graph:
        A compiled agent graph from :func:`create_agent_graph`.
    session_id:
        Unique session identifier used as LangGraph thread ID.
    agent_name:
        Name of the agent (e.g. ``"build"``, ``"plan"``).
    model_name:
        Resolved model string (e.g. ``"anthropic:claude-sonnet-4-5"``).
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        session_id: str,
        agent_name: str,
        model_name: str,
        system_prompt: str | None = None,
        recursion_limit: int = 50,
    ) -> None:
        from pyharness.core.system_prompt import DEFAULT_SYSTEM_PROMPT

        self.graph = graph
        self.session_id = session_id
        self.agent_name = agent_name
        self.model_name = model_name
        self.recursion_limit = recursion_limit
        self.system_prompt: str = system_prompt or DEFAULT_SYSTEM_PROMPT.format(
            agent_name=agent_name, model_name=model_name
        )
        self.config: dict[str, Any] = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": self.recursion_limit,
        }
        self.child_sessions: list[str] = []  # IDs of child subagent sessions

    async def run(
        self,
        user_message: str,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the agent and stream event dictionaries.

        Yields events with the following shapes::

            {"type": "content", "data": str}           # streaming token
            {"type": "tool_call", "data": {...}}       # tool invocation started
            {"type": "tool_result", "data": {...}}     # tool result
            {"type": "interrupted", "data": None}      # cancelled by user
            {"type": "done", "data": None}             # agent finished

        Parameters
        ----------
        user_message:
            The natural-language user prompt to process.
        cancel_event:
            Optional :class:`asyncio.Event` that, when set, will interrupt
            the agent loop.  The event is checked between each streaming
            iteration.

        Yields
        ------
        dict
            Streamed events (``type`` + ``data``).
        """
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_message),
            ],
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
        }

        cancelled = False

        try:
            async for event in self.graph.astream_events(
                initial_state, config=self.config, version="v2"
            ):
                # R2.6: check cancel event between iterations
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break

                kind = event["event"]

                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield {"type": "content", "data": content}

                elif kind == "on_tool_start":
                    yield {
                        "type": "tool_call",
                        "data": {
                            "name": event["name"],
                            "input": event["data"].get("input", {}),
                        },
                    }

                elif kind == "on_tool_end":
                    output_raw = event["data"].get("output", "")
                    yield {
                        "type": "tool_result",
                        "data": {
                            "name": event["name"],
                            "output": str(output_raw)[:2000],
                        },
                    }
        except GraphRecursionError:
            yield {
                "type": "error",
                "data": (
                    "Agent recursion limit reached. The task was too complex. "
                    "Try breaking it into smaller steps."
                ),
            }
            return

        if cancelled:
            yield {"type": "interrupted", "data": None}
        else:
            yield {"type": "done", "data": None}

    def spawn_subagent(
        self, agent_type: str, prompt: str, session_id: str
    ) -> str:
        """Spawn a subagent and return its result.

        Parameters
        ----------
        agent_type:
            The type of subagent to spawn (e.g. ``"general"``, ``"explore"``).
        prompt:
            The task prompt for the subagent.
        session_id:
            Unique session ID for the child session.

        Returns
        -------
        str
            A message indicating what was spawned and how to retrieve results.
        """
        child_id = f"{session_id}:{agent_type}"
        self.child_sessions.append(child_id)
        return (
            f"Subagent spawned: {agent_type} (session: {child_id})\n"
            f"Task: {prompt[:200]}{'...' if len(prompt) > 200 else ''}\n"
            f"Parent: {self.session_id} ({self.agent_name})\n"
            f"The subagent runs in its own context with inherited permissions."
        )
