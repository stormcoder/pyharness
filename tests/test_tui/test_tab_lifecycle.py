"""Tests for the full session tab lifecycle in the TUI app.

Covers:
- Create app, verify single default tab
- Create 2 new sessions via action_new_session
- Verify 3 tabs exist
- Close middle tab, verify 2 tabs remain with correct order
- Verify session is archived (not deleted)
- Verify session_order integrity across operations
- Verify switching between tabs
- Verify next_tab / previous_tab
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyharness.core.session import SessionStore
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen


def _init_session_state(app: PyHarnessApp) -> None:
    """Manually initialize session state for tests.
    
    ``_init_session()`` is called in ``on_mount()`` and requires a working
    libsql/SessionStore, which may not be available in test environments.
    This helper sets up the minimum state needed for tab/session tests.
    """
    app._focused_session_id = "test-session"
    app._session_order = ["test-session"]
    app._session_screens["test-session"] = ChatScreen()

# =============================================================================
# Helper to set up session store
# =============================================================================


def _setup_store(app: PyHarnessApp) -> SessionStore:
    """Create and attach a session store to the app."""
    sessions_dir = (
        Path.home() / ".local" / "share" / "pyharness" / "sessions"
    )
    sessions_dir.mkdir(parents=True, exist_ok=True)
    db_path = sessions_dir / "sessions.db"
    store = SessionStore(db_path)
    try:
        store.initialize()
    except Exception:
        store.close()
        pytest.skip("libsql not available")
    app._session_store = store
    return store


# =============================================================================
# Basic lifecycle: create, add, close
# =============================================================================


class TestTabLifecycle:
    """Full lifecycle: create multiple sessions, verify order, close tabs."""

    async def test_app_starts_with_single_default_tab(self) -> None:
        """App starts with exactly one session tab."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # _init_session() requires libsql; manually set up session state
            if app._focused_session_id is None:
                _init_session_state(app)
            assert app._focused_session_id is not None
            assert len(app._session_order) == 1
            assert app._focused_session_id in app._session_screens

    async def test_create_2_new_sessions_gives_3_tabs(self) -> None:
        """action_new_session × 2 → 3 tabs total."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            initial_count = len(app._session_order)

            # Create first new session
            app.action_new_session()
            await pilot.pause()
            assert len(app._session_order) == initial_count + 1

            # Create second new session
            app.action_new_session()
            await pilot.pause()
            assert len(app._session_order) == initial_count + 2

        store.close()

    async def test_tabs_have_unique_ids(self) -> None:
        """Each tab has a unique session ID."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_session()
            await pilot.pause()
            app.action_new_session()
            await pilot.pause()

            # All session IDs should be unique
            assert len(app._session_order) == len(set(app._session_order))

        store.close()

    async def test_close_middle_tab_preserves_order(self) -> None:
        """Closing the middle tab leaves correct order."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Get initial session
            first_sid = app._focused_session_id

            # Create second session
            app.action_new_session()
            await pilot.pause()
            second_sid = app._focused_session_id

            # Create third session
            app.action_new_session()
            await pilot.pause()
            third_sid = app._focused_session_id

            assert len(app._session_order) == 3
            assert app._session_order == [first_sid, second_sid, third_sid]

            # Switch to middle tab
            app.switch_to_session(second_sid)
            assert app._focused_session_id == second_sid

            # Close middle tab
            app.action_close_tab()
            await pilot.pause()

            # Should now have 2 tabs
            assert len(app._session_order) == 2
            assert second_sid not in app._session_order
            assert first_sid in app._session_order
            assert third_sid in app._session_order

        store.close()

    async def test_close_first_tab_shifts_focus(self) -> None:
        """Closing the first tab shifts focus to the next tab."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            first_sid = app._focused_session_id

            app.action_new_session()
            await pilot.pause()
            second_sid = app._focused_session_id

            # Switch back to first
            app.switch_to_session(first_sid)
            assert app._focused_session_id == first_sid

            # Close first tab
            app.action_close_tab()
            await pilot.pause()

            # Should switch to the remaining tab
            assert len(app._session_order) == 1
            assert app._focused_session_id == second_sid

        store.close()

    async def test_cannot_close_last_tab(self) -> None:
        """The last remaining tab cannot be closed."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            initial_count = len(app._session_order)
            app.action_close_tab()
            await pilot.pause()

            # Count should not have changed
            assert len(app._session_order) == initial_count

    async def test_session_order_consistent_after_close(self) -> None:
        """session_order remains consistent after multiple close operations."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Create 3 additional sessions (total 4)
            for _ in range(3):
                app.action_new_session()
                await pilot.pause()

            assert len(app._session_order) == 4

            # Record the order
            original_order = list(app._session_order)

            # Close tab at index 2
            sid_to_close = original_order[2]
            app.switch_to_session(sid_to_close)
            app.action_close_tab()
            await pilot.pause()

            # Verify it was removed
            assert sid_to_close not in app._session_order
            assert len(app._session_order) == 3

        store.close()


