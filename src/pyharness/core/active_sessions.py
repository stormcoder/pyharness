"""Active sessions — persist currently-open session tabs across restarts.

Replaces the old ``~/.local/share/pyharness/sessions/current`` pointer file
with a structured ``active.json`` that stores all open tab state.

R1.11: Save active.json on shutdown.
R1.12: Restore active session tabs on startup (with migration from old pointer).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict


class TabEntry(TypedDict):
    """A single active tab entry in active.json."""

    session_id: str
    screen_id: str


@dataclass
class ActiveSessions:
    """Manages the active.json file in the sessions directory.

    Each tab entry is a ``TabEntry`` dict with ``session_id`` and ``screen_id``.

    On first load, if the old ``current`` pointer file exists, its contents are
    migrated into the first tab slot and the pointer file is deleted.

    Usage::

        active = ActiveSessions(sessions_dir)
        active.add("sess-abc", "chat-1")
        active.save()

        # After restart:
        active.load()
        for entry in active.list_all():
            print(entry["session_id"], entry["screen_id"])
    """

    _sessions_dir: Path
    _tabs: list[TabEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # File paths
    # ------------------------------------------------------------------

    @property
    def _active_path(self) -> Path:
        """Path to the active.json file."""
        return self._sessions_dir / "active.json"

    @property
    def _current_ptr_path(self) -> Path:
        """Path to the legacy ``current`` pointer file."""
        return self._sessions_dir / "current"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Default to empty tabs if not provided."""
        if not isinstance(self._tabs, list):
            object.__setattr__(self, "_tabs", [])

    def add(self, session_id: str, screen_id: str) -> None:
        """Add (or update) a tab entry.

        If the *session_id* is already present, its *screen_id* is updated
        rather than creating a duplicate entry.

        Args:
            session_id: The session ID for the tab.
            screen_id: The screen ID (e.g. ``"chat-1"``) for the tab.
        """
        # Update existing entry if session_id already tracked
        for entry in self._tabs:
            if entry["session_id"] == session_id:
                entry["screen_id"] = screen_id
                return
        self._tabs.append(TabEntry(session_id=session_id, screen_id=screen_id))

    def remove(self, session_id: str) -> None:
        """Remove a tab entry by session ID.

        No-op if *session_id* is not present.

        Args:
            session_id: The session ID to remove.
        """
        self._tabs = [t for t in self._tabs if t["session_id"] != session_id]

    def list_all(self) -> list[TabEntry]:
        """Return all active tab entries.

        Returns:
            A list of tab entries, each a dict with ``session_id`` and
            ``screen_id`` keys.
        """
        return list(self._tabs)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write ``active.json`` to disk.

        Creates the parent directory if it does not exist.
        """
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, list[TabEntry]] = {"tabs": self._tabs}
        self._active_path.write_text(json.dumps(payload, indent=2))

    def load(self) -> None:
        """Load tabs from ``active.json``, migrating from the old ``current``
        pointer file if it exists.

        Migration: if ``current`` exists and ``active.json`` does not, the
        session ID from ``current`` is registered as the single active tab
        and the pointer file is deleted.
        """
        self._migrate_from_current_if_needed()

        if not self._active_path.exists():
            self._tabs = []
            return

        try:
            data = json.loads(self._active_path.read_text())
        except (json.JSONDecodeError, OSError):
            self._tabs = []
            return

        raw_tabs: list[dict[str, str]] = data.get("tabs", [])
        self._tabs = [
            TabEntry(
                session_id=entry.get("session_id", ""),
                screen_id=entry.get("screen_id", ""),
            )
            for entry in raw_tabs
            if isinstance(entry, dict)
        ]

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_from_current_if_needed(self) -> None:
        """If the legacy ``current`` pointer exists and ``active.json`` does
        not, migrate the pointer into the new format and delete the old file."""
        if self._active_path.exists():
            return
        if not self._current_ptr_path.exists():
            return

        try:
            sid = self._current_ptr_path.read_text().strip()
            if sid:
                self._tabs.append(
                    TabEntry(session_id=sid, screen_id="_default")
                )
                self.save()
        except OSError:
            pass

        # Always delete the legacy file after migration attempt
        with contextlib.suppress(OSError):
            self._current_ptr_path.unlink(missing_ok=True)
