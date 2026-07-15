"""Widget for rendering chat messages with role-based coloring.

Used for user, assistant, tool, and error messages in the chat area.
"""

from __future__ import annotations

from textual.widgets import Static

# Role → ANSI hex color mapping (GitHub dark theme)
ROLE_COLORS: dict[str, str] = {
    "user": "#58a6ff",
    "assistant": "#7ee787",
    "tool": "#d2a8ff",
    "error": "#f85149",
    "system": "#8b949e",
}


class MessageWidget(Static):
    """Renders a single chat message with role-based colour.

    Usage:
        yield MessageWidget("user", "What is the git status?")
        yield MessageWidget("assistant", "Let me check that for you...")
        yield MessageWidget("tool", "bash: git status\nOn branch main")
        yield MessageWidget("error", "Command failed with exit code 1")
    """

    def __init__(self, role: str, content: str, **kwargs: object) -> None:
        color = ROLE_COLORS.get(role, "#c9d1d9")
        super().__init__(
            f"[bold {color}]{role.title()}:[/] {content}",
            **kwargs,
        )