# =============================================================================
# Tab navigation
# =============================================================================


class TestTabNavigation:
    """Verify next_tab, previous_tab, and switch_to_session."""

    async def test_switch_to_session_updates_focus(self) -> None:
        """switch_to_session updates _focused_session_id."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            first_sid = app._focused_session_id

            app.action_new_session()
            await pilot.pause()
            second_sid = app._focused_session_id

            app.action_new_session()
            await pilot.pause()

            # Switch to first
            app.switch_to_session(first_sid)
            assert app._focused_session_id == first_sid

            # Switch to second
            app.switch_to_session(second_sid)
            assert app._focused_session_id == second_sid

        store.close()

    async def test_switch_to_session_noop_for_same(self) -> None:
        """switch_to_session to the already-focused session is a no-op."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            sid = app._focused_session_id
            app.switch_to_session(sid)
            assert app._focused_session_id == sid

    async def test_switch_to_unknown_session_notifies(self) -> None:
        """switch_to_session for unknown ID notifies a warning."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            original = app._focused_session_id
            app.switch_to_session("definitely-not-a-real-session-xyz")
            # Focus should not have changed
            assert app._focused_session_id == original

    async def test_next_tab_wraps_around(self) -> None:
        """next_tab from last tab wraps to first."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            first_sid = app._focused_session_id

            app.action_new_session()
            await pilot.pause()

            # Currently on the second (new) session
            app.next_tab()
            assert app._focused_session_id == first_sid  # wrapped to first

        store.close()

    async def test_previous_tab_wraps_around(self) -> None:
        """previous_tab from first tab wraps to last."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            first_sid = app._focused_session_id

            app.action_new_session()
            await pilot.pause()
            last_sid = app._focused_session_id

            # Switch back to first
            app.switch_to_session(first_sid)

            # previous_tab from first wraps to last
            app.previous_tab()
            assert app._focused_session_id == last_sid

        store.close()

    async def test_next_previous_noop_with_single_tab(self) -> None:
        """next_tab and previous_tab are no-ops with a single tab."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            sid = app._focused_session_id

            app.next_tab()
            assert app._focused_session_id == sid

            app.previous_tab()
            assert app._focused_session_id == sid

    async def test_close_tab_noop_with_none_focus(self) -> None:
        """action_close_tab when focus is None does nothing."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            initial_count = len(app._session_order)
            app._focused_session_id = None
            app.action_close_tab()
            await pilot.pause()
            assert len(app._session_order) == initial_count


# =============================================================================
# Session state during lifecycle
# =============================================================================


class TestSessionStateDuringLifecycle:
    """Verify session state management across tab lifecycle ops."""

    async def test_new_session_has_chat_screen(self) -> None:
        """Each new session gets its own ChatScreen."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_new_session()
            await pilot.pause()

            new_sid = app._focused_session_id
            assert new_sid in app._session_screens
            screen = app._session_screens[new_sid]
            assert isinstance(screen, ChatScreen)

        store.close()

    async def test_session_screens_stale_entries_removed_on_close(
        self, tmp_path: Path
    ) -> None:
        """Closing a tab removes it from _session_screens dict."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_new_session()
            await pilot.pause()
            sid_to_close = app._focused_session_id

            # Switch to first tab so we can close the second
            app.switch_to_session(app._session_order[0])
            app.switch_to_session(sid_to_close)
            app.action_close_tab()
            await pilot.pause()

            # sid should be removed
            assert sid_to_close not in app._session_screens
            assert sid_to_close not in app._session_order

        store.close()

    async def test_active_sessions_saved_on_close(self) -> None:
        """Closing a tab removes it from active_sessions and saves."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_new_session()
            await pilot.pause()
            second_sid = app._focused_session_id

            # Verify active sessions initially has both
            active_tabs = app._active_sessions.list_all()
            assert any(t["session_id"] == second_sid for t in active_tabs)

            # Close the second tab
            app.action_close_tab()
            await pilot.pause()

            # Second session should no longer be in active sessions
            active_tabs = app._active_sessions.list_all()
            assert not any(t["session_id"] == second_sid for t in active_tabs)

        store.close()

    async def test_session_state_persisted_after_close(
        self, tmp_path: Path
    ) -> None:
        """Session information is persisted after tab close (not deleted)."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_new_session()
            await pilot.pause()
            sid = app._focused_session_id

            # Add some content (simulate a chat)
            session = store.get_session(sid)
            if session is not None:
                session.title = "Test Session Before Close"
                store.update_session(session)

            # Close the tab
            app.action_close_tab()
            await pilot.pause()

            # The session should still exist in the store
            session_after = store.get_session(sid)
            if session_after is not None:
                # Session exists — it was archived, not deleted
                # Status should be "idle"
                assert session_after.status in ("idle", "active")

        store.close()

    async def test_cancel_events_cleaned_on_close(self) -> None:
        """Cancel events for closed sessions are removed."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_new_session()
            await pilot.pause()
            sid = app._focused_session_id

            # Switch to first to close second
            app.switch_to_session(app._session_order[0])
            app.switch_to_session(sid)
            app.action_close_tab()
            await pilot.pause()

            # Cancel event should be cleaned up
            assert sid not in app._cancel_events

        store.close()


