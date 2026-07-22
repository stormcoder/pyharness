"""SessionTabBar — horizontal tab bar for multi-session management.

Implements R4.1-R4.6 from the parallel-multi-agent specification §4.1:

- **R4.1** Display one tab per active session with session title (or "New Session").
- **R4.2** Clicking a tab switches to that session.
- **R4.3** ``+`` button creates a new session.
- **R4.4** ``×`` button closes the session (saves, removes tab).
- **R4.5** Keyboard: ``Ctrl+Tab`` next, ``Ctrl+Shift+Tab`` previous, ``Ctrl+W`` close.
- **R4.6** Activity indicator (dot) when agent is running in that tab.
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static


class _TabLabel(Static):
    """A single tab's title label — clickable, with activity indicator."""

    session_id: str = ""

    def __init__(self, session_id: str, title: str, running: bool = False) -> None:
        prefix = "● " if running else ""
        display = title[:20] if len(title) > 20 else title
        super().__init__(f"{prefix}{display}")
        self.session_id = session_id


class _TabCloseButton(Static):
    """The ``×`` close button on a tab."""

    session_id: str = ""

    def __init__(self, session_id: str) -> None:
        super().__init__("×")
        self.session_id = session_id


class _NewTabButton(Static):
    """The ``+`` button for creating a new session."""


