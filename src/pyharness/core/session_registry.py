"""Session registry — maps screen IDs to session IDs for multi-screen support.

Phase 1 of parallel multi-agent: each ``ChatScreen`` owns exactly one session.
The ``SessionRegistry`` is the single source of truth for which screen is bound
to which session, replacing the old app-level ``_current_session_id`` scalar.

Usage::

    reg = SessionRegistry()
    reg.register("chat-1", "sess-abc123")
    sid = reg.get("chat-1")          # → "sess-abc123"
    reg.list_all()                   # → {"chat-1": "sess-abc123"}
    reg.unregister("chat-1")
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Reserved screen ID for the default single-session ChatScreen.
DEFAULT_SCREEN_ID = "_default"


@dataclass
class SessionRegistry:
    """Thread-safe mapping from screen IDs to session IDs.

    Each ``ChatScreen`` gets a stable **screen_id** (typically the value of
    ``id`` on the Textual DOM node or a user-chosen label).  The registry
    records which **session_id** is bound to that screen.
    """

    _map: dict[str, str] = field(default_factory=dict)

    def register(self, screen_id: str, session_id: str) -> None:
        """Bind a screen to a session.

        If *screen_id* is already registered, its previous binding is
        silently replaced.
        """
        self._map[screen_id] = session_id

    def get(self, screen_id: str) -> str | None:
        """Return the session ID for *screen_id*, or ``None``."""
        return self._map.get(screen_id)

    def unregister(self, screen_id: str) -> None:
        """Remove a screen's binding.  No-op if not registered."""
        self._map.pop(screen_id, None)

    def list_all(self) -> dict[str, str]:
        """Return a shallow copy of the current screen → session mapping."""
        return dict(self._map)

    # -- convenience helpers ---------------------------------------------------

    @property
    def default_session_id(self) -> str | None:
        """Return the session ID registered under the default screen slot."""
        return self._map.get(DEFAULT_SCREEN_ID)

    def register_default(self, session_id: str) -> None:
        """Register the default single-session binding."""
        self.register(DEFAULT_SCREEN_ID, session_id)