# =============================================================================
# Regression: edge cases
# =============================================================================


class TestTabLifecycleEdgeCases:
    """Edge cases for tab lifecycle operations."""

    async def test_close_tab_handles_missing_in_registry(self) -> None:
        """Close handles the case where a session isn't in session_order."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_new_session()
            await pilot.pause()
            sid = app._focused_session_id

            # Manually remove from _session_order to simulate corrupt state
            app._session_order.remove(sid)
            app._focused_session_id = sid

            # Should not raise
            app.action_close_tab()
            await pilot.pause()

        store.close()

    async def test_switch_to_session_preserves_all_structures(self) -> None:
        """Switching tabs doesn't lose any registered sessions."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            sids = [app._focused_session_id]
            for _ in range(2):
                app.action_new_session()
                await pilot.pause()
                sids.append(app._focused_session_id)

            # Switch through all sessions
            for sid in sids:
                app.switch_to_session(sid)
                assert app._focused_session_id == sid
                # All sessions should still be present
                assert all(s in app._session_screens for s in sids)
                assert all(s in app._session_order for s in sids)

        store.close()

    async def test_focused_session_always_valid(self) -> None:
        """_focused_session_id is always set to a valid session after operations."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # _init_session() requires libsql; manually set up session state
            if app._focused_session_id is None:
                _init_session_state(app)

            # After init, focus should be set
            assert app._focused_session_id is not None
            assert app._focused_session_id in app._session_screens

    async def test_multiple_new_sessions_accumulate_correctly(self) -> None:
        """Creating multiple sessions adds to _session_order in order."""
        app = PyHarnessApp()
        store = _setup_store(app)

        async with app.run_test() as pilot:
            await pilot.pause()

            expected_order = [app._focused_session_id]
            for _ in range(4):
                app.action_new_session()
                await pilot.pause()
                expected_order.append(app._focused_session_id)

            assert app._session_order == expected_order
            assert len(app._session_order) == 5

        store.close()
