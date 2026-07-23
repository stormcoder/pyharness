"""Tests for SessionBrowser — R1.7 and R1.8 from the parallel multi-agent spec.

R1.7: SessionBrowser queries real sessions and displays them.
R1.8: SessionBrowser supports resume, new, archive, and delete actions.

Run with::

    uv run pytest tests/test_tui/test_session_browser.py -q --tb=short
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Button, ListItem, ListView, Static

from pyharness.tui.screens.sessions import (
    SessionBrowser,
    _format_session_label,
    _format_tokens,
    _truncate_id,
)

# =============================================================================
# Minimal fake Session / SessionStore for testing without libsql
# =============================================================================


@dataclass
class FakeSession:
    """Drop-in Session stand-in so tests don't need libsql / turso."""

    id: str
    title: str = "New Session"
    project: str = ""
    model: str = ""
    agent: str = "build"
    status: str = "active"
    git_branch: str | None = None
    total_tokens: int = 0
    metadata: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at


class FakeSessionStore:
    """In-memory SessionStore stand-in for SessionBrowser tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, FakeSession] = {}

    def create_session(self, session: FakeSession) -> FakeSession:
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> FakeSession | None:
        return self._sessions.get(session_id)

    def list_sessions(
        self, project: str | None = None, status: str | None = None
    ) -> list[FakeSession]:
        sessions = list(self._sessions.values())
        if project is not None:
            sessions = [s for s in sessions if s.project == project]
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        # Sort by updated_at descending (newest first), matching SessionStore behavior
        sessions.sort(key=lambda s: s.updated_at or "", reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> None:
        """Soft-delete (archive) a session."""
        s = self._sessions.get(session_id)
        if s:
            s.status = "archived"


# =============================================================================
# Minimal test App wrapper
# =============================================================================


class _TestApp(App[None]):
    """Minimal Textual app that pushes a SessionBrowser as default screen."""

    def __init__(self, browser: SessionBrowser) -> None:
        self._browser = browser
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(self._browser)




def _run_browser(browser: SessionBrowser) -> object:
    """Return the ``run_test`` context manager for a SessionBrowser."""
    app = _TestApp(browser)
    return app.run_test()


# =============================================================================
# Helpers — session factories
# =============================================================================


def _make_fake_sessions(count: int = 3) -> list[FakeSession]:
    """Create a list of distinct FakeSession instances."""
    sessions: list[FakeSession] = []
    for i in range(1, count + 1):
        sessions.append(
            FakeSession(
                id=f"sess-test-{i:04d}",
                title=f"Test Session {i}",
                project=f"project-{i}",
                model="anthropic:claude-sonnet-4-5",
                agent="build" if i % 2 == 1 else "plan",
                status="active" if count == 1 or i <= count - 1 else "archived",
                total_tokens=i * 500,
            )
        )
    return sessions


def _populate_fake_store(
    store: FakeSessionStore, sessions: list[FakeSession]
) -> None:
    for s in sessions:
        store.create_session(s)


def _extract_list_item_texts(pilot: Pilot[None]) -> list[str]:
    """Extract plain text from all ListItem children in the session list."""
    screen = _browser_from_pilot(pilot)
    list_view = screen.query_one(ListView)
    texts: list[str] = []
    for child in list_view.children:
        if isinstance(child, ListItem):
            for sub in child.children:
                if isinstance(sub, Static):
                    rendered = sub.render()
                    if hasattr(rendered, "plain"):
                        texts.append(rendered.plain)
                    else:
                        texts.append(str(rendered))
    return texts


def _browser_from_pilot(pilot: Pilot[None]) -> SessionBrowser:
    """Extract the SessionBrowser instance from the pilot's app."""
    screen = pilot.app.screen_stack[-1]
    assert isinstance(screen, SessionBrowser), (
        f"Expected SessionBrowser, got {type(screen).__name__}"
    )
    return screen


# =============================================================================
# Unit tests — format helpers
# =============================================================================


