"""MemPalace integration — semantic memory with graceful degradation.

MemPalace is pyharness's differentiating feature: no other terminal coding
agent has semantic memory.  When ``mempalace`` is installed, the agent can
search project memory, store facts, query the knowledge graph, and read/write
agent diaries.  When it isn't, every operation returns sensible defaults with
zero startup delay and zero extra dependencies.

Usage::

    from pyharness.core.memory import get_memory_store

    store = get_memory_store("pyharness", config)
    await store.initialize()
    ctx = await store.wake_up("fix session storage bug")

Architecture
------------
- Wing = Project scope (``mike/pyharness``)
- Room = Topic (``sessions``, ``decisions``, ``architecture``)
- Drawer = Individual content unit
- Knowledge Graph = Structured facts
- Diary = Per-agent learnings written at session boundaries
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pyharness.core.logging import get_logger

if TYPE_CHECKING:
    from pyharness.config.schema import MemoryConfig

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level import check — executed once at import time
# ---------------------------------------------------------------------------

MEM_PALACE_AVAILABLE = importlib.util.find_spec("mempalace") is not None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemorySearchResult:
    """A single result from semantic search."""

    content: str
    score: float
    wing: str = ""
    room: str = ""
    drawer_id: str = ""


@dataclass
class WakeUpContext:
    """Context loaded at session start.

    On wake-up, pyharness queries the knowledge graph, searches for related
    past sessions, and loads recent agent diary entries into a structured
    context that is injected as a system preamble.
    """

    related_sessions: list[MemorySearchResult] = field(default_factory=list)
    kg_facts: list[dict[str, Any]] = field(default_factory=list)
    diary_entries: list[dict[str, Any]] = field(default_factory=list)
    briefing: str = ""

    def to_system_preamble(self) -> str:
        """Convert wake-up context to a system preamble string.

        Returns a Markdown-formatted string suitable for injection into the
        agent's system message.  When no context is available, returns an
        empty string.
        """
        parts: list[str] = []

        if self.kg_facts:
            parts.append("## Knowledge Graph Facts\n")
            for fact in self.kg_facts:
                subj = fact.get("subject", "?")
                pred = fact.get("predicate", "?")
                obj = fact.get("object", "?")
                parts.append(f"- {subj} → {pred} → {obj}")

        if self.related_sessions:
            parts.append("\n## Related Past Sessions\n")
            for s in self.related_sessions[:3]:
                parts.append(f"- {s.content[:200]}")

        if self.diary_entries:
            parts.append("\n## Agent Diary\n")
            for entry in self.diary_entries[:3]:
                parts.append(f"- {entry.get('content', '')[:200]}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """Wrapper around MemPalace.  Gracefully degrades when not installed.

    Every public method returns sensible defaults when ``mempalace`` is not
    available — there is no need for callers to check ``.available`` before
    every call (though they may for performance).

    Parameters:
        config: Memory configuration from the project's ``pyharness.json``.
        project_name: Project identifier used as the MemPalace wing name.
    """

    def __init__(self, config: MemoryConfig, project_name: str = "pyharness") -> None:
        self.config = config
        self.project_name = project_name
        self._palace: Any = None
        self._initialized = False

    # -- properties -----------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether MemPalace is importable."""
        return MEM_PALACE_AVAILABLE

    @property
    def initialized(self) -> bool:
        """Whether the underlying MemPalace has been successfully initialized."""
        return self._initialized

    # -- lifecycle ------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize the memory store.

        No-op when MemPalace is not installed.  When MemPalace *is* installed
        but initialization fails (e.g. database corruption), the error is
        logged and the store remains in the uninitialized state — callers
        will receive graceful defaults.
        """
        if not self.available:
            logger.info("memory.unavailable", reason="mempalace not installed")
            return
        if self._initialized:
            return

        try:
            from mempalace import MemPalace  # noqa: PLC0415

            self._palace = MemPalace()
            self._initialized = True
            logger.info("memory.initialized", wing=self.config.wing)
        except Exception:
            logger.exception(
                "memory.init_failed",
                wing=self.config.wing,
            )
            self._initialized = False

    async def close(self) -> None:
        """Clean up resources.  Currently a no-op placeholder."""
        pass

    # -- wake-up --------------------------------------------------------------

    async def wake_up(self, query: str = "") -> WakeUpContext:
        """Load context for a new session.

        Queries the knowledge graph, searches for related past sessions, and
        reads agent diary entries.  Returns an empty :class:`WakeUpContext`
        when MemPalace is not available.

        Args:
            query: Optional search string (e.g. the user's first message).
        """
        if not self._ready():
            logger.info("memory.wake_up_skipped", reason="not available")
            return WakeUpContext(briefing="(MemPalace not installed)")

        ctx = WakeUpContext()
        try:
            # Semantic search
            results = await self.search(
                query, limit=self.config.wake_up.max_results
            )
            ctx.related_sessions = [
                MemorySearchResult(
                    content=r.get("content", ""),
                    score=r.get("score", 0.0),
                    wing=r.get("wing", ""),
                    room=r.get("room", ""),
                    drawer_id=r.get("drawer_id", ""),
                )
                for r in results
            ]

            # Knowledge graph facts
            if self.config.wake_up.include_kg:
                ctx.kg_facts = await self._kg_query_all()

            # Agent diary entries
            if self.config.wake_up.include_diary:
                ctx.diary_entries = await self._diary_read()

            # Compose briefing
            n_sessions = len(ctx.related_sessions)
            n_facts = len(ctx.kg_facts)
            prefix = "\U0001f9e0"  # 🧠

            if n_sessions:
                ctx.briefing = (
                    f"{prefix} Loaded {n_sessions} related past discussions "
                    f"and {n_facts} knowledge graph facts."
                )
            elif n_facts:
                ctx.briefing = (
                    f"{prefix} {n_facts} knowledge graph facts loaded."
                )
            else:
                ctx.briefing = (
                    f"{prefix} Ready — nothing relevant found in memory."
                )
        except Exception:
            logger.exception("memory.wake_up_failed")

        return ctx

    # -- semantic search ------------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Semantic search across project memory.

        Args:
            query: Natural-language search query (max 250 chars).
            limit: Maximum number of results to return.

        Returns:
            List of result dicts with keys ``content``, ``score``, ``wing``,
            ``room``, and ``drawer_id``.  Returns an empty list when
            MemPalace is unavailable or the search fails.
        """
        if not self._ready():
            return []

        try:
            # Call the actual MemPalace search method.
            # MemPalace's API expects keyword args: query, wing, limit.
            results = self._palace.search(
                query=query[:250],
                wing=self.config.wing,
                limit=limit,
            )
            return results if results else []
        except Exception:
            logger.exception("memory.search_failed")
            return []

    # -- indexing -------------------------------------------------------------

    async def index(self, content: str, room: str = "sessions") -> None:
        """Index content into the palace.

        Args:
            content: Verbatim content to store.
            room: Topic room (default ``"sessions"``).
        """
        if not self._ready():
            return

        try:
            self._palace.add_drawer(
                wing=self.config.wing,
                room=room,
                content=content,
            )
            logger.debug("memory.indexed", room=room, content_len=len(content))
        except Exception:
            logger.exception("memory.index_failed")

    async def remember(self, fact: str, room: str = "decisions") -> None:
        """Store a decision or fact.

        Convenience wrapper around :meth:`index` with a ``decisions`` room
        default.

        Args:
            fact: The fact or decision to remember.
            room: Topic room (default ``"decisions"``).
        """
        await self.index(content=fact, room=room)

    # -- agent diary ----------------------------------------------------------

    async def diary_write(
        self, agent_name: str, entry: str, topic: str = "general"
    ) -> None:
        """Write to an agent's diary.

        Args:
            agent_name: Name of the agent (e.g. ``"build"``, ``"plan"``).
            entry: Diary entry content in AAAK format.
            topic: Topic tag (default ``"general"``).
        """
        if not self._ready():
            return

        try:
            self._palace.diary_write(
                agent_name=agent_name,
                entry=entry,
                wing=self.config.wing,
            )
        except Exception:
            logger.exception("memory.diary_write_failed")

    async def diary_read(
        self, agent_name: str = "build", last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Read recent diary entries for an agent.

        Args:
            agent_name: Which agent's diary to read.
            last_n: Maximum number of recent entries.

        Returns:
            List of diary entry dicts.
        """
        if not self._ready():
            return []

        try:
            entries = self._palace.diary_read(
                agent_name=agent_name,
                last_n=last_n,
                wing=self.config.wing,
            )
            return entries if entries else []
        except Exception:
            logger.exception("memory.diary_read_failed")
            return []

    # -- knowledge graph ------------------------------------------------------

    async def kg_query(self, entity: str) -> list[dict[str, Any]]:
        """Query the knowledge graph for facts about an entity.

        Args:
            entity: Entity to query (e.g. ``"AuthMiddleware"``,
                ``"error handling"``).

        Returns:
            List of fact dicts with ``subject``, ``predicate``, ``object``
            keys.
        """
        if not self._ready():
            return []

        try:
            results = self._palace.kg_query(entity=entity)
            return results if results else []
        except Exception:
            logger.exception("memory.kg_query_failed")
            return []

    async def kg_add(
        self, subject: str, predicate: str, obj: str
    ) -> dict[str, Any]:
        """Add a fact to the knowledge graph.

        Args:
            subject: The entity (e.g. ``"AuthMiddleware"``).
            predicate: The relationship (e.g. ``"located_in"``).
            obj: The connected entity (e.g. ``"src/auth/middleware.py"``).
        """
        if not self._ready():
            return {"status": "unavailable", "reason": "MemPalace not installed"}

        try:
            result = self._palace.kg_add(
                subject=subject,
                predicate=predicate,
                object=obj,
            )
            return result if isinstance(result, dict) else {"status": "ok"}
        except Exception:
            logger.exception("memory.kg_add_failed")
            return {"status": "error"}

    # -- session search -------------------------------------------------------

    async def search_sessions(self, topic: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find past sessions by topic.

        Args:
            topic: Topic to search for in past sessions.
            limit: Maximum number of results.

        Returns:
            List of session result dicts.
        """
        return await self.search(query=topic, limit=limit)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ready(self) -> bool:
        """Check whether the store is ready for operations."""
        return self.available and self._initialized

    async def _kg_query_all(self) -> list[dict[str, Any]]:
        """Get all KG facts for this project.

        This is a placeholder — the actual MemPalace API does not expose
        a "query all facts" endpoint, but future versions may.  Returns an
        empty list until that API is available.
        """
        return []

    async def _diary_read(self) -> list[dict[str, Any]]:
        """Read recent diary entries (all agents).

        Reads the ``build`` agent diary as the primary source of project
        context.
        """
        return await self.diary_read(agent_name="build", last_n=5)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_memory_store: MemoryStore | None = None


def get_memory_store(
    project_name: str = "pyharness",
    config: MemoryConfig | None = None,
) -> MemoryStore:
    """Return the global :class:`MemoryStore` singleton, creating it if needed.

    Args:
        project_name: Wing name for MemPalace.
        config: Memory configuration.  If ``None``, a default
            :class:`~pyharness.config.schema.MemoryConfig` is created.

    Returns:
        The singleton :class:`MemoryStore` instance.
    """
    global _memory_store

    if _memory_store is None:
        if config is None:
            from pyharness.config.schema import MemoryConfig

            config = MemoryConfig(
                wing=f"{{{project_name}}}",
            )
        _memory_store = MemoryStore(config=config, project_name=project_name)

    return _memory_store


def reset_memory_store() -> None:
    """Reset the global memory store singleton (for testing)."""
    global _memory_store
    _memory_store = None


# Backward-compatible alias — SPEC §14 Phase 2 references ``MemoryManager``
MemoryManager = MemoryStore
