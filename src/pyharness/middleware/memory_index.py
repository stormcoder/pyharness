"""Memory auto-index middleware for session lifecycle events.

Implements SPEC §6.1: hooks into session.start, session.idle,
session.compacted, and session.end to trigger automatic MemPalace indexing.
"""

from __future__ import annotations

from pyharness.core.logging import get_logger

logger = get_logger(__name__)


class MemoryIndexMiddleware:
    """Triggers automatic MemPalace indexing on session lifecycle events.

    When MemPalace is available, this middleware captures session exchanges
    at configured trigger points and indexes them into the project wing.

    Parameters:
        config: Memory configuration from ``pyharness.json``.
        project_name: Wing name for MemPalace scoping.
    """

    def __init__(self, config: object | None = None, project_name: str = "") -> None:
        self._config = config
        self._project_name = project_name

    @property
    def available(self) -> bool:
        """Whether MemPalace is importable."""
        return False  # Phase 3: wire to actual MemPalace import check

    async def on_session_idle(self, session_id: str) -> None:
        """Trigger auto-index when the session becomes idle."""

    async def on_session_compacted(self, session_id: str) -> None:
        """Capture session context before compaction."""

    async def on_session_end(self, session_id: str) -> None:
        """Run full index + diary write at session end."""
