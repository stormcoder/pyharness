"""Agent-facing memory tools — MemPalace semantic search & knowledge graph.

These are LangChain ``@tool``-decorated functions that the agent can call
directly to search project memory, store facts, query the knowledge graph,
and interact with agent diaries.

When ``mempalace`` is not installed, every tool returns a graceful
"MemPalace not installed" message instead of raising an error.

Available tools
---------------
- :tool:`mempalace_search` — Semantic search across project memory
- :tool:`mempalace_remember` — Store a fact or decision
- :tool:`mempalace_search_sessions` — Find past sessions by topic
- :tool:`mempalace_diary_read` — Read agent diary entries
- :tool:`mempalace_kg_query` — Query the knowledge graph
- :tool:`mempalace_kg_add` — Add a fact to the knowledge graph

.. rubric:: R3.14-R3.15: Async Tool Safety

All tools are ``async def`` and ``await`` the async ``MemoryStore`` methods
directly.  The previous ``asyncio.run()`` wrappers have been removed to
guarantee safe operation under a running event loop.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Graceful-degradation message
# ---------------------------------------------------------------------------

_MEM_NOT_INSTALLED = (
    "MemPalace not installed. "
    "Install with: `pip install mempalace` or `uv add mempalace`. "
    "Memory tools provide semantic search, knowledge graphs, and agent "
    "diaries for cross-session recall — pyharness's differentiating feature."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store():
    """Lazy-import the memory store singleton."""
    from pyharness.core.memory import get_memory_store

    return get_memory_store()


def _format_results(results: list[dict[str, Any]], max_items: int = 5) -> str:
    """Format search/KG results for display to the agent.

    Args:
        results: List of result dicts.
        max_items: Maximum number of items to include in the output.

    Returns:
        Formatted string.
    """
    if not results:
        return "No results found."

    lines = [f"Found {len(results)} result(s):"]
    for i, r in enumerate(results[:max_items]):
        content = r.get("content", str(r))
        score = r.get("score")
        score_str = f" (score: {score:.3f})" if score is not None else ""
        lines.append(f"\n  [{i + 1}]{score_str} {content[:300]}")
    if len(results) > max_items:
        lines.append(f"\n  ... and {len(results) - max_items} more")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools (all async — R3.14-R3.15)
# ---------------------------------------------------------------------------


@tool
async def mempalace_search(query: str, limit: int = 5) -> str:
    """Search across project memory for past conversations, decisions, and code context.

    Use this to find relevant information from earlier sessions, architectural
    decisions, or agent learnings that are stored in MemPalace.

    Args:
        query: What to search for (natural language).  Be specific — include
            keywords, file names, or function names.
        limit: Maximum number of results to return (default 5).

    Returns:
        Formatted search results or a "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    results = await store.search(query=query, limit=limit)
    return _format_results(results, max_items=limit)


@tool
async def mempalace_remember(fact: str) -> str:
    """Store a fact, decision, or important finding for future recall.

    Use this to record architectural decisions, bug insights, important
    code patterns, or anything that will be useful in future sessions.

    Args:
        fact: The fact or decision to remember.  Be specific and include
            context (e.g. "AuthMiddleware lives in src/auth/middleware.py").

    Returns:
        Confirmation or "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    await store.remember(fact=fact)
    return f"🧠 Stored: {fact[:200]}"


@tool
async def mempalace_search_sessions(topic: str) -> str:
    """Find past sessions by topic or description.

    Use this to discover prior conversations, related debugging sessions,
    or previous work on a topic.

    Args:
        topic: Topic to search for in past sessions.

    Returns:
        Formatted session search results or "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    results = await store.search_sessions(topic=topic, limit=10)
    return _format_results(results, max_items=5)


@tool
async def mempalace_diary_read(agent_name: str = "build") -> str:
    """Read diary entries from a specific agent.

    Diaries contain agent self-reflections, lessons learned, and notes
    written at session boundaries.

    Args:
        agent_name: Which agent's diary to read (build, plan, explore, etc.).
            Default is "build".

    Returns:
        Formatted diary entries or "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    entries = await store.diary_read(agent_name=agent_name, last_n=5)
    if not entries:
        return f"No diary entries found for agent '{agent_name}'."

    lines = [f"Diary entries for '{agent_name}' ({len(entries)} recent):"]
    for i, entry in enumerate(entries):
        content = entry.get("content", entry.get("entry", str(entry)))
        topic = entry.get("topic", "general")
        lines.append(f"\n  [{i + 1}] ({topic}) {content[:300]}")
    return "\n".join(lines)


@tool
async def mempalace_kg_query(entity: str) -> str:
    """Query the knowledge graph for facts about an entity.

    The knowledge graph stores structured facts like "AuthMiddleware located_in
    src/auth/middleware.py" or "error handling uses SentryIntegration".

    Args:
        entity: Entity to query (e.g., "AuthMiddleware", "error handling",
            "database schema").

    Returns:
        Formatted knowledge graph facts or "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    results = await store.kg_query(entity=entity)
    if not results:
        return f"No facts found for '{entity}'."

    lines = [f"Knowledge graph facts for '{entity}':"]
    for i, fact in enumerate(results):
        subj = fact.get("subject", "?")
        pred = fact.get("predicate", "?")
        obj = fact.get("object", "?")
        lines.append(f"  {i + 1}. {subj} → {pred} → {obj}")
    return "\n".join(lines)


@tool
async def mempalace_kg_add(subject: str, predicate: str, obj: str) -> str:
    """Add a fact to the knowledge graph.

    Use this to record structural relationships between code entities,
    architectural constraints, or any verifiable relationship.

    Args:
        subject: The entity (e.g., "AuthMiddleware").
        predicate: The relationship (e.g., "located_in", "uses", "implements").
        obj: The connected entity (e.g., "src/auth/middleware.py").

    Returns:
        Confirmation or "not installed" message.
    """
    from pyharness.core.memory import MEM_PALACE_AVAILABLE

    if not MEM_PALACE_AVAILABLE:
        return _MEM_NOT_INSTALLED

    store = _get_store()
    if not store.initialized:
        return _MEM_NOT_INSTALLED

    result = await store.kg_add(subject=subject, predicate=predicate, obj=obj)
    status = result.get("status", "unknown")
    if status == "ok":
        return f"🧠 Added fact: {subject} → {predicate} → {obj}"
    return f"Failed to add fact: {result.get('reason', status)}"


# ---------------------------------------------------------------------------
# Convenience: list of all memory tools
# ---------------------------------------------------------------------------

ALL_MEMORY_TOOLS: list = [
    mempalace_search,
    mempalace_remember,
    mempalace_search_sessions,
    mempalace_diary_read,
    mempalace_kg_query,
    mempalace_kg_add,
]
