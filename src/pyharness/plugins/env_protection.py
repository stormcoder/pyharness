"""Example plugin: prevent reading .env files."""

from __future__ import annotations

from typing import Any


class EnvProtectionPlugin:
    """Blocks tool access to ``.env`` files for security."""

    _BLOCKED_SUFFIXES: tuple[str, ...] = (".env",)

    async def on_session_idle(self, ctx: Any, session: dict) -> None:
        """No-op."""

    async def on_session_error(self, ctx: Any, session: dict) -> None:
        """No-op."""

    async def on_tool_execute_before(
        self, ctx: Any, tool_name: str, args: dict
    ) -> None:
        """Intercept tool calls that try to read blocked files."""
        path = str(args.get("path", "")).lower()
        if tool_name == "read" and any(
            path.endswith(suffix) for suffix in self._BLOCKED_SUFFIXES
        ):
            raise RuntimeError(
                "Reading .env files is blocked for security."
            )
