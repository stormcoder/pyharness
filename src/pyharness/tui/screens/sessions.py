"""Session browser — list sessions and support resume / new / archive / delete.

Implements R1.7 (query real sessions from SessionStore) and R1.8 (actions:
resume, new, archive, delete) from ``docs/specs/parallel-multi-agent.md``.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, ListItem, ListView, Static

from pyharness.core.session import Session

if TYPE_CHECKING:
    from pyharness.core.session import SessionStore

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[str, str] = {
    "active": "\u25cf",  # ●
    "idle": "\u25cb",  # ○
    "compacted": "\u25d1",  # ◑
    "archived": "\u25c7",  # ◇
}

_STATUS_COLORS: dict[str, str] = {
    "active": "#3fb950",
    "idle": "#8b949e",
    "compacted": "#d29922",
    "archived": "#6e7681",
}


def _truncate_id(session_id: str, width: int = 12) -> str:
    """Truncate a session ID for compact display."""
    if len(session_id) <= width:
        return session_id
    return session_id[:width] + "\u2026"


def _format_tokens(count: int) -> str:
    """Human-readable token count."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M tok"
    if count >= 1_000:
        return f"{count // 1_000}k tok"
    return f"{count} tok"


def _format_session_label(session: Session) -> str:
    """Build a compact, styled label for a ListView item."""
    sid = _truncate_id(session.id)
    icon = _STATUS_ICONS.get(session.status, "?")
    color = _STATUS_COLORS.get(session.status, "#8b949e")
    tokens = _format_tokens(session.total_tokens)
    title = (session.title or "Untitled")[:50]
    model = session.model or "\u2014"
    agent = session.agent or "build"
    updated = session.updated_at[:10] if session.updated_at else ""

    return (
        f"[bold]{title}[/]  "
        f"[{color}]{icon} {session.status}[/]  "
        f"[#8b949e]{model} \u00b7 {agent}[/]  "
        f"[#58a6ff]{tokens}[/]  "
        f"[#484f58]{sid}[/]  "
        f"[#6e7681]{updated}[/]"
    )


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class SessionBrowser(Screen[object]):
    """Browse, resume, archive, and delete chat sessions.

    Pushes onto the screen stack via :meth:`PyHarnessApp.action_sessions`.
    Dismiss values:
      - ``str`` session_id — resume that session
      - ``"__new__"`` — create a new session
      - ``None`` — cancelled (Escape)
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("enter", "resume", "Resume"),
        ("r", "rename", "Rename"),
        ("n", "new_session", "New"),
        ("a", "archive", "Archive"),
        ("d", "delete_session", "Delete"),
        ("ctrl+a", "select_all", "All"),
        ("ctrl+d", "action_bulk_delete", "Bulk Del"),
        ("space", "toggle_selection", "Select"),
    ]

    _sessions: list[Session]

    def __init__(
        self,
        session_store: SessionStore | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._session_store: SessionStore | None = session_store
        self._sessions: list[Session] = []
        self._selected_sessions: set[str] = set()
        self._sort_order: str = "newest"

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Container(id="session-browser"):
            yield Static("[bold #58a6ff]Sessions[/]", id="sb-title")
            yield Static(
                "[#8b949e]Active sessions will appear here. "
                "\u2328 Resume \u00b7 n New \u00b7 a Archive \u00b7 d Delete \u00b7 r Rename[/]",
                id="sb-status",
            )
            yield ListView(id="sb-list")
            with Container(id="sb-actions"):
                yield Button(
                    "New Session",
                    id="btn-new",
                    variant="primary",
                )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._refresh_list()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_dismiss(self, result: object = None) -> None:
        self.dismiss()

    def action_resume(self) -> None:
        """Dismiss with the selected session_id so the caller can resume it."""
        session_id = self._selected_session_id()
        if session_id is None:
            self.notify("No session selected — create one with [bold]n[/] New",
                        severity="warning")
            return
        self.dismiss(session_id)

    def action_new_session(self) -> None:
        """Signal the caller to create a new session and switch to it."""
        self.dismiss("__new__")

    def action_archive(self) -> None:
        """Mark selected sessions as archived (soft-delete).

        If multiple sessions are selected via ``_selected_sessions``,
        archive all of them.  Otherwise archive the highlighted session.
        """
        # If sessions are multi-selected, archive all selected
        if self._selected_sessions:
            self._action_bulk_archive()
            return

        # Otherwise, single-session archive
        session_id = self._selected_session_id()
        if session_id is None:
            self.notify("No session selected", severity="warning")
            return
        store = self._resolve_store()
        if store is None:
            self.notify("Session store not available", severity="error")
            return
        try:
            store.delete_session(session_id)
        except Exception as exc:
            self.notify(f"Archive failed: {exc}", severity="error")
            return
        self.notify(
            f"Archived session {_truncate_id(session_id)}",
        )
        self._refresh_list()

    def action_rename(self) -> None:
        """Rename the selected session."""
        session_id = self._selected_session_id()
        if session_id is None:
            self.notify("No session selected", severity="warning")
            return

        class RenameModal(ModalScreen[str | None]):
            def compose(self) -> ComposeResult:
                with Vertical(id="rename-dialog"):
                    yield Static("Rename Session", id="rename-title")
                    yield Input(
                        placeholder="Enter new session name...",
                        id="rename-input",
                    )
                    with Container(id="rename-actions"):
                        yield Button("Rename", variant="primary", id="rename-btn")
                        yield Button("Cancel", id="cancel-btn")

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "rename-btn":
                    inp = self.query_one("#rename-input", Input)
                    self.dismiss(inp.value)
                else:
                    self.dismiss(None)

        self.app.push_screen(
            RenameModal(),
            callback=lambda new_title: self._do_rename(session_id, new_title),
        )

    def _do_rename(self, session_id: str, new_title: str | None) -> None:
        """Validate and persist a session rename."""
        if new_title is None:
            return  # cancelled
        new_title = new_title.strip()
        if not new_title:
            with contextlib.suppress(Exception):
                self.notify("Session name cannot be empty", severity="warning")
            return

        store = self._resolve_store()
        if store is None:
            with contextlib.suppress(Exception):
                self.notify("Session store not available", severity="error")
            return

        try:
            session = store.get_session(session_id)
            if session is None:
                with contextlib.suppress(Exception):
                    self.notify("Session not found", severity="error")
                return
            session.title = new_title
            store.update_session(session)
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.notify(f"Rename failed: {exc}", severity="error")
            return

        # Update tab bar if available
        if hasattr(self, "tab_bar") and self.tab_bar is not None:
            with contextlib.suppress(Exception):
                self.tab_bar.update_title(session_id, new_title)

        with contextlib.suppress(Exception):
            self.notify(f"Renamed to '{new_title}'")
        with contextlib.suppress(Exception):
            self._refresh_list()

    def _action_bulk_archive(self) -> None:
        """Archive all multi-selected sessions."""
        store = self._resolve_store()
        if store is None:
            self.notify("Session store not available", severity="error")
            return
        count = 0
        for sid in list(self._selected_sessions):
            try:
                store.delete_session(sid)  # soft-delete = archive
                count += 1
            except Exception:
                pass
        self._selected_sessions.clear()
        self.notify(f"Archived {count} session(s)")
        self._refresh_list()

    def action_delete_session(self) -> None:
        """Permanently remove selected sessions from the store.

        If multiple sessions are selected via ``_selected_sessions``,
        delete all of them.  Otherwise delete the highlighted session.
        Refuses to delete the **last remaining session** (single session
        only — multi-select bypasses this guard for bulk workflows).
        """
        # If sessions are multi-selected, delete all selected
        if self._selected_sessions:
            store = self._resolve_store()
            if store is None:
                self.notify("Session store not available", severity="error")
                return
            count = 0
            for sid in list(self._selected_sessions):
                try:
                    if hasattr(store, "hard_delete"):
                        store.hard_delete(sid)
                    else:
                        store.delete_session(sid)
                    count += 1
                except Exception:
                    pass
            self._selected_sessions.clear()
            self.notify(f"Deleted {count} session(s)")
            self._refresh_list()
            return

        # Otherwise, single-session delete
        session_id = self._selected_session_id()
        if session_id is None:
            self.notify("No session selected", severity="warning")
            return
        store = self._resolve_store()
        if store is None:
            self.notify("Session store not available", severity="error")
            return

        # Guard: never delete the last remaining session (single only)
        try:
            all_sessions = store.list_sessions()
        except Exception:
            all_sessions = []
        if len(all_sessions) <= 1:
            self.notify(
                "Cannot delete the last session",
                severity="warning",
            )
            return

        # Guard: refuse to delete the currently focused session
        if hasattr(self.app, "_focused_session_id") and (
            session_id == self.app._focused_session_id  # type: ignore[union-attr]
        ):
            self.notify(
                "Cannot delete the focused session — switch to another session first",
                severity="warning",
            )
            return

        try:
            # Use hard_delete when available, fall back to soft-delete
            if hasattr(store, "hard_delete"):
                store.hard_delete(session_id)
            else:
                store.delete_session(session_id)
        except Exception as exc:
            self.notify(f"Delete failed: {exc}", severity="error")
            return
        self._selected_sessions.discard(session_id)
        self.notify(
            f"Deleted session {_truncate_id(session_id)}",
        )
        self._refresh_list()

    def action_select_all(self) -> None:
        """Select all visible sessions."""
        if not self._sessions:
            self.notify("No sessions to select", severity="warning")
            return
        for s in self._sessions:
            self._selected_sessions.add(s.id)
        self._refresh_list()

    def action_bulk_delete(self) -> None:
        """Permanently delete all selected sessions.

        Refuses if the selection would delete **every** session in the store.
        """
        if not self._selected_sessions:
            self.notify("No sessions selected — press Space to select", severity="warning")
            return
        store = self._resolve_store()
        if store is None:
            self.notify("Session store not available", severity="error")
            return

        # Guard: cannot delete ALL sessions
        try:
            all_sessions = store.list_sessions()
        except Exception:
            all_sessions = []
        if len(self._selected_sessions) >= len(all_sessions):
            self.notify(
                "Cannot delete all sessions",
                severity="warning",
            )
            return

        count = 0
        for sid in list(self._selected_sessions):
            try:
                if hasattr(store, "hard_delete"):
                    store.hard_delete(sid)
                else:
                    store.delete_session(sid)
                count += 1
            except Exception:
                pass
        self._selected_sessions.clear()
        self.notify(f"Deleted {count} session(s)")
        self._refresh_list()

    def action_toggle_selection(self) -> None:
        """Toggle selection of the currently highlighted session."""
        session_id = self._selected_session_id()
        if session_id is None:
            return
        if session_id in self._selected_sessions:
            self._selected_sessions.discard(session_id)
        else:
            self._selected_sessions.add(session_id)
        self._refresh_list()

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self.action_new_session()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_store(self) -> SessionStore | None:
        """Return a SessionStore, preferring explicit injection over app attr."""
        if self._session_store is not None:
            return self._session_store
        store = getattr(self.app, "_session_store", None)
        if store is None:
            return None
        return store

    def _selected_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted row, or None."""
        list_view: ListView = self.query_one("#sb-list", ListView)
        idx: int | None = list_view.index
        if idx is None or idx < 0 or idx >= len(self._sessions):
            return None
        return self._sessions[idx].id

    def _refresh_list(self) -> None:
        """Reload sessions from the store and repopulate the ListView."""
        store = self._resolve_store()
        if store is None:
            self._sessions = []
            self._show_empty("Session store not connected")
            return

        try:
            sessions = store.list_sessions()
        except Exception:
            sessions = []

        self._sessions = list(sessions)

        # Sort by updated_at based on _sort_order preference
        if self._sort_order == "newest":
            self._sessions.sort(key=lambda s: s.updated_at or "", reverse=True)
        else:
            self._sessions.sort(key=lambda s: s.updated_at or "")

        list_view: ListView = self.query_one("#sb-list", ListView)
        list_view.clear()

        # Get existing ListItem children (may have lingered from prior refresh)
        existing_items = [
            c for c in list_view.children if isinstance(c, ListItem)
        ]

        if not sessions:
            # Remove lingering items and show empty state
            for item in existing_items:
                item._detach()
            self._show_empty("No saved sessions yet")
            return

        # Remove lingering items that exceed the new count
        new_count = len(self._sessions)
        for i in range(new_count, len(existing_items)):
            existing_items[i]._detach()

        for i, s in enumerate(self._sessions):
            raw = _format_session_label(s)
            # Highlight selected sessions
            if s.id in self._selected_sessions:
                raw = f"[#d29922 on #3d2e00] {raw} [/]"

            if i < len(existing_items):
                # Update existing ListItem in-place
                statics = [
                    c for c in existing_items[i].children if isinstance(c, Static)
                ]
                if statics:
                    statics[0].update(raw)
            else:
                # Append new ListItem for additional sessions
                list_view.append(ListItem(Static(raw)))

    def _show_empty(self, message: str) -> None:
        """Display an empty-state message in the list view."""
        list_view: ListView = self.query_one("#sb-list", ListView)
        list_view.clear()
        for child in list(list_view.children):
            if isinstance(child, ListItem):
                child._detach()
        list_view.append(ListItem(Static(f"[#8b949e]{message}[/]")))
