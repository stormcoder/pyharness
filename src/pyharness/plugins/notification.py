"""Example plugin: desktop notifications on session events."""

from __future__ import annotations

from typing import Any


class NotificationPlugin:
    """Sends desktop notification when a session completes or errors."""

    async def on_session_idle(self, ctx: Any, session: dict) -> None:
        """Notify user that a session has completed."""
        self._notify(
            "pyharness",
            f"Session completed: {session.get('title', 'Untitled')}",
            critical=False,
        )

    async def on_session_error(self, ctx: Any, session: dict) -> None:
        """Notify user that a session error occurred."""
        self._notify(
            "pyharness",
            "Session error occurred",
            critical=True,
        )

    async def on_tool_execute_before(
        self, ctx: Any, tool_name: str, args: dict
    ) -> None:
        """No-op: notifications are for session-level events only."""

    @staticmethod
    def _notify(title: str, body: str, *, critical: bool = False) -> None:
        """Emit a ``notify-send`` call (Linux only)."""
        try:
            import subprocess

            cmd = ["notify-send"]
            if critical:
                cmd.extend(["-u", "critical"])
            cmd.extend([title, body])
            subprocess.run(cmd, timeout=2)
        except Exception:
            pass
