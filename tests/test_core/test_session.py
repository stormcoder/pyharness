"""Tests for the SQLite session storage layer."""

from __future__ import annotations

import pytest

from pyharness.core.session import Message, Session, SessionStore

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_session(**overrides) -> Session:
    kwargs = {
        "title": "Test Session",
        "project": "test-project",
        "model": "anthropic:claude-sonnet-4-5",
        "agent": "build",
        **overrides,
    }
    return Session(**kwargs)


def _make_message(**overrides) -> Message:
    kwargs = {
        "role": "user",
        "content": "Hello, world!",
        **overrides,
    }
    return Message(**kwargs)


# ---------------------------------------------------------------------------
# 1. Initialize creates tables
# ---------------------------------------------------------------------------


def test_initialize_creates_tables(store: SessionStore) -> None:
    """After initialization, schema_version and sessions tables must exist."""
    db = store._db
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "schema_version" in tables
    assert "sessions" in tables
    assert "messages" in tables

    # Verify WAL mode is active
    cursor = db.execute("PRAGMA journal_mode")
    row = cursor.fetchone()
    assert row is not None
    assert row[0].lower() == "wal"


# ---------------------------------------------------------------------------
# 2. Create and retrieve a session
# ---------------------------------------------------------------------------


def test_create_and_get_session(store: SessionStore) -> None:
    """Creating a session and retrieving it by ID should work round-trip."""
    s = _make_session()
    created = store.create_session(s)

    assert created.id == s.id
    assert created.title == "Test Session"

    loaded = store.get_session(s.id)
    assert loaded is not None
    assert loaded.id == s.id
    assert loaded.title == "Test Session"
    assert loaded.project == "test-project"
    assert loaded.model == "anthropic:claude-sonnet-4-5"
    assert loaded.agent == "build"
    assert loaded.status == "active"
    assert isinstance(loaded.messages, list)
    assert len(loaded.messages) == 0


# ---------------------------------------------------------------------------
# 3. Add messages to a session and retrieve them
# ---------------------------------------------------------------------------


def test_add_and_retrieve_messages(store: SessionStore) -> None:
    """Messages appended to a session should be returned in timestamp order."""
    s = _make_session()
    store.create_session(s)

    msg1 = _make_message(role="user", content="First message")
    msg2 = _make_message(role="assistant", content="Second message")
    msg3 = _make_message(
        role="tool",
        content="",
        tool_name="bash",
        tool_args={"command": "ls"},
        tool_result="file1.py\nfile2.py",
        token_count=42,
    )

    store.add_message(s.id, msg1)
    store.add_message(s.id, msg2)
    store.add_message(s.id, msg3)

    loaded = store.get_session(s.id)
    assert loaded is not None
    assert len(loaded.messages) == 3

    assert loaded.messages[0].role == "user"
    assert loaded.messages[0].content == "First message"

    assert loaded.messages[1].role == "assistant"
    assert loaded.messages[1].content == "Second message"

    assert loaded.messages[2].role == "tool"
    assert loaded.messages[2].tool_name == "bash"
    assert loaded.messages[2].tool_args == {"command": "ls"}
    assert loaded.messages[2].tool_result == "file1.py\nfile2.py"
    assert loaded.messages[2].token_count == 42

    # Session total_tokens should be updated
    assert loaded.total_tokens == 42


# ---------------------------------------------------------------------------
# 4. List sessions filtered by project
# ---------------------------------------------------------------------------


def test_list_sessions_filtered_by_project(store: SessionStore) -> None:
    """list_sessions should only return sessions for the given project."""
    s1 = _make_session(title="Project A — session 1", project="project-a")
    s2 = _make_session(title="Project A — session 2", project="project-a")
    s3 = _make_session(title="Project B — session 1", project="project-b")

    store.create_session(s1)
    store.create_session(s2)
    store.create_session(s3)

    a_sessions = store.list_sessions(project="project-a")
    b_sessions = store.list_sessions(project="project-b")
    all_sessions = store.list_sessions()

    assert len(a_sessions) == 2
    assert {s.title for s in a_sessions} == {
        "Project A — session 1",
        "Project A — session 2",
    }

    assert len(b_sessions) == 1
    assert b_sessions[0].title == "Project B — session 1"

    assert len(all_sessions) == 3


# ---------------------------------------------------------------------------
# 5. Update session status
# ---------------------------------------------------------------------------