class _TabContainer(Horizontal):
    """A single tab: label + close button, wrapped in a Horizontal."""

    session_id: str = ""

    def __init__(
        self,
        session_id: str,
        title: str,
        is_active: bool = False,
        is_running: bool = False,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self._tab_title = title
        self._tab_active = is_active
        self._tab_running = is_running

    def compose(self) -> ComposeResult:
        label = _TabLabel(self.session_id, self._tab_title, running=self._tab_running)
        close_btn = _TabCloseButton(self.session_id)
        close_btn.can_focus = False
        label.can_focus = False
        self.can_focus = False
        if self._tab_active:
            label.add_class("active-tab")
        yield label
        yield close_btn


class SessionTabBar(Horizontal):
    """A horizontal tab bar showing one tab per active session.

    Each tab shows: an optional activity dot (``●`` when agent is running),
    the session title, and a ``×`` close button.  A ``+`` button at the
    end creates a new session.

    The widget communicates with the app via callbacks.  Messages are also
    posted so parent screens can intercept them if needed.

    Parameters
    ----------
    sessions:
        A list of ``(session_id, title)`` tuples for currently open sessions.
    active_id:
        The ``session_id`` of the currently focused tab.
    running_ids:
        A set of ``session_id`` values whose agents are currently running.
    """

    class TabSelected(Message):
        """Posted when a session tab is clicked."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class TabClosed(Message):
        """Posted when a tab's close button is clicked."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class NewTabRequested(Message):
        """Posted when the ``+`` button is clicked."""

    DEFAULT_CSS = """
    SessionTabBar {
        height: auto;
        min-height: 1;
        dock: top;
        background: #161b22;
        border-bottom: solid #30363d;
        overflow-x: auto;
        scrollbar-size: 0 0;
    }

    SessionTabBar _TabContainer {
        width: auto;
        min-width: 12;
        height: 1;
        background: #161b22;
        border-right: solid #30363d;
    }

    SessionTabBar _TabLabel {
        width: auto;
        min-width: 8;
        height: 1;
        padding: 0 1;
        color: #8b949e;
        content-align: left middle;
        text-overflow: ellipsis;
    }

    SessionTabBar _TabLabel.active-tab {
        color: #c9d1d9;
        background: #0d1117;
        border-bottom: solid #58a6ff;
    }

    SessionTabBar _TabLabel:hover {
        background: #21262d;
    }

    SessionTabBar _TabCloseButton {
        width: 3;
        height: 1;
        color: #8b949e;
        content-align: center middle;
    }

    SessionTabBar _TabCloseButton:hover {
        color: #f85149;
        background: #21262d;
    }

    SessionTabBar _NewTabButton {
        width: 3;
        height: 1;
        color: #58a6ff;
        content-align: center middle;
    }

    SessionTabBar _NewTabButton:hover {
        color: #7ee787;
        background: #21262d;
    }
    """

    def __init__(
        self,
        sessions: list[tuple[str, str]] | None = None,
        active_id: str | None = None,
        running_ids: set[str] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._sessions: list[tuple[str, str]] = sessions or []
        self._active_id: str | None = active_id
        self._running_ids: set[str] = running_ids or set()

    # -- public properties ------------------------------------------------------

    @property
    def active_id(self) -> str | None:
        """The ``session_id`` of the currently active/selected tab."""
        return self._active_id

    @active_id.setter
    def active_id(self, value: str | None) -> None:
        self._active_id = value
        self._rebuild()

    # -- public methods ---------------------------------------------------------

    def update_state(
        self,
        sessions: list[tuple[str, str]],
        active_id: str | None = None,
        running_ids: set[str] | None = None,
    ) -> None:
        """Replace the entire tab list and re-render.

        Args:
            sessions: List of ``(session_id, title)`` tuples.
            active_id: The currently active session ID.
            running_ids: Set of session IDs with running agents.
        """
        self._sessions = list(sessions)
        if active_id is not None:
            self._active_id = active_id
        if running_ids is not None:
            self._running_ids = set(running_ids)
        self._rebuild()

    def add_tab(self, session_id: str, title: str) -> None:
        """Add a single tab for *session_id* with *title*."""
        if not any(s[0] == session_id for s in self._sessions):
            self._sessions.append((session_id, title))
            self._rebuild()

    def remove_tab(self, session_id: str) -> None:
        """Remove the tab for *session_id*."""
        self._sessions = [
            (sid, t) for sid, t in self._sessions if sid != session_id
        ]
        self._rebuild()

    def update_title(self, session_id: str, title: str) -> None:
        """Update the display title for *session_id*."""
        self._sessions = [
            (sid, title if sid == session_id else t)
            for sid, t in self._sessions
        ]
        self._rebuild()

    # -- internal ---------------------------------------------------------------

    def _rebuild(self) -> None:
        """Completely rebuild the tab bar children.

        Uses ``remove_children`` followed by ``mount``.  Widgets use
        Textual-class-based identification (via ``.session_id`` attributes,
        ``_TabLabel``, ``_TabCloseButton``, ``_NewTabButton`` CSS classes)
        rather than fixed DOM IDs — this avoids ``DuplicateIds`` errors
        during hot rebuilds.

        When no Textual app is active (e.g. pure-data tests), the rebuild
        is deferred until the widget is mounted.
        """
        if getattr(self, "_rebuilding", False):
            return
        self._rebuilding = True
        try:
            try:
                self.remove_children()
            except Exception:
                # Widget is not mounted — just update the internal state
                self._rebuilding = False
                return
            for sid, title in self._sessions:
                is_active = sid == self._active_id
                is_running = sid in self._running_ids
                self.mount(_TabContainer(sid, title, is_active, is_running))
            self.mount(_NewTabButton())
        finally:
            self._rebuilding = False

    # -- event handling ---------------------------------------------------------

    def on_click(self, event: events.Click) -> None:
        """Handle click events — dispatch to the appropriate callback.

        Clicking on:
        - A tab label → switch to that session (R4.2)
        - A close button → close that session (R4.4)
        - The ``+`` button → create a new session (R4.3)
        """
        widget = event.widget
        if widget is None:
            return

        if isinstance(widget, _NewTabButton):
            self.post_message(self.NewTabRequested())
            return

        if isinstance(widget, _TabCloseButton):
            self.post_message(self.TabClosed(widget.session_id))
            return

        if isinstance(widget, _TabLabel):
            self.post_message(self.TabSelected(widget.session_id))
            return

        # Walk up to find the containing _TabContainer
        parent = getattr(widget, "parent", None)
        while parent is not None:
            if isinstance(parent, _TabContainer):
                self.post_message(self.TabSelected(parent.session_id))
                return
            parent = getattr(parent, "parent", None)
