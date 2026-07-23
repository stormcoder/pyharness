"""Tests for session-to-markdown export — OpenCode-style format.

TDD red phase — the ``export_session_to_markdown`` function uses the
OLD ``| Field | Value |`` table format.  These tests require the NEW
OpenCode-style format with inline bold labels (``**Label:** value``).

See ``session-ses_09dc.md`` for the reference format.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pyharness.core.session import Message, Session


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_session(**overrides: object) -> Session:
    """Create a Session with sensible defaults."""
    kwargs: dict = {
        "id": "sess-abc123",
        "title": "Test Session",
        "project": "/home/user/myproject",
        "model": "anthropic:claude-sonnet-4-5",
        "agent": "build",
        "created_at": "2026-07-20T12:00:00+00:00",
        "updated_at": "2026-07-20T12:05:00+00:00",
        "status": "active",
        "git_branch": "feature/export-cmd",
        "total_tokens": 1500,
    }
    kwargs.update(overrides)
    return Session(**kwargs)


def _make_message(**overrides: object) -> Message:
    """Create a Message with sensible defaults."""
    kwargs: dict = {
        "id": "msg-001",
        "role": "user",
        "content": "Hello, pyharness!",
        "timestamp": "2026-07-20T12:00:30+00:00",
        "token_count": 0,
    }
    kwargs.update(overrides)
    return Message(**kwargs)


# ---------------------------------------------------------------------------
# Import guard — the function must exist
# ---------------------------------------------------------------------------


def test_export_function_can_be_imported() -> None:
    """The ``export_session_to_markdown`` function must be importable."""
    from pyharness.core.session_export import export_session_to_markdown

    assert callable(export_session_to_markdown)


# ===========================================================================
# NEW FORMAT TESTS — OpenCode-style (FAILING until format is updated)
# ===========================================================================


class TestOpenCodeHeaderFormat:
    """The markdown header must use inline bold labels, NOT a table."""

    def test_header_uses_inline_bold_labels_not_table(self) -> None:
        """Header must use ``**Label:** value``, NOT ``| Field | Value |`` table.

        See ``session-ses_09dc.md`` for the reference format.
        """
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        # Old format (table) must NOT be present
        assert "| Field | Value |" not in content, (
            "Export must NOT use markdown table format — use **Label:** value"
        )
        assert "|-------|" not in content, (
            "Export must NOT contain table separator row"
        )

        # New format (inline bold) must be present
        assert "**Session ID:**" in content, (
            "Export must use **Session ID:** inline label"
        )
        assert "**Model:**" in content, (
            "Export must use **Model:** inline label"
        )
        assert "**Agent:**" in content, (
            "Export must use **Agent:** inline label"
        )
        assert "**Created:**" in content, (
            "Export must use **Created:** inline label"
        )

    def test_metadata_includes_messages_count(self) -> None:
        """The header must show ``**Messages:** N``."""
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(id="msg-1", role="user", content="Q1"),
            _make_message(id="msg-2", role="assistant", content="A1"),
            _make_message(id="msg-3", role="user", content="Q2"),
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()
        assert re.search(r"\*\*Messages:\*\*\s*3", content), (
            "Export must show **Messages:** 3"
        )

    def test_metadata_includes_total_tokens(self) -> None:
        """The header must show ``**Total Tokens:** N``."""
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session(total_tokens=2500)
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()
        assert re.search(r"\*\*Total Tokens:\*\*\s*2500", content), (
            "Export must show **Total Tokens:** 2500"
        )


class TestOpenCodeMessageFormat:
    """Message formatting must match OpenCode style."""

    def test_user_messages_use_h2_user_heading(self) -> None:
        """User messages use ``## User`` heading."""
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(role="user", content="Write a hello-world script.")
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        assert "## User" in content, (
            "User messages must use '## User' heading"
        )

    def test_assistant_messages_use_h2_assistant_heading(self) -> None:
        """Assistant messages use ``## Assistant`` heading."""
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(
                role="assistant",
                content="Here is your script:\n\n```python\nprint('hello')\n```",
            )
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        assert "## Assistant" in content, (
            "Assistant messages must use '## Assistant' heading"
        )

    def test_tool_messages_are_nested_under_assistant(self) -> None:
        """Tool calls use ``**Tool: name**``, ``**Input:**``, ``**Output:**``
        blocks rather than a separate ``## Tool`` heading section.
        """
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(
                role="tool",
                content="",
                tool_name="read",
                tool_args={"filePath": "/foo/bar.py"},
                tool_result="def main(): pass",
            )
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        # Must use **Tool: name** format
        assert "**Tool: read**" in content, (
            "Tool messages must use '**Tool: read**' format"
        )
        assert "**Input:**" in content, (
            "Tool messages must show '**Input:**' block"
        )
        assert "**Output:**" in content, (
            "Tool messages must show '**Output:**' block"
        )
        assert "/foo/bar.py" in content, (
            "Tool args must appear in input block"
        )
        assert "def main(): pass" in content, (
            "Tool result must appear in output block"
        )

    def test_no_per_message_timestamps(self) -> None:
        """OpenCode format does NOT include timestamps on each message.

        Only the session header has **Created:** and **Updated:**.
        """
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(
                role="user",
                content="Hello",
                timestamp="2026-07-20T12:01:00+00:00",
            ),
            _make_message(
                role="assistant",
                content="Hi there!",
                timestamp="2026-07-20T12:01:05+00:00",
            ),
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        # The message body content should not have timestamps
        # (only the header metadata has dates)
        # Check that after "---" separator, message sections don't contain ISO timestamps
        sections = content.split("---")
        for section in sections[1:]:  # skip header
            # Each message section should not have its own timestamp
            assert "2026-07-20T" not in section, (
                f"Per-message timestamps must not appear in export: {section[:100]}"
            )

    def test_message_sections_separated_by_horizontal_rule(self) -> None:
        """Message sections are separated by ``---``."""
        from pyharness.core.session_export import export_session_to_markdown

        session = _make_session()
        session.messages = [
            _make_message(role="user", content="Q1"),
            _make_message(role="assistant", content="A1"),
        ]
        result_path = export_session_to_markdown(session)
        content = result_path.read_text()

        separator_count = content.count("---")
        assert separator_count >= 2, (
            "Export must separate messages with '---' horizontal rules"
        )