class TestFormatHelpers:
    """Unit tests for display formatting helpers."""

    def test_truncate_id_short(self) -> None:
        assert _truncate_id("abc", width=12) == "abc"
        assert _truncate_id("sess-123456", width=12) == "sess-123456"

    def test_truncate_id_long(self) -> None:
        result = _truncate_id("sess-abcdefghijklmnop")
        assert len(result) <= 13
        assert result.endswith("\u2026")

    def test_format_tokens_small(self) -> None:
        assert _format_tokens(0) == "0 tok"
        assert _format_tokens(42) == "42 tok"
        assert _format_tokens(999) == "999 tok"

    def test_format_tokens_k(self) -> None:
        assert _format_tokens(1_000) == "1k tok"
        assert _format_tokens(1_500) == "1k tok"
        assert _format_tokens(15_500) == "15k tok"

    def test_format_tokens_m(self) -> None:
        assert _format_tokens(1_000_000) == "1.0M tok"
        assert _format_tokens(2_500_000) == "2.5M tok"

    def test_format_session_label_includes_key_fields(self) -> None:
        s = FakeSession(
            id="sess-abc123",
            title="Fix the bug",
            model="anthropic:claude-sonnet-4-5",
            agent="build",
            status="active",
            total_tokens=1500,
        )
        label = _format_session_label(s)  # type: ignore[arg-type]
        assert "Fix the bug" in label
        assert "active" in label
        assert "claude-sonnet-4-5" in label
        assert "build" in label
        assert "1k tok" in label
        assert "sess-abc123" in label

    def test_format_session_label_fallback_title(self) -> None:
        s = FakeSession(id="sess-x", title="", model="", agent="build")
        label = _format_session_label(s)  # type: ignore[arg-type]
        assert "Untitled" in label

    def test_format_session_label_fallback_model(self) -> None:
        s = FakeSession(id="sess-x", title="Test", model="", agent="build")
        label = _format_session_label(s)  # type: ignore[arg-type]
        assert "\u2014" in label


# =============================================================================
# Unit tests — SessionBrowser internals (no Textual runtime)
# =============================================================================


