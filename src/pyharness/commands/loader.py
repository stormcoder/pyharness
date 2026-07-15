"""Slash command loader — discovers and registers custom commands.

Phase 2: Loads built-in commands from the app's ``COMMANDS`` registry and
custom commands from ``pyharness.json`` ``command`` config section.

Commands are keyed as ``/name`` → :class:`CommandConfig` with template and
description.  The loader merges built-in defaults with project overrides
from the config.

Usage::

    from pyharness.commands.loader import CommandLoader

    loader = CommandLoader(config)
    all_commands = loader.load_all()
    # → {"/new": CommandConfig(...), "/help": CommandConfig(...), ...}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyharness.config.schema import PyHarnessConfig


# ---------------------------------------------------------------------------
# Built-in commands from SPEC §12.1 and Phase 2 requirements
# ---------------------------------------------------------------------------

BUILTIN_COMMANDS: dict[str, str] = {
    "/new": "Start a new session",
    "/undo": "Undo last action",
    "/redo": "Redo last undone action",
    "/sessions": "List all sessions",
    "/help": "Show help",
    "/compact": "Compact session context",
    "/editor": "Open external editor",
    "/export": "Export session to markdown",
    "/models": "List available models",
    "/themes": "List available themes",
    "/memory": "Search project memory",
    "/remember": "Store a fact in memory",
}


# ---------------------------------------------------------------------------
# Loaded command
# ---------------------------------------------------------------------------


@dataclass
class LoadedCommand:
    """A loaded command ready for registration in the TUI."""

    name: str
    description: str
    template: str = ""
    agent: str = ""
    model: str = ""


# ---------------------------------------------------------------------------
# CommandLoader
# ---------------------------------------------------------------------------


class CommandLoader:
    """Discovers and loads slash commands from built-in defaults and config.

    Args:
        config: Project configuration with optional ``command`` overrides.
    """

    def __init__(self, config: PyHarnessConfig | None = None) -> None:
        self._config = config

    def load_all(self) -> dict[str, LoadedCommand]:
        """Return all registered commands (built-in + custom config overrides).

        Custom commands from ``pyharness.json`` take precedence over
        built-in defaults with the same name.

        Returns:
            Mapping of ``/name`` → :class:`LoadedCommand`.
        """
        commands: dict[str, LoadedCommand] = {}

        # 1. Load built-in defaults
        for name, desc in BUILTIN_COMMANDS.items():
            commands[name] = LoadedCommand(name=name, description=desc)

        # 2. Override/extend with config commands
        if self._config is not None:
            for name, cmd_cfg in self._config.command.items():
                if not name.startswith("/"):
                    name = "/" + name
                commands[name] = LoadedCommand(
                    name=name,
                    description=cmd_cfg.description or "",
                    template=cmd_cfg.template or "",
                    agent=cmd_cfg.agent or "",
                    model=cmd_cfg.model or "",
                )

        return commands

    def find(self, name: str) -> LoadedCommand | None:
        """Look up a single command by name.

        Args:
            name: Command name with leading ``/`` (e.g. ``"/new"``).

        Returns:
            :class:`LoadedCommand` or ``None`` if not found.
        """
        all_cmds = self.load_all()
        return all_cmds.get(name)