# ===========================================================================
# Existing tests (updated assertions for new format)
# ===========================================================================


def test_export_empty_session() -> None:
    """Session with no messages should produce a title-based header."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    result_path = export_session_to_markdown(session)

    assert isinstance(result_path, Path)
    content = result_path.read_text()
    assert "# Test Session" in content, (
        "Title must be the h1 heading"
    )
    assert "sess-abc123" in content, (
        "Session ID must appear"
    )


def test_export_single_user_message() -> None:
    """One user message — user's content must appear in the export."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    session.messages = [
        _make_message(
            id="msg-1",
            role="user",
            content="Write a hello-world script in Python.",
        )
    ]

    result_path = export_session_to_markdown(session)
    content = result_path.read_text()
    assert "Write a hello-world script in Python." in content


def test_export_multiple_turns() -> None:
    """User → Assistant → User → Assistant sequence.

    Verifies all turns are present *and* appear in the correct order.
    """
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    session.messages = [
        _make_message(id="msg-1", role="user", content="Q1"),
        _make_message(id="msg-2", role="assistant", content="A1"),
        _make_message(id="msg-3", role="user", content="Q2"),
        _make_message(id="msg-4", role="assistant", content="A2"),
    ]

    result_path = export_session_to_markdown(session)

    # All content must appear
    content = result_path.read_text()
    assert "Q1" in content
    assert "A1" in content
    assert "Q2" in content
    assert "A2" in content

    # Order check: Q1 before A1 before Q2 before A2
    idx_q1 = content.index("Q1")
    idx_a1 = content.index("A1")
    idx_q2 = content.index("Q2")
    idx_a2 = content.index("A2")
    assert idx_q1 < idx_a1 < idx_q2 < idx_a2


def test_export_tool_message_rendering() -> None:
    """A 'tool' role message with tool_name and tool_result.

    The tool name must be visible and the result must be included.
    Updated for OpenCode format.
    """
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    session.messages = [
        _make_message(
            id="msg-1",
            role="tool",
            content="",
            tool_name="bash",
            tool_args={"command": "ls -la"},
            tool_result="total 42\ndrwxr-xr-x  5 user  staff   160 Jul 20 12:00 .",
        )
    ]

    result_path = export_session_to_markdown(session)
    content = result_path.read_text()

    assert "bash" in content, "Tool name must appear in export"
    assert "total 42" in content, "Tool result content must appear in export"


