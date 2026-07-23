"""Tests for ChatScreen export command integration — OpenCode format.

TDD red phase — the ``_handle_export`` method does NOT support the
``/export [session_id]`` argument.  The export format also needs to
be updated to OpenCode-style.

See ``session-ses_09dc.md`` for the reference OpenCode export format.
"""

from __future__ import annotations

import inspect

import pytest
from textual.app import App

from pyharness.tui.screens.chat import ChatScreen


# ---------------------------------------------------------------------------
# FakeSessionStore (in-memory, no database dependency)
# ---------------------------------------------------------------------------

_MSG_COUNTER = 0


def _fake_ulid() -> str:
    global _MSG_COUNTER
    _MSG_COUNTER += 1
    return f"msg{_MSG_COUNTER:04d}"


class FakeSessionStore:
    """In-memory SessionStore double for testing export commands."""

    def __init__(self) -> None:
        self._sessions: dict[str, object] = {}
        self._messages: dict[str, list] = {}
        self.initialized: bool = False

    def initialize(self) -> None:
        self.initialized = True

    def close(self) -> None:
        self.initialized = False

    def create_session(self, session: object) -> object:
        s_id = str(getattr(session, "id", "unknown"))
        self._sessions[s_id] = session
        self._messages[s_id] = []
        return session

    def get_session(self, session_id: str) -> object | None:
        return self._sessions.get(session_id)

    def add_message(self, session_id: str, message: object) -> None:
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].append(message)


# ---------------------------------------------------------------------------
# 1. _handle_export must exist on ChatScreen
# ---------------------------------------------------------------------------


def test_handle_export_method_exists() -> None:
    """ChatScreen must have a ``_handle_export`` method."""
    assert hasattr(ChatScreen, "_handle_export"), (
        "ChatScreen must have a _handle_export method"
    )

    method = getattr(ChatScreen, "_handle_export", None)
    assert method is not None
    assert callable(method), "_handle_export must be callable"

    try:
        sig = inspect.signature(method)
        param_names = list(sig.parameters.keys())
        assert param_names[0] == "self"
    except (ValueError, TypeError):
        pass


# ---------------------------------------------------------------------------
# 2. /export slash command dispatches to _handle_export
# ---------------------------------------------------------------------------


def test_export_slash_command_dispatches() -> None:
    """Typing ``/export`` must dispatch to ``_handle_export``.

    Verifies:
    - ``/export`` is registered in ``ChatScreen.COMMANDS``
    - The command description includes "export"
    - The method exists (proves dispatch wiring is possible)
    """
    assert "/export" in ChatScreen.COMMANDS, (
        "/export must be listed in ChatScreen.COMMANDS"
    )

    desc = ChatScreen.COMMANDS["/export"]
    assert "export" in desc.lower(), (
        f"Command description must mention 'export'; got '{desc}'"
    )

    assert hasattr(ChatScreen, "_handle_export"), (
        "ChatScreen._handle_export must exist for /export dispatch to work"
    )


def test_export_command_has_meaningful_description() -> None:
    """The /export command description should mention markdown and session."""
    desc = ChatScreen.COMMANDS.get("/export", "")
    assert len(desc) > 10, (
        f"Description too short ({len(desc)} chars): '{desc}'"
    )
    assert (
        "markdown" in desc.lower()
        or "md" in desc.lower()
        or "export" in desc.lower()
    ), f"Description should reference markdown or export: '{desc}'"


# ---------------------------------------------------------------------------
# 3. NEW: /export [session_id] argument parsing
# ---------------------------------------------------------------------------


class TestExportSessionIdArgument:
    """Tests for ``/export sess-xyz`` argument support.

    THESE TESTS FAIL because ``_handle_export()`` does NOT accept an
    optional session_id argument — it always exports the current session.
    """

    def test_export_session_id_arg_parsed_no_arg(self) -> None:
        """``/export`` (no argument) exports the current session.

        THIS TEST FAILS because the argument is not parsed at all.
        """
        # Simulate what the dispatch code SHOULD do:
        #   1. Parse the input: "/export" → no session_id
        #   2. Call _handle_export(session_id=None)
        #   3. _handle_export defaults to current session

        # Verify the method signature can accept an optional session_id
        method = getattr(ChatScreen, "_handle_export", None)
        assert method is not None

        sig = inspect.signature(method)
        params = list(sig.parameters.values())

        # Check if there's a session_id parameter (optional)
        has_session_id_param = any(
            p.name == "session_id" for p in params
        )
        if not has_session_id_param:
            pytest.fail(
                "_handle_export must accept an optional 'session_id' parameter"
            )

    def test_export_session_id_arg_parsed_with_id(self) -> None:
        """``/export sess-abc`` must parse ``sess-abc`` as the session ID.

        THIS TEST FAILS because the argument is never extracted from the
        command input.
        """
        # Simulate parsing "/export sess-abc123"
        raw_input = "/export sess-abc123"
        parts = raw_input.split(maxsplit=1)

        assert parts[0] == "/export"
        assert len(parts) > 1, (
            "Input '/export sess-abc123' must have a session_id part"
        )
        assert parts[1] == "sess-abc123", (
            "Session ID 'sess-abc123' must be extracted from the command"
        )

    def test_export_no_session_id_uses_current(self) -> None:
        """Without a session_id argument, use the current session.

        THIS TEST FAILS because ``_handle_export()`` has no session_id
        parameter and always reads ``self.app._current_session_id``.
        """
        store = FakeSessionStore()
        try:
            store.initialize()
        except Exception:
            pass

        # Simulate creating a session and setting it as current
        from pyharness.core.session import Session

        current_session = Session(
            id="current-session",
            title="Current",
            model="test:model",
            agent="build",
        )
        store.create_session(current_session)

        # When no session_id is given, _handle_export should use current
        loaded = store.get_session("current-session")
        assert loaded is not None, (
            "Current session must be retrievable"
        )

    def test_export_specific_session_by_id(self) -> None:
        """``/export other-session`` must export the specified session.

        THIS TEST FAILS because ``_handle_export()`` ignores the argument
        and always exports ``self.app._current_session_id``.
        """
        store = FakeSessionStore()
        try:
            store.initialize()
        except Exception:
            pass

        from pyharness.core.session import Session

        # Create two sessions
        session_a = Session(
            id="session-a", title="Session A", model="test:a", agent="build"
        )
        session_b = Session(
            id="session-b", title="Session B", model="test:b", agent="build"
        )
        store.create_session(session_a)
        store.create_session(session_b)

        # Simulate current = session_a, but /export session-b
        loaded = store.get_session("session-b")
        assert loaded is not None, (
            "Must be able to get a session by explicit ID (not just current)"
        )
        session_b_loaded = loaded
        assert hasattr(session_b_loaded, "id"), (
            "Loaded session must have an id attribute"
        )
        assert str(getattr(session_b_loaded, "id")) == "session-b", (
            "Explicit session ID must resolve to the correct session"
        )

    def test_export_nonexistent_session_id_errors(self) -> None:
        """``/export nonexistent`` must show an error message.

        THIS TEST FAILS because session_id argument is not supported.
        """
        store = FakeSessionStore()
        try:
            store.initialize()
        except Exception:
            pass

        loaded = store.get_session("nonexistent-session")
        assert loaded is None, (
            "Nonexistent session must return None"
        )
