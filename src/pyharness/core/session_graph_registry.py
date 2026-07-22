"""Session-scoped agent graph registry.

R2.4: ``SessionGraphRegistry`` caches compiled agent graphs per session so
they are not recreated on every user input.  Each session gets its own graph
with its own checkpoint thread via ``thread_id``.

R2.5: ``invalidate(session_id)`` discards a cached graph when the model or
tools change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver  # noqa: TC001
from langgraph.graph.state import CompiledStateGraph  # noqa: TC001

from pyharness.core.agent import create_agent_graph


@dataclass
class SessionGraphRegistry:
    """Caches compiled agent graphs keyed by session ID.

    The same session always gets the same graph instance so that LangGraph
    checkpointing can associate state with the correct thread.

    Usage::

        registry = SessionGraphRegistry(checkpointer)
        graph = registry.get_or_create("sess-abc", model, tools)
        runner = AgentRunner(graph, "sess-abc", "build", "openai:gpt-5")
    """

    checkpointer: BaseCheckpointSaver | None = None
    _graphs: dict[str, CompiledStateGraph] = field(default_factory=dict)

    def get_or_create(
        self,
        session_id: str,
        model: Any,  # BaseChatModel
        tools: list[BaseTool],
    ) -> CompiledStateGraph:
        """Return the cached graph for *session_id* or create and cache a new one.

        Args:
            session_id: The session ID (used as cache key, NOT as thread_id).
            model: A LangChain ``BaseChatModel`` from the provider bridge.
            tools: Tools available to the agent.

        Returns:
            A compiled agent graph.
        """
        if session_id not in self._graphs:
            self._graphs[session_id] = create_agent_graph(
                model, tools, checkpointer=self.checkpointer
            )
        return self._graphs[session_id]

    def invalidate(self, session_id: str) -> None:
        """Discard the cached graph for *session_id*.

        The next call to ``get_or_create`` for this session will build a
        fresh graph.  This should be called when the model or tool set
        changes for a session.

        Args:
            session_id: The session whose graph should be discarded.
        """
        self._graphs.pop(session_id, None)

    def invalidate_all(self) -> None:
        """Discard all cached graphs."""
        self._graphs.clear()

    def __contains__(self, session_id: str) -> bool:
        """Return ``True`` if *session_id* has a cached graph."""
        return session_id in self._graphs