def test_export_includes_timestamps() -> None:
    """Session metadata dates must appear in the header, not per-message."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session(created_at="2026-07-20T13:45:00+00:00")
    session.messages = [
        _make_message(id="msg-1", role="user", content="ping"),
    ]

    result_path = export_session_to_markdown(session)
    content = result_path.read_text()

    # The date portion must appear in the header
    assert "2026-07-20" in content, "Created date must appear in export header"


def test_export_includes_session_metadata() -> None:
    """Markdown export must include session id, model, and created_at."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session(
        id="sess-export-test-42",
        model="openrouter:anthropic/claude-opus-4-5",
        created_at="2026-07-19T08:00:00+00:00",
    )

    result_path = export_session_to_markdown(session)
    content = result_path.read_text()

    assert "sess-export-test-42" in content, "Session ID must appear"
    assert "openrouter:anthropic/claude-opus-4-5" in content, (
        "Model must appear"
    )
    assert "2026-07-19" in content, "Created date must appear"


def test_export_writes_to_file(tmp_path: Path) -> None:
    """The export must actually write the markdown to disk."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    session.messages = [
        _make_message(role="user", content="Save me to disk!")
    ]

    output_path = tmp_path / "export_test.md"
    result_path = export_session_to_markdown(session, output_path)

    assert result_path == output_path, "Must return the output path"
    assert output_path.exists(), "Output file must exist on disk"
    content = output_path.read_text()
    assert "Save me to disk!" in content


def test_export_file_naming(tmp_path: Path) -> None:
    """Default file name must include the session id."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session(id="sess-file-naming-test")

    result_path = export_session_to_markdown(
        session, tmp_path / "custom_name.md"
    )

    assert result_path.name == "custom_name.md", (
        "Should respect explicit filename"
    )
    assert result_path.parent == tmp_path, (
        "Should write to specified directory"
    )


def test_export_default_filename_includes_session_id(tmp_path: Path) -> None:
    """When no explicit path is given, derive filename from session id."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session(id="sess-abc123def456")

    result_path = export_session_to_markdown(session)

    assert "sess-abc123def456" in result_path.name, (
        "Default filename must include session id"
    )
    assert result_path.suffix == ".md", "Default extension must be .md"


def test_export_rich_markup_stripped() -> None:
    """Rich markup like ``[bold #58a6ff]text[/]`` must be stripped."""
    from pyharness.core.session_export import export_session_to_markdown

    session = _make_session()
    session.messages = [
        _make_message(
            role="assistant",
            content=(
                "[bold #58a6ff]Hello![/]\n"
                "Here is some [italic]styled[/] text.\n"
                "[#f85149 on #0d1117]Error:[/] something happened."
            ),
        )
    ]

    result_path = export_session_to_markdown(session)
    content = result_path.read_text()

    # Rich markup tags must be absent
    assert "[bold" not in content, "[bold ...] must be stripped"
    assert "[italic]" not in content, "[italic] must be stripped"
    assert "[#f85149" not in content, "color tags must be stripped"

    # But the actual text content must remain
    assert "Hello!" in content
    assert "styled" in content
    assert "Error:" in content
    assert "something happened." in content


def test_format_message_user() -> None:
    """Formatting a user message produces the OpenCode-style markdown."""
    from pyharness.core.session_export import format_message

    msg = _make_message(
        id="msg-10",
        role="user",
        content="Can you refactor this module?",
    )

    result = format_message(msg)

    assert isinstance(result, str)
    assert "Can you refactor this module?" in result
    # OpenCode format: ## User heading
    assert "## User" in result, "User messages must have '## User' heading"
    # No timestamp in message body
    assert "2026-07-20" not in result, (
        "Per-message timestamps must NOT appear in OpenCode format"
    )


def test_format_message_assistant() -> None:
    """Formatting an assistant message produces the OpenCode-style markdown."""
    from pyharness.core.session_export import format_message

    msg = _make_message(
        id="msg-11",
        role="assistant",
        content="Certainly! Here's the refactored code:\n\n```python\ndef foo(): pass\n```",
    )

    result = format_message(msg)

    assert isinstance(result, str)
    assert "## Assistant" in result, (
        "Assistant messages must have '## Assistant' heading"
    )
    assert "def foo(): pass" in result, "Code content must appear in export"


def test_format_message_tool() -> None:
    """Formatting a tool message produces the OpenCode-style markdown."""
    from pyharness.core.session_export import format_message

    msg = _make_message(
        id="msg-12",
        role="tool",
        content="",
        tool_name="read_file",
        tool_args={"filePath": "src/main.py"},
        tool_result="print('hello world')",
    )

    result = format_message(msg)

    assert isinstance(result, str)
    # OpenCode format: **Tool: read_file**
    assert "**Tool: read_file**" in result, (
        "Tool messages must use '**Tool: read_file**' format"
    )
    assert "print('hello world')" in result, "Tool result must appear"
    assert "src/main.py" in result, "Tool args must appear in input"
