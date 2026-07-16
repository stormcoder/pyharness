"""Widget for rendering chat messages with tool calls and image attachments.

Used for user, assistant, tool, error, image, and system messages in the
chat area.  Image display uses placeholder text — full terminal image
protocol support (Kitty/iTerm2) is deferred to post-v1.0.
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
    "image": "#ffa657",
}


class MessageWidget(Static):
    """Renders a single chat message with role-based colour.

    Supports user, assistant, tool, error, and image roles.  Image
    messages are displayed as placeholders — full terminal image
    protocol (Kitty/iTerm2) support is deferred to post-v1.0.

    Usage::

        yield MessageWidget("user", "What is the git status?")
        yield MessageWidget("assistant", "Let me check that for you...")
        yield MessageWidget("tool", "bash: git status\\nOn branch main")
        yield MessageWidget("error", "Command failed with exit code 1")
        yield MessageWidget("image", "screenshot.png")
    """

    def __init__(self, role: str, content: str, **kwargs: object) -> None:
        color = ROLE_COLORS.get(role, "#c9d1d9")
        if role == "image":
            display = f"[bold {color}]📷 Image:[/] {content}"
        else:
            display = f"[bold {color}]{role.title()}:[/] {content}"
        super().__init__(display, **kwargs)


class ImageAttachment(Static):
    """Placeholder widget for image attachments.

    Full image rendering via terminal image protocol (Kitty/iTerm2)
    is deferred to post-v1.0.
    """

    def __init__(
        self, file_path: str, alt_text: str = "", **kwargs: object
    ) -> None:
        self.file_path = file_path
        self.alt_text = alt_text
        display = (
            f"[bold #ffa657]📷 Image: {file_path}[/]\n"
            f"[#8b949e]Alt: {alt_text or '(none)'}[/]\n"
            f"[#8b949e]Image display requires Kitty/iTerm2 terminal protocol. "
            f"Full support deferred to post-v1.0.[/]"
        )
        super().__init__(display, **kwargs)


class ChatMessage:
    """Factory for creating chat message widgets."""

    @staticmethod
    def user(text: str) -> MessageWidget:
        """Create a user message widget."""
        return MessageWidget("user", text)

    @staticmethod
    def assistant(text: str) -> MessageWidget:
        """Create an assistant message widget."""
        return MessageWidget("assistant", text)

    @staticmethod
    def tool(name: str, result: str) -> MessageWidget:
        """Create a tool result message widget."""
        return MessageWidget("tool", f"[{name}] {result}")

    @staticmethod
    def image(file_path: str, alt_text: str = "") -> ImageAttachment:
        """Create an image attachment placeholder."""
        return ImageAttachment(file_path, alt_text=alt_text)
