"""Session briefing widget — shown on startup to summarize project context.

Phase 2: Displays a brief summary of what was learned last session,
knowledge graph highlights, and related past work.
"""

from __future__ import annotations

from textual.widgets import Static


class SessionBriefing(Static):
    """Briefing widget shown at session start.

    Reads the wake-up context from :class:`~pyharness.core.memory.WakeUpContext`
    and displays a concise summary of project memory — related sessions,
    knowledge graph highlights, and agent diary notes.

    When MemPalace is not installed, shows a graceful-degradation message.
    """

    def on_mount(self) -> None:
        """Display an initial briefing (placeholder in Phase 2)."""
        self.update(
            "[bold #7ee787]\u2728 Ready[/]\n\n"
            "[#8b949e]Session briefing with memory context "
            "will appear here (Phase 2+).[/]"
        )

    def set_briefing(self, briefing_text: str) -> None:
        """Update the briefing with actual memory context.

        Args:
            briefing_text: The formatted briefing string to display.
        """
        self.update(briefing_text)
