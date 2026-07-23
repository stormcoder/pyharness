"""Session-to-Markdown export.

Produces a self-contained Markdown file from a :class:`Session`
with all messages, tool calls, metadata, and session stats in
OpenCode-style format with inline bold labels and nested tool messages.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pyharness.core.session import Message, Session

# ---------------------------------------------------------------------------
# Rich markup stripping
# ---------------------------------------------------------------------------

# Match a Rich tag: [tag_name optional=value]...[/] or [/tag_name]
_RICH_TAG_RE = re.compile(
    r"\[/?(?:bold(?: +" + re.escape("#") + r"[0-9a-fA-F]{3,8})?|italic|i|dim|"
    + re.escape("#") + r"[0-9a-fA-F]{3,8}(?: +on +"
    + re.escape("#") + r"[0-9a-fA-F]{3,8})?|/"
    r")\]"
)


def _strip_rich_markup(text: str) -> str:
    """Remove Rich Textual markup tags like ``[bold #58a6ff]...[/]``.

    Keeps the inner text content, only stripping the tags themselves.
    Also handles ``[bold #hex on #hex]`` patterns.
    """
    return _RICH_TAG_RE.sub("", text)


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def format_message(message: Message) -> str:
    """Format a single :class:`Message` as a markdown section.

    Role mapping (OpenCode-style):
        * ``user`` → ``## User`` heading (no timestamp)
        * ``assistant`` → ``## Assistant`` heading (no timestamp)
        * ``tool`` → ``**Tool: {name}**`` block with ``**Input:**``
          and ``**Output:**`` sections (nested; no ``## Tool`` heading)

    Rich markup is stripped from content before writing.
    Per-message timestamps are NOT included — only the session header
    has ``**Created:**`` and ``**Updated:**``.
    """
    content = _strip_rich_markup(message.content)

    if message.role == "user":
        return _format_section(heading="User", content=content)

    elif message.role == "assistant":
        return _format_section(heading="Assistant", content=content)

    elif message.role == "tool":
        tool_name = message.tool_name or "unknown"
        lines: list[str] = [f"**Tool: {tool_name}**"]
        if message.tool_args:
            args_text = json.dumps(message.tool_args, indent=2)
            lines.append("**Input:**")
            lines.append("```json")
            lines.append(args_text)
            lines.append("```")
        result_text = _strip_rich_markup(message.tool_result or "")
        if result_text:
            lines.append("**Output:**")
            lines.append("```")
            lines.append(result_text)
            lines.append("```")
        lines.append("")
        return "\n".join(lines)

    else:
        heading = message.role.capitalize()
        return _format_section(heading=heading, content=content)


def _format_section(heading: str, content: str) -> str:
    """Build a markdown section with heading and content (no timestamp)."""
    lines: list[str] = [f"## {heading}", ""]
    if content:
        lines.append(content)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session metadata header (OpenCode-style inline bold labels)
# ---------------------------------------------------------------------------


def _build_metadata_header(session: Session) -> str:
    """Produce session metadata as inline **Label:** value lines."""
    msg_count = len(session.messages)
    return (
        f"**Session ID:** {session.id}\n"
        f"**Model:** {session.model or 'N/A'}\n"
        f"**Agent:** {session.agent}\n"
        f"**Created:** {session.created_at}\n"
        f"**Updated:** {session.updated_at}\n"
        f"**Messages:** {msg_count}\n"
        f"**Total Tokens:** {session.total_tokens}"
    )


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


def export_session_to_markdown(
    session: Session, output_path: Path | None = None
) -> Path:
    """Export a session and its messages to a Markdown file.

    Args:
        session: The :class:`Session` object with ``.messages`` populated.
        output_path: Output file path. If ``None``, auto-derives from
            session id using the pattern
            ``./pyharness_session_{session_id}.md`` in the current
            working directory.

    Returns:
        Path to the written file.
    """
    if output_path is None:
        output_path = Path.cwd() / f"pyharness_session_{session.id}.md"

    lines: list[str] = []
    lines.append(f"# {session.title}")
    lines.append("")
    lines.append(_build_metadata_header(session))
    lines.append("")

    for message in session.messages:
        if message.role != "tool":
            lines.append("---")
        formatted = format_message(message)
        lines.append(formatted)

    content = "\n".join(lines) + "\n"
    output_path.write_text(content)
    return output_path