def test_update_session_status(store: SessionStore) -> None:
    """Updating a session's status should be reflected on reload."""
    s = _make_session()
    store.create_session(s)

    s.status = "idle"
    s.title = "Updated Title"
    store.update_session(s)

    loaded = store.get_session(s.id)
    assert loaded is not None
    assert loaded.status == "idle"
    assert loaded.title == "Updated Title"


# ---------------------------------------------------------------------------
# 6. Delete (archive) a session
# ---------------------------------------------------------------------------


def test_delete_session_archives(store: SessionStore) -> None:
    """Deleting a session should mark it as 'archived', not remove it."""
    s = _make_session()
    store.create_session(s)

    store.delete_session(s.id)

    # Direct query confirms archived status (list_sessions defaults to
    # no status filter, but we check the raw status)
    loaded = store.get_session(s.id)
    assert loaded is not None
    assert loaded.status == "archived"

    # Filtering by 'active' should exclude it
    active = store.list_sessions(status="active")
    assert s.id not in {x.id for x in active}

    # Filtering by 'archived' should include it
    archived = store.list_sessions(status="archived")
    assert s.id in {x.id for x in archived}


# ---------------------------------------------------------------------------
# 7. Nonexistent session returns None
# ---------------------------------------------------------------------------


def test_get_nonexistent_session(store: SessionStore) -> None:
    """Getting a session that doesn't exist should return None."""
    result = store.get_session("sess-nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# 8. Session metadata round-trip
# ---------------------------------------------------------------------------


def test_session_metadata_roundtrip(store: SessionStore) -> None:
    """Custom metadata stored on a session should survive round-trip."""
    s = _make_session(
        metadata={"cwd": "/home/user/project", "editor": "vim", "env": {"DEBUG": "1"}}
    )
    store.create_session(s)

    loaded = store.get_session(s.id)
    assert loaded is not None
    assert loaded.metadata == {
        "cwd": "/home/user/project",
        "editor": "vim",
        "env": {"DEBUG": "1"},
    }


# ===========================================================================
# Bug 3: Hard Delete (TDD — FAILING)
# ===========================================================================


class TestHardDelete:
    """SessionStore must support permanent row deletion (hard_delete)."""

    def test_hard_delete_removes_row(self, store: SessionStore) -> None:
        """``store.hard_delete(session_id)`` must remove the row from the
        database entirely — get_session returns None after."""
        s = _make_session()
        store.create_session(s)

        # Confirm session exists
        assert store.get_session(s.id) is not None

        # Hard delete
        store.hard_delete(s.id)

        # Session must be gone entirely
        assert store.get_session(s.id) is None, (
            "hard_delete() must permanently remove the session row. "
            "get_session() should return None."
        )

    def test_hard_delete_removes_messages(self, store: SessionStore) -> None:
        """Hard-deleting a session must cascade-delete its messages."""
        s = _make_session()
        store.create_session(s)

        msg1 = _make_message(role="user", content="First")
        msg2 = _make_message(role="assistant", content="Second")
        store.add_message(s.id, msg1)
        store.add_message(s.id, msg2)

        # Confirm messages exist via direct query
        db = store._db
        count_before = db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (s.id,)
        ).fetchone()[0]
        assert count_before == 2

        # Hard delete
        store.hard_delete(s.id)

        # Messages for this session must be gone
        count_after = db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (s.id,)
        ).fetchone()[0]
        assert count_after == 0, (
            f"hard_delete() must cascade-delete messages. "
            f"Found {count_after} messages still in DB."
        )

    def test_delete_session_still_soft_deletes(self, store: SessionStore) -> None:
        """Existing ``delete_session()`` must still soft-delete (backward compat)."""
        s = _make_session()
        store.create_session(s)

        store.delete_session(s.id)

        loaded = store.get_session(s.id)
        assert loaded is not None, (
            "Soft-delete must retain the row — get_session() must still find it"
        )
        assert loaded.status == "archived", (
            f"Soft-delete must set status='archived', got {loaded.status!r}"
        )

    def test_hard_delete_nonexistent_does_not_raise(self, store: SessionStore) -> None:
        """``hard_delete('nonexistent')`` must not raise an exception."""
        try:
            store.hard_delete("sess-nonexistent-xyz")
        except Exception as exc:
            pytest.fail(
                f"hard_delete() on nonexistent session must not raise: {exc}"
            )