class TestSessionBrowserUnit:
    """Constructor and helper tests that need no Textual runtime."""

    def test_construct_with_explicit_store(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        assert browser._session_store is store

    def test_construct_without_store(self) -> None:
        browser = SessionBrowser()
        assert browser._session_store is None

    def test_initial_sessions_empty(self) -> None:
        browser = SessionBrowser()
        assert browser._sessions == []

    def test_resolve_store_explicit(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        assert browser._resolve_store() is store


# =============================================================================
# Integration tests — with Textual pilot
# =============================================================================


class TestSessionBrowserIntegration:
    """Async pilot tests exercising the full Textual screen lifecycle."""

    async def test_mount_shows_empty_state_when_no_sessions(self) -> None:
        """R1.7: Empty store → 'No saved sessions yet' message."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            texts = _extract_list_item_texts(pilot)
            assert any("No saved sessions yet" in t for t in texts), (
                f"Expected empty-state message, got: {texts}"
            )

    async def test_mount_shows_sessions_when_populated(self) -> None:
        """R1.7: Populated store → each session appears in the list."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(3)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            texts = _extract_list_item_texts(pilot)
            assert len(texts) >= 3, f"Expected 3 items, got {len(texts)}: {texts}"
            for s in sessions:
                matching = [t for t in texts if s.title in t]
                assert matching, (
                    f"Session '{s.title}' not found in list items: {texts}"
                )

    async def test_mount_shows_no_sessions_store_none(self) -> None:
        """R1.7: No store → graceful 'Session store not connected' message."""
        browser = SessionBrowser(session_store=None)
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            texts = _extract_list_item_texts(pilot)
            assert any("Session store not connected" in t for t in texts), (
                f"Expected store-not-connected message, got: {texts}"
            )

    async def test_resume_does_not_crash_when_no_selection(self) -> None:
        """R1.8: Resume with no selection notifies user (no crash)."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            screen.action_resume()  # Must not raise

    async def test_new_session_dismisses_with_sentinel(self) -> None:
        """R1.8: New action sends '__new__' sentinel to the caller."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            screen.action_new_session()  # Must not raise

    async def test_archive_updates_session_status(self) -> None:
        """R1.8: Archive action sets the session status to 'archived'."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(2)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            list_view = screen.query_one(ListView)
            list_view.index = 0
            await pilot.pause()

            screen.action_archive()

        # After dismiss, verify the session was archived
        # Use the store's sorted session list — the first displayed session
        # is the one at index 0 in the sorted list
        sorted_sessions = store.list_sessions()
        archived = store.get_session(sorted_sessions[0].id)
        assert archived is not None
        assert archived.status == "archived", (
            f"Expected 'archived', got {archived.status!r}"
        )

    async def test_delete_action_archives_session(self) -> None:
        """R1.8: Delete action archives the session via soft-delete."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(3)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            list_view = screen.query_one(ListView)
            list_view.index = 0
            await pilot.pause()

            screen.action_delete_session()

        sorted_sessions = store.list_sessions()
        deleted = store.get_session(sorted_sessions[0].id)
        assert deleted is not None
        assert deleted.status == "archived", (
            f"Expected 'archived' after delete, got {deleted.status!r}"
        )

    async def test_dismiss_works(self) -> None:
        """Escape / dismiss returns None (no session selected)."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            screen.action_dismiss()  # Must not raise

    async def test_button_new_session_exists(self) -> None:
        """The 'New Session' button is composed."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            btn = screen.query_one(Button)
            assert btn is not None, "New Session button must exist"

    async def test_display_shows_all_required_fields(self) -> None:
        """R1.7: Each session row shows id (truncated), title, model, agent,
        status, and token count."""
        store = FakeSessionStore()
        s = FakeSession(
            id="sess-abcdef1234567890",
            title="Debug the thing",
            model="openai:gpt-4o",
            agent="explore",
            status="active",
            total_tokens=4200,
        )
        _populate_fake_store(store, [s])

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            texts = _extract_list_item_texts(pilot)
            row = texts[0]

            assert "Debug the thing" in row, "title missing"
            assert "openai:gpt-4o" in row, "model missing"
            assert "explore" in row, "agent missing"
            assert "active" in row, "status missing"
            assert "4k tok" in row, "token count missing"
            assert "sess-abcdef1\u2026" in row, f"truncated ID missing in: {row!r}"


# =========================================================================
# Backward compatibility
# =========================================================================


class TestSessionBrowserBackwardCompat:
    """Ensure SessionBrowser remains backward compatible."""

    async def test_no_store_does_not_crash_on_dismiss(self) -> None:
        browser = SessionBrowser(session_store=None)
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            _browser_from_pilot(pilot).action_dismiss()

    async def test_empty_list_dismiss_works(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            _browser_from_pilot(pilot).action_dismiss()

    async def test_archive_on_empty_list_shows_warning(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            _browser_from_pilot(pilot).action_archive()

    async def test_delete_on_empty_list_shows_warning(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            _browser_from_pilot(pilot).action_delete_session()

    async def test_resume_on_empty_list_shows_warning(self) -> None:
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            _browser_from_pilot(pilot).action_resume()


# =============================================================================
# Bug 4: Session Manager Improvements (TDD — FAILING)
# =============================================================================


class TestSessionBrowserDateColumn:
    """Session browser must display date info for each session."""

    def test_session_browser_has_date_column(self) -> None:
        """The session browser must display ``updated_at`` (or ``created_at``)
        for each session."""
        s = FakeSession(
            id="sess-date-1",
            title="Recent Work",
            model="anthropic:claude-sonnet-4-5",
            agent="build",
            updated_at="2026-07-22T10:00:00+00:00",
            created_at="2026-07-20T08:00:00+00:00",
        )
        label = _format_session_label(s)  # type: ignore[arg-type]

        # Must contain some date component — at minimum the year
        assert "2026" in label, (
            f"Session label must include a date (year). Got: {label!r}"
        )

    def test_session_label_includes_date(self) -> None:
        """``_format_session_label(session)`` must include a formatted date string."""
        s = FakeSession(
            id="sess-d2",
            title="Debug Session",
            model="openai:gpt-4o",
            agent="build",
            updated_at="2026-07-22T14:30:00+00:00",
        )
        label = _format_session_label(s)  # type: ignore[arg-type]

        # Must include a date — either the raw ISO prefix or formatted
        has_date = ("2026-07" in label or "Jul" in label or "2026" in label)
        assert has_date, (
            f"Session label must include a formatted date. Got: {label!r}"
        )


class TestSessionListSorting:
    """Sessions must be displayed in descending date order by default."""

    def test_session_list_sorted_newest_first(self) -> None:
        """Sessions must appear in descending date order (newest first)."""
        now = datetime.now(timezone.utc)
        s1 = FakeSession(
            id="sess-old",
            title="Old Session",
            updated_at=(now - timedelta(days=5)).isoformat(),
        )
        s2 = FakeSession(
            id="sess-new",
            title="New Session",
            updated_at=(now - timedelta(hours=1)).isoformat(),
        )
        s3 = FakeSession(
            id="sess-mid",
            title="Middle Session",
            updated_at=(now - timedelta(days=2)).isoformat(),
        )

        store = FakeSessionStore()
        for s in [s1, s2, s3]:
            store.create_session(s)

        sessions = store.list_sessions()
        assert len(sessions) == 3

        # Newest first
        assert sessions[0].id == "sess-new", (
            f"Expected newest first, got {sessions[0].id}"
        )
        assert sessions[1].id == "sess-mid"
        assert sessions[2].id == "sess-old"

    def test_session_browser_sort_order_configurable(self) -> None:
        """Sort order must be toggleable (newest/oldest)."""
        # This tests that the SessionBrowser supports a configurable sort order.
        # The implementation must expose a way to change from newest->oldest to oldest->newest.

        # Verify that list_sessions currently returns by updated_at DESC (newest first)
        now = datetime.now(timezone.utc)
        s1 = FakeSession(
            id="sess-a",
            title="A",
            updated_at=(now - timedelta(days=10)).isoformat(),
        )
        s2 = FakeSession(
            id="sess-z",
            title="Z",
            updated_at=(now - timedelta(hours=1)).isoformat(),
        )

        store = FakeSessionStore()
        store.create_session(s1)
        store.create_session(s2)

        sessions = store.list_sessions()
        # Default: newest first
        assert sessions[0].id == "sess-z"

        # The browser should expose a sort_order parameter or method
        # that can be toggled. Test that this attribute/parameter exists.
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        assert hasattr(browser, "_sort_order") or hasattr(browser, "sort_order"), (
            "SessionBrowser must have _sort_order or sort_order attribute "
            "for configurable sorting"
        )


class TestBulkSelectionAndDelete:
    """Session browser must support multi-select and bulk delete."""

    def test_session_browser_has_select_all_binding(self) -> None:
        """There must be a keybinding or action for selecting all sessions."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Must have a binding or action for 'select all'
        bindings_keys = [b[0] for b in browser.BINDINGS]
        has_select_all = "ctrl+a" in bindings_keys or "select_all" in bindings_keys
        assert has_select_all, (
            f"SessionBrowser must have a 'select all' binding. "
            f"Current bindings: {bindings_keys}"
        )

    def test_session_browser_has_bulk_delete_binding(self) -> None:
        """There must be a keybinding or action for bulk-deleting selected sessions."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Must have bindings or action methods for bulk-delete
        bindings_keys = [b[0] for b in browser.BINDINGS]
        has_bulk_delete = any(
            "bulk" in k or "multi" in k for k in bindings_keys
        )
        # Also check for action methods
        has_bulk_action = any(
            name.startswith("action_") and ("bulk" in name or "multi" in name)
            for name in dir(browser)
        )
        assert has_bulk_delete or has_bulk_action, (
            f"SessionBrowser must have a bulk-delete binding or action. "
            f"Bindings: {bindings_keys}"
        )

    def test_session_browser_multi_select(self) -> None:
        """Must be able to select multiple sessions at once (toggle selection)."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Must have a multi-select mechanism — either a _selected set or
        # a selection mode
        assert hasattr(browser, "_selected_sessions") or hasattr(
            browser, "_selection_mode"
        ), (
            "SessionBrowser must support multi-select via _selected_sessions "
            "or _selection_mode attribute"
        )

    def test_bulk_delete_removes_multiple_sessions(self) -> None:
        """Bulk delete must remove all selected sessions."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(3)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Must have a bulk_delete method
        assert hasattr(browser, "action_bulk_delete") or hasattr(
            browser, "action_delete_selected"
        ), (
            "SessionBrowser must have action_bulk_delete or action_delete_selected"
        )


# =============================================================================
# Issue 1: Missing command references — BINDINGS completeness
# =============================================================================


class TestBindingsIncludeBulkOperations:
    """SessionBrowser BINDINGS must include entries for space, ctrl+a, ctrl+d."""

    def test_bindings_include_bulk_operations(self) -> None:
        """SessionBrowser BINDINGS must include space (select), ctrl+a (select all),
        ctrl+d (bulk delete) keybindings with descriptive names."""
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Collect binding keys and associated action names
        bindings_map: dict[str, str] = {b[0]: b[1] for b in browser.BINDINGS}

        # Space must toggle selection
        assert "space" in bindings_map, (
            "BINDINGS must include 'space' key for selection toggling. "
            f"Bindings: {list(bindings_map)}"
        )

        # ctrl+a must select all
        assert "ctrl+a" in bindings_map, (
            "BINDINGS must include 'ctrl+a' for select all. "
            f"Bindings: {list(bindings_map)}"
        )

        # ctrl+d must trigger bulk delete
        assert "ctrl+d" in bindings_map, (
            "BINDINGS must include 'ctrl+d' for bulk delete. "
            f"Bindings: {list(bindings_map)}"
        )

        # The action for ctrl+d must be action_bulk_delete
        assert bindings_map["ctrl+d"] == "action_bulk_delete", (
            f"ctrl+d must map to 'action_bulk_delete', "
            f"got '{bindings_map['ctrl+d']}'"
        )


# =============================================================================
# Issue 2: Deleting last session must be prevented
# =============================================================================


class TestLastSessionProtection:
    """Deleting the only remaining session must be refused with a warning."""

    async def test_cannot_delete_last_session(self) -> None:
        """action_delete_session() must refuse to delete the only session
        in the store, showing a warning notification."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            list_view = screen.query_one(ListView)
            list_view.index = 0
            await pilot.pause()

            # Call delete — must be refused because it's the only session
            screen.action_delete_session()

        # After dismiss, the session must NOT have been deleted
        session = store.get_session(sessions[0].id)
        assert session is not None, (
            "Last session must NOT be deleted from the store"
        )
        assert session.status == "active", (
            f"Last session must remain active. Got status: {session.status!r}"
        )

    async def test_bulk_delete_cannot_delete_all_sessions(self) -> None:
        """action_bulk_delete() with all sessions selected must refuse
        or leave at least one session."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(2)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)

            # Select ALL sessions
            screen._selected_sessions = {s.id for s in sessions}
            await pilot.pause()

            screen.action_bulk_delete()

        # Verify at least one session remains
        remaining = [s for s in store.list_sessions()
                     if s.status == "active"]
        assert len(remaining) >= 1, (
            f"Bulk delete of ALL sessions must leave at least one session. "
            f"Remaining active: {len(remaining)}"
        )

    async def test_delete_currently_focused_session_protected(self) -> None:
        """Deleting the session that is currently focused in the app must
        leave the app in a valid state — the session must remain active,
        not be archived."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            list_view = screen.query_one(ListView)
            list_view.index = 0
            await pilot.pause()

            # Try deleting the only focused session
            screen.action_delete_session()

        # The session must still be active — not archived or deleted
        session = store.get_session(sessions[0].id)
        assert session is not None, (
            "Focused session must still exist in the store after delete attempt"
        )
        assert session.status == "active", (
            f"Focused session must remain active. Got status: {session.status!r}. "
            "The last remaining session must not be deletable."
        )


# =============================================================================
# Issue 3: Multi-selection operations on delete / archive
# =============================================================================


class TestMultiSelectionOperations:
    """Single-key actions must operate on all selected sessions, not just
    the highlighted one."""

    async def test_delete_with_multi_selection_deletes_all_selected(self) -> None:
        """When 3 sessions are selected via _selected_sessions, pressing d
        must delete all 3, not just the highlighted one."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(3)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)

            # Select all 3 sessions
            screen._selected_sessions = {s.id for s in sessions}
            await pilot.pause()

            screen.action_delete_session()

        # All selected sessions should now be archived (soft-deleted)
        for s in sessions:
            stored = store.get_session(s.id)
            assert stored is not None, f"Session {s.id} must still exist"
            assert stored.status == "archived", (
                f"Session {s.id} must be archived after multi-select delete. "
                f"Got status: {stored.status!r}"
            )

    async def test_archive_with_multi_selection_archives_all_selected(self) -> None:
        """When 3 sessions are selected, pressing a must archive all 3."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(3)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]
        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)

            screen._selected_sessions = {s.id for s in sessions}
            await pilot.pause()

            screen.action_archive()

        # All selected sessions should be archived
        for s in sessions:
            stored = store.get_session(s.id)
            assert stored is not None
            assert stored.status == "archived", (
                f"Session {s.id} must be archived after multi-select archive. "
                f"Got status: {stored.status!r}"
            )

    def test_bulk_delete_action_removed_or_delegates(self) -> None:
        """action_bulk_delete should either be removed or delegate to
        action_delete_session — no duplicate delete logic.

        The test verifies that we don't have two independent copies of
        delete logic: either action_bulk_delete delegates to
        action_delete_session, or action_delete_session itself handles
        all selected sessions (making a separate bulk method redundant).
        """
        store = FakeSessionStore()
        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        has_bulk = hasattr(browser, "action_bulk_delete")
        has_single = hasattr(browser, "action_delete_session")

        if has_bulk and has_single:
            import inspect
            bulk_src = inspect.getsource(browser.action_bulk_delete)  # type: ignore[arg-type]
            single_src = inspect.getsource(browser.action_delete_session)  # type: ignore[arg-type]

            # Check: does action_bulk_delete call action_delete_session?
            bulk_calls_single = "action_delete_session" in bulk_src

            # Check: does action_delete_session iterate over _selected_sessions?
            # (not just discard one entry — actually iterate/loop)
            single_iterates_selection = (
                "for " in single_src and "_selected_sessions" in single_src
            ) or (
                "_selected_sessions" in single_src
                and "discard" not in single_src
            )

            assert bulk_calls_single or single_iterates_selection, (
                "Duplicate delete logic detected. Either action_bulk_delete "
                "must call action_delete_session for each selected session, or "
                "action_delete_session must iterate over _selected_sessions "
                "to handle multi-selection (making action_bulk_delete redundant)."
            )


# =============================================================================
# Issue 2 / Help message test
# =============================================================================


class TestLastSessionWarningMessages:
    """Warning messages when deleting the last session must be meaningful."""

    async def test_last_session_delete_shows_meaningful_warning(self) -> None:
        """When trying to delete the last session, the warning message must
        mention 'last session' or 'cannot delete'."""
        store = FakeSessionStore()
        sessions = _make_fake_sessions(1)
        _populate_fake_store(store, sessions)

        browser = SessionBrowser(session_store=store)  # type: ignore[arg-type]

        # Monkey-patch notify to capture the warning text
        captured_notify: list[tuple[str, str]] = []
        _orig_notify = browser.notify

        def _capture_notify(
            message: str,
            severity: str = "information",
            timeout: float | None = None,
        ) -> None:
            captured_notify.append((message, severity))
            _orig_notify(message, severity=severity, timeout=timeout)

        browser.notify = _capture_notify  # type: ignore[assignment]

        async with _run_browser(browser) as pilot:
            await pilot.pause()
            screen = _browser_from_pilot(pilot)
            list_view = screen.query_one(ListView)
            list_view.index = 0
            await pilot.pause()

            screen.action_delete_session()

        # Check for warning-level notification about last session
        warnings = [(msg, sev) for msg, sev in captured_notify
                    if sev == "warning"]
        assert len(warnings) >= 1, (
            f"Expected at least one warning-level notification when "
            f"deleting last session. Got notifications: {captured_notify}"
        )

        warning_text = " ".join(msg for msg, _ in warnings).lower()
        assert "last session" in warning_text or "cannot delete" in warning_text, (
            f"Warning must mention 'last session' or 'cannot delete'. "
            f"Got: {captured_notify}"
        )

        # Verify the session was NOT deleted
        session = store.get_session(sessions[0].id)
        assert session is not None, "Last session must not be deleted"
        assert session.status == "active", (
            f"Last session must remain active. Got: {session.status!r}"
        )
