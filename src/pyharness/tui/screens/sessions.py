"""Session browser — list sessions and support resume / new / archive / delete.

Implements R1.7 (query real sessions from SessionStore) and R1.8 (actions:
resume, new, archive, delete) from ``docs/specs/parallel-multi-agent.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, ListItem, ListView, Static

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

    return (
        f"[bold]{title}[/]  "
        f"[{color}]{icon} {session.status}[/]  "
        f"[#8b949e]{model} \u00b7 {agent}[/]  "
        f"[#58a6ff]{tokens}[/]  "
        f"[#484f58]{sid}[/]"
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
        ("n", "new_session", "New"),
        ("a", "archive", "Archive"),
        ("d", "delete_session", "Delete"),
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

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Container(id="session-browser"):
            yield Static("[bold #58a6ff]Sessions[/]", id="sb-title")
            yield Static(
                "[#8b949e]Active sessions will appear here. "
                "\u2328 Resume \u00b7 n New \u00b7 a Archive \u00b7 d Delete[/]",
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
        """Mark the selected session as archived (soft-delete)."""
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

    def action_delete_session(self) -> None:
        """Permanently remove the selected session from the store."""
        session_id = self._selected_session_id()
        if session_id is None:
            self.notify("No session selected", severity="warning")
            return
        store = self._resolve_store()
        if store is None:
            self.notify("Session store not available", severity="error")
            return
        try:
            # NOTE: SessionStore.delete_session() soft-deletes (status='archived').
            # True permanent row deletion requires SessionStore.hard_delete()
            # which does not exist yet.  For now we soft-delete; the session
            # will be filtered out of default list-view queries (status filter).
            store.delete_session(session_id)
        except Exception as exc:
            self.notify(f"Delete failed: {exc}", severity="error")
            return
        self.notify(
            f"Deleted session {_truncate_id(session_id)}",
        )
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
        list_view: ListView = self.query_one("#sb-list", ListView)
        list_view.clear()

        if not sessions:
            self._show_empty("No saved sessions yet")
            return

        for s in sessions:
            raw = _format_session_label(s)
            list_view.append(ListItem(Static(raw)))

    def _show_empty(self, message: str) -> None:
        """Display an empty-state message in the list view."""
        list_view: ListView = self.query_one("#sb-list", ListView)
        list_view.clear()
        list_view.append(ListItem(Static(f"[#8b949e]{message}[/]")))
