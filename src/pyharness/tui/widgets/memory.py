"""Memory tab widget — MemPalace memory browser in the sidebar.

Implements SPEC §6.5: the sidebar's 4th tab showing knowledge graph facts,
related past sessions, agent diary preview, and quick-actions for memory
operations.

When MemPalace is not installed, the tab shows an installation prompt.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class MemoryTab(Static):
    """Memory tab showing KG facts, related sessions, and diary.

    This widget lives in the sidebar as the 🧠 Memory tab.  It displays
    knowledge graph facts, related past sessions, and agent diary entries.
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "🧠 Knowledge Graph",
            classes="section-title",
        )
        yield Static(
            "(MemPalace not installed — run `pip install mempalace` "
            "to enable semantic memory)",
            id="kg-content",
            classes="placeholder",
        )
        yield Static(
            "📋 Related Sessions",
            classes="section-title",
        )
        yield Static(
            "No related sessions found.",
            id="related-content",
            classes="placeholder",
        )
        yield Static(
            "📝 Agent Diary",
            classes="section-title",
        )
        yield Static(
            "Session learnings will appear here.",
            id="diary-content",
            classes="placeholder",
        )

    def update_kg_facts(self, facts: list[str]) -> None:
        """Replace the knowledge graph content with live facts.

        Args:
            facts: Human-readable fact strings (e.g. ``"AuthMiddleware → "
                "located_in → src/auth/middleware.py"``).
        """
        if not facts:
            return
        kg = self.query_one("#kg-content", Static)
        if not facts:
            kg.update("No knowledge graph facts recorded yet.")
        else:
            kg.update("\n".join(f"• {f}" for f in facts))

    def update_related_sessions(self, sessions: list[str]) -> None:
        """Replace the related-sessions content.

        Args:
            sessions: Session summaries or titles, most relevant first.
        """
        related = self.query_one("#related-content", Static)
        if not sessions:
            related.update("No related sessions found.")
        else:
            related.update("\n".join(f"• {s}" for s in sessions[:5]))

    async def refresh_memory(self) -> None:
        """Refresh the memory display from MemPalace.

        Called after tool executions that modify the knowledge graph or
        index new content.  No-op when MemPalace is not installed.
        """

    def update_diary(self, entries: list[str]) -> None:
        """Replace the agent diary content.

        Args:
            entries: Recent diary entries, one per agent.
        """
        diary = self.query_one("#diary-content", Static)
        if not entries:
            diary.update("Session learnings will appear here.")
        else:
            diary.update("\n\n".join(entries[:5]))
