"""Session browser screen — lists recent and archived sessions.

Phase 2: Functional stub showing static content.  Full SQLite-backed
session listing with search and filtering lands in Phase 3.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Static


class SessionBrowser(Screen):
    """Session browser displaying recent and archived chat sessions.

    Planned layout::

        ┌──────────────────────────────────────────┐
        │  Session Browser                    [X]   │
        │──────────────────────────────────────────│
        │  Search: [__________________]             │
        │                                           │
        │  📁 2024-01-15 — Fix auth middleware       │
        │  📁 2024-01-14 — Add session storage       │
        │  📁 2024-01-13 — TUI chat screen setup     │
        │                                           │
        │  [New Session]  [Open]  [Delete]  [Export] │
        └──────────────────────────────────────────┘
    """

    def compose(self) -> ComposeResult:
        with Container(id="sessions-container"):
            yield Static(
                "[bold #58a6ff]\U0001f4c1 Session Browser[/]\n\n"
                "[#8b949e]Session browsing will be available in Phase 3.[/]",
                id="sessions-content",
            )
