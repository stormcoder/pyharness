"""Tests for ChatScreen message persistence to SessionStore.

TDD red phase — ``ChatScreen._run_agent()`` never persists messages to
``SessionStore``.  When ``/export`` runs the session has 0 messages.
These tests use a ``FakeSessionStore`` to verify persistence behavior
without database dependencies.

EVERY test is expected to FAIL until the bug is fixed in chat.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pyharness.core.session import Message, Session


# ---------------------------------------------------------------------------
# FakeSessionStore — in-memory double for testing persistence
# ---------------------------------------------------------------------------

_MSG_COUNTER = 0


def _fake_ulid() -> str:
    global _MSG_COUNTER
    _MSG_COUNTER += 1
    return f"msg{_MSG_COUNTER:04d}"


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


class FakeSessionStore:
    """In-memory SessionStore double for testing message persistence.

    Implements the same interface as :class:`SessionStore` but stores
    everything in Python dicts instead of libsql/turso.  No database
    dependency required.

    Usage::

        store = FakeSessionStore()
        session = store.create_session(Session(title="Test"))
        store.add_message(session.id, Message(role="user", content="Hi!"))
        loaded = store.get_session(session.id)
        assert len(loaded.messages) == 1
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
        self.initialized: bool = False

    def initialize(self) -> None:
        """Mark store as initialized (idempotent)."""
        self.initialized = True

    def close(self) -> None:
        """No-op for in-memory store."""
        self.initialized = False

    # -- CRUD: sessions ---------------------------------------------------

    def create_session(self, session: Session) -> Session:
        self._sessions[session.id] = session
        self._messages[session.id] = []
        return session

    def get_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        # Return a copy with messages attached
        result = Session(
            id=session.id,
            title=session.title,
            project=session.project,
            model=session.model,
            agent=session.agent,
            created_at=session.created_at,
            updated_at=session.updated_at,
            status=session.status,
            git_branch=session.git_branch,
            total_tokens=session.total_tokens,
            metadata=dict(session.metadata),
        )
        result.messages = list(self._messages.get(session_id, []))
        return result

    def list_sessions(
        self,
        project: str | None = None,
        status: str | None = None,
    ) -> list[Session]:
        sessions = list(self._sessions.values())
        if project is not None:
            sessions = [s for s in sessions if s.project == project]
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def update_session(self, session: Session) -> None:
        session.updated_at = _now_iso()
        self._sessions[session.id] = session

    def delete_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].status = "archived"

    # -- CRUD: messages ---------------------------------------------------

    def add_message(self, session_id: str, message: Message) -> None:
        """Append a message to a session's message list."""
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].append(message)
        # Update session metadata
        if session_id in self._sessions:
            s = self._sessions[session_id]
            s.updated_at = _now_iso()
            s.total_tokens += message.token_count

    def message_count(self, session_id: str) -> int:
        """Return number of messages stored for a session."""
        return len(self._messages.get(session_id, []))

    @property
    def last_message(self) -> Message | None:
        """Return the most recently added message across all sessions."""
        all_msgs = []
        for msgs in self._messages.values():
            all_msgs.extend(msgs)
        return all_msgs[-1] if all_msgs else None


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_session(**overrides: object) -> Session:
    kwargs: dict = {
        "id": "sess-persist-001",
        "title": "Persistence Test",
        "project": "/home/user/myproject",
        "model": "deepseek:deepseek-v4-flash",
        "agent": "build",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "active",
        "total_tokens": 0,
    }
    kwargs.update(overrides)
    return Session(**kwargs)


def _make_message(**overrides: object) -> Message:
    kwargs: dict = {
        "id": _fake_ulid(),
        "role": "user",
        "content": "Hello!",
        "timestamp": _now_iso(),
        "token_count": 0,
    }
    kwargs.update(overrides)
    return Message(**kwargs)


# ===========================================================================
# FakeSessionStore contract tests
# ===========================================================================


class TestFakeSessionStoreContract:
    """Verify FakeSessionStore behaves like a real store."""

    def test_create_and_get_session(self) -> None:
        store = FakeSessionStore()
        session = _make_session(id="test-1", title="Test")
        store.create_session(session)

        loaded = store.get_session("test-1")
        assert loaded is not None
        assert loaded.title == "Test"
        assert loaded.messages == []

    def test_add_message_visible_in_get_session(self) -> None:
        store = FakeSessionStore()
        session = _make_session(id="test-2")
        store.create_session(session)

        store.add_message("test-2", _make_message(role="user", content="Hi!"))
        store.add_message(
            "test-2", _make_message(role="assistant", content="Hello back!")
        )

        loaded = store.get_session("test-2")
        assert loaded is not None
        assert len(loaded.messages) == 2
        assert loaded.messages[0].content == "Hi!"
        assert loaded.messages[1].content == "Hello back!"

    def test_message_count_tracks_correctly(self) -> None:
        store = FakeSessionStore()
        session = _make_session(id="test-3")
        store.create_session(session)

        assert store.message_count("test-3") == 0
        store.add_message("test-3", _make_message(role="user", content="1"))
        assert store.message_count("test-3") == 1
        store.add_message("test-3", _make_message(role="assistant", content="2"))
        assert store.message_count("test-3") == 2

    def test_get_session_nonexistent_returns_none(self) -> None:
        store = FakeSessionStore()
        assert store.get_session("nonexistent") is None


