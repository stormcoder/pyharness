"""Session browser — list sessions with memory badges."""
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import ListItem, ListView, Static


class SessionBrowser(Screen):
    """Browse and resume active/archived sessions.

    Memory badges (🧠) appear next to sessions that have MemPalace data.
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("enter", "resume", "Resume"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="session-browser"):
            yield Static("[bold #58a6ff]Sessions[/]", id="sb-title")
            yield Static(
                "[#8b949e]Active sessions will appear here. "
                "Sessions gain \U0001f9e0 memory badges when MemPalace data exists.[/]",
                id="sb-status",
            )
            yield ListView(
                ListItem(Static("[#8b949e]No saved sessions yet[/]")),
                id="sb-list",
            )

    def action_dismiss(self) -> None:
        self.dismiss()

    def action_resume(self) -> None:
        self.dismiss()
