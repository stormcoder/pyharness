"""MCP client loader — discovers and manages MCP server connections.

Provides :class:`MCPLoader` for managing local (stdio) and remote (HTTP)
MCP server lifecycle, and :class:`MCPServer` as its configuration record.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServer:
    """Descriptor for a single MCP server connection.

    Attributes:
        name: Human-readable name for the server (unique key).
        type: Transport type — ``"local"`` (subprocess) or ``"remote"`` (HTTP).
        enabled: Whether the server is allowed to be used.
        active: Whether the server is currently connected.
        tool_count: Number of tools discovered from this server.
        command: For ``type="local"``, the subprocess command + args.
        url: For ``type="remote"``, the server URL.
    """

    name: str
    type: str = "local"  # "local" or "remote"
    enabled: bool = True
    active: bool = False
    tool_count: int = 0
    command: list[str] | None = None
    url: str | None = None


class MCPLoader:
    """Manages MCP server lifecycle.

    Holds a registry of :class:`MCPServer` instances and provides helpers
    for querying active servers and loading configurations from the
    pyharness config dictionary.
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPServer] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_servers(self) -> list[MCPServer]:
        """List all configured MCP servers."""
        return list(self._servers.values())

    def get_server(self, name: str) -> MCPServer | None:
        """Return a single server by name, or ``None`` if absent."""
        return self._servers.get(name)

    def get_active_servers(self) -> list[MCPServer]:
        """Return only servers that are currently active."""
        return [s for s in self._servers.values() if s.active]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_server(self, name: str, server: MCPServer) -> None:
        """Register or replace a server by name."""
        self._servers[name] = server

    def load_from_config(self, config: dict) -> None:
        """Load MCP servers from a pyharness config dictionary.

        Args:
            config: Dict with optional ``"mcp"`` key mapping server names
                   to their configuration dicts.
        """
        if "mcp" not in config:
            return
        for name, cfg in config["mcp"].items():
            if not isinstance(cfg, dict):
                continue
            server = MCPServer(
                name=name,
                type=cfg.get("type", "local"),
                enabled=cfg.get("enabled", True),
                active=cfg.get("enabled", True)
                and cfg.get("type") is not None,
                command=cfg.get("command"),
                url=cfg.get("url"),
            )
            self._servers[name] = server