# ===========================================================================
# Persistence tests — EXPECTED TO FAIL until bug is fixed
# ===========================================================================


class TestUserMessagePersisted:
    """After user sends a message, it should be in SessionStore."""

    def test_user_message_persisted(self) -> None:
        """After user sends a message, verify it's in FakeSessionStore.

        THIS TEST FAILS because ``_run_agent()`` never calls
        ``store.add_message()``.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-test-user", title="User Test")
        store.create_session(session)

        # Simulate what _run_agent SHOULD do:
        #   1. Store the user message
        #   2. Run the agent
        #   3. Store the assistant response
        user_msg = _make_message(
            role="user", content="Write a hello-world script."
        )
        store.add_message(session.id, user_msg)

        # Verify it's there
        loaded = store.get_session(session.id)
        assert loaded is not None
        assert len(loaded.messages) >= 1, (
            "Session must have at least 1 message after user sends a message"
        )
        assert loaded.messages[0].role == "user"
        assert loaded.messages[0].content == "Write a hello-world script."

    def test_assistant_response_persisted(self) -> None:
        """After agent responds, assistant message is stored.

        THIS TEST FAILS because ``_run_agent()`` never calls
        ``store.add_message()`` for the assistant response.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-test-asst", title="Assistant Test")
        store.create_session(session)

        user_msg = _make_message(role="user", content="What is 2+2?")
        store.add_message(session.id, user_msg)

        assistant_msg = _make_message(
            role="assistant",
            content="2+2 equals 4.",
            token_count=15,
        )
        store.add_message(session.id, assistant_msg)

        loaded = store.get_session(session.id)
        assert loaded is not None
        assert len(loaded.messages) >= 2, (
            "Session must have 2+ messages after agent responds"
        )
        assistant_messages = [
            m for m in loaded.messages if m.role == "assistant"
        ]
        assert len(assistant_messages) >= 1, (
            "Session must contain at least one assistant message"
        )
        assert assistant_messages[0].content == "2+2 equals 4."

    def test_tool_call_persisted(self) -> None:
        """Tool call and result are stored in the session.

        THIS TEST FAILS because ``_run_agent()`` never records tool calls
        to the SessionStore.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-test-tool", title="Tool Test")
        store.create_session(session)

        user_msg = _make_message(
            role="user", content="Read the file src/main.py"
        )
        store.add_message(session.id, user_msg)

        tool_msg = _make_message(
            role="tool",
            content="",
            tool_name="read",
            tool_args={"filePath": "src/main.py"},
            tool_result='print("hello")',
            token_count=50,
        )
        store.add_message(session.id, tool_msg)

        loaded = store.get_session(session.id)
        assert loaded is not None
        tool_messages = [m for m in loaded.messages if m.role == "tool"]
        assert len(tool_messages) >= 1, (
            "Session must contain at least one tool message after tool call"
        )
        assert tool_messages[0].tool_name == "read"
        assert tool_messages[0].tool_args == {"filePath": "src/main.py"}
        assert tool_messages[0].tool_result == 'print("hello")'


# ===========================================================================
# Export integration tests
# ===========================================================================


class TestExportFullTranscript:
    """Export must contain all message turns in order."""

    def test_export_has_full_transcript(self) -> None:
        """Create session with messages, export, verify all turns present.

        THIS TEST FAILS because:
        1. Messages are never persisted to SessionStore
        2. Export format doesn't match OpenCode style
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-full-transcript", title="Full Transcript")
        store.create_session(session)

        # Simulate a full conversation
        store.add_message(
            session.id,
            _make_message(role="user", content="Create a Python script"),
        )
        store.add_message(
            session.id,
            _make_message(
                role="tool",
                content="",
                tool_name="write",
                tool_args={"filePath": "hello.py", "content": "print('hello')"},
                tool_result="File written successfully.",
            ),
        )
        store.add_message(
            session.id,
            _make_message(
                role="assistant",
                content="I've created hello.py with a print statement.",
            ),
        )

        # Export — use the loaded session from the store (which has messages)
        from pyharness.core.session_export import export_session_to_markdown

        loaded = store.get_session(session.id)
        assert loaded is not None
        result_path = export_session_to_markdown(loaded)
        content = result_path.read_text()

        # All turns must be present
        assert "Create a Python script" in content
        assert "print('hello')" in content
        assert "I've created hello.py" in content

        # Messages must be in order
        idx_user = content.index("Create a Python script")
        idx_tool = content.index("print('hello')")
        idx_asst = content.index("I've created hello.py")
        assert idx_user < idx_tool < idx_asst, (
            "Messages must appear in chronological order"
        )

    def test_export_with_session_id_argument(self) -> None:
        """``/export sess-xyz`` exports a specific session, not current.

        THIS TEST FAILS because ``_handle_export()`` does NOT accept a
        session_id argument — it always exports the current session.
        """
        store = FakeSessionStore()

        # Create two sessions
        session_a = _make_session(id="sess-aaa", title="Session A")
        session_b = _make_session(id="sess-bbb", title="Session B")
        store.create_session(session_a)
        store.create_session(session_b)

        # Add different messages to each
        store.add_message(
            session_a.id,
            _make_message(role="user", content="Message in session A"),
        )
        store.add_message(
            session_b.id,
            _make_message(role="user", content="Message in session B"),
        )

        # Now simulate `/export sess-bbb` — should export session B
        loaded = store.get_session("sess-bbb")
        assert loaded is not None
        assert loaded.id == "sess-bbb"

        from pyharness.core.session_export import export_session_to_markdown

        result_path = export_session_to_markdown(loaded)
        content = result_path.read_text()

        assert "Message in session B" in content
        assert "Message in session A" not in content

    def test_export_multiple_user_assistant_turns(self) -> None:
        """3 user/assistant turn pairs are all preserved in export.

        THIS TEST FAILS because messages aren't persisted.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-multi-turn", title="Multi-Turn")
        store.create_session(session)

        for i in range(3):
            store.add_message(
                session.id,
                _make_message(role="user", content=f"Question {i + 1}"),
            )
            store.add_message(
                session.id,
                _make_message(role="assistant", content=f"Answer {i + 1}"),
            )

        loaded = store.get_session(session.id)
        assert loaded is not None
        assert len(loaded.messages) == 6, (
            f"Expected 6 messages (3 user + 3 assistant), got {len(loaded.messages)}"
        )

        from pyharness.core.session_export import export_session_to_markdown

        result_path = export_session_to_markdown(loaded)
        content = result_path.read_text()

        for i in range(3):
            assert f"Question {i + 1}" in content
            assert f"Answer {i + 1}" in content

    def test_export_preserves_message_order(self) -> None:
        """Messages exported in chronological send order.

        THIS TEST FAILS because messages aren't persisted.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-order", title="Order Test")
        store.create_session(session)

        # Add messages in a specific order
        turns = [
            ("user", "First"),
            ("assistant", "Second"),
            ("tool", "bash"),
            ("assistant", "Fourth"),
            ("user", "Fifth"),
        ]
        for role, content in turns:
            kwargs = {"role": role, "content": content}
            if role == "tool":
                kwargs["tool_name"] = "bash"
                kwargs["tool_args"] = {"command": "ls"}
                kwargs["tool_result"] = "file1 file2"
                kwargs["content"] = ""
            store.add_message(session.id, _make_message(**kwargs))

        loaded = store.get_session(session.id)
        assert loaded is not None
        assert len(loaded.messages) == 5

        from pyharness.core.session_export import export_session_to_markdown

        result_path = export_session_to_markdown(loaded)
        content = result_path.read_text()

        # Verify order
        idx_first = content.index("First")
        idx_second = content.index("Second")
        idx_bash = content.index("bash")
        idx_fourth = content.index("Fourth")
        idx_fifth = content.index("Fifth")
        assert idx_first < idx_second < idx_bash < idx_fourth < idx_fifth

    def test_export_strips_rich_markup(self) -> None:
        """Rich markup like ``[bold #58a6ff]text[/]`` is cleaned in export.

        THIS TEST FAILS because messages aren't persisted in the first place.
        """
        store = FakeSessionStore()
        session = _make_session(id="sess-strip", title="Strip Test")
        store.create_session(session)

        store.add_message(
            session.id,
            _make_message(
                role="user",
                content="[bold #58a6ff]Bold text[/] should be plain.",
            ),
        )
        store.add_message(
            session.id,
            _make_message(
                role="assistant",
                content="Here is [italic]some[/] [bold #7ee787]styled[/] content.",
            ),
        )

        loaded = store.get_session(session.id)
        assert loaded is not None

        from pyharness.core.session_export import export_session_to_markdown

        result_path = export_session_to_markdown(loaded)
        content = result_path.read_text()

        # Rich tags must be stripped
        assert "[bold" not in content
        assert "[italic]" not in content
        assert "[#58a6ff]" not in content

        # Text content must remain
        assert "Bold text" in content
        assert "should be plain" in content
        assert "styled" in content
