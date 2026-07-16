"""Sidebar with AGENTS.md, Context, and MCP sections — no tabs, no tools.

Phase 2: Redesigned from tabbed panes to labeled sections in a vertical scroll.
Phase 3: Added refresh methods for MCP status and AGENTS.md content.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static


class Sidebar(VerticalScroll):
    """Project sidebar with AGENTS.md, context usage, and MCP server status.

    Toggle with ``Ctrl+o`` from :class:`~pyharness.tui.app.PyHarnessApp`.
    """

    can_focus = False  # CRITICAL: Never steal focus from input field

    def compose(self) -> ComposeResult:
        # Section 1: AGENTS.md
        with Container(id="section-agents"):
            yield Static("[bold #58a6ff]AGENTS.md[/]", id="agents-header")
            yield Static(
                "[#8b949e]Run /init to create AGENTS.md for this project[/]",
                id="agents-content",
            )

        # Divider
        yield Static("", id="divider-1")

        # Section 2: Context
        with Container(id="section-context"):
            yield Static("[bold #58a6ff]Context[/]", id="context-header")
            yield Static(
                "[#8b949e]0 / 200,000 tokens (0.0%)[/]", id="context-tokens"
            )
            yield Static("[#8b949e]$0.00 spent[/]", id="context-cost")

        # Divider
        yield Static("", id="divider-2")

        # Section 3: MCP Servers
        with Container(id="section-mcp"):
            yield Static("[bold #58a6ff]MCP Servers[/]", id="mcp-header")
            yield Static(
                "[#8b949e]No MCP servers configured[/]", id="mcp-status"
            )

    # ------------------------------------------------------------------
    # Public refresh methods (Phase 3)
    # ------------------------------------------------------------------

    def refresh_mcp_status(self) -> None:
        """Refresh MCP server status from the MCPLoader."""
        from pyharness.tools.mcp_loader import MCPLoader

        loader = MCPLoader()
        # Load from config if available
        try:
            from pyharness.config.loader import load_config

            config = load_config(Path.cwd())
            loader.load_from_config({"mcp": config.mcp})
        except Exception:
            pass

        servers = loader.list_servers()
        status: dict[str, bool] = {}
        for s in servers:
            status[s.name] = s.active and s.enabled
        self.update_mcp_servers(status)

    def refresh_agents_md(self) -> None:
        """Refresh the AGENTS.md section with actual file content/status."""
        agents_md = Path.cwd() / "AGENTS.md"
        if agents_md.exists():
            content = agents_md.read_text()
            first_line = content.strip().split("\n")[0][:80]
            self.query_one("#agents-content", Static).update(
                f"[#7ee787]AGENTS.md found:[/] {first_line}..."
            )
        else:
            self.query_one("#agents-content", Static).update(
                "[#8b949e]Run /init to create AGENTS.md for this project[/]"
            )

    # ------------------------------------------------------------------
    # Section updaters
    # ------------------------------------------------------------------

    def update_context(
        self, tokens_used: int = 0, tokens_total: int = 200000, cost: float = 0.0
    ) -> None:
        """Update the context section with current usage.

        Args:
            tokens_used: Number of tokens consumed so far.
            tokens_total: Context window size in tokens.
            cost: Estimated cost in USD.
        """
        pct = (tokens_used / tokens_total) * 100 if tokens_total else 0
        self.query_one("#context-tokens", Static).update(
            f"[#8b949e]{tokens_used:,} / {tokens_total:,} tokens ({pct:.1f}%)[/]"
        )
        self.query_one("#context-cost", Static).update(
            f"[#8b949e]${cost:.2f} spent[/]"
        )

    def update_mcp_servers(self, servers: dict[str, bool]) -> None:
        """Update MCP section with server status indicators.

        Args:
            servers: Mapping of ``{server_name: is_active}``.
        """
        if not servers:
            self.query_one("#mcp-status", Static).update(
                "[#8b949e]No MCP servers configured[/]"
            )
            return
        lines: list[str] = []
        for name, active in servers.items():
            dot = "[#3fb950]🟢[/]" if active else "[#f85149]🔴[/]"
            lines.append(f"  {dot} [#c9d1d9]{name}[/]")
        self.query_one("#mcp-status", Static).update(
            "\n".join(lines) if lines else "[#8b949e]No MCP servers configured[/]"
        )


# ---------------------------------------------------------------------------
# Standalone utility widgets (not used by the new Sidebar but available for
# backward compatibility with tests and potential future use).
# ---------------------------------------------------------------------------


class SessionList(Static):
    """Placeholder listing of recent sessions."""

    def on_mount(self) -> None:
        self.update("[#8b949e]Sessions will be listed here (Phase 2).[/]")


class ToolList(Static):
    """List of available tools for the current session."""

    def on_mount(self) -> None:
        """Populate the tool list from registry."""
        from pyharness.tools.registry import get_registry

        registry = get_registry()
        tools = registry.get_names()

        lines = ["[bold #58a6ff]Available Tools[/]\n"]
        if tools:
            for name in sorted(tools):
                try:
                    tool = registry.get_tool(name)
                    desc = tool.description[:60] if tool.description else "No description"
                except KeyError:
                    desc = "No description"
                lines.append(f"[#7ee787]  {name}[/] — [#8b949e]{desc}[/]")
        else:
            from pyharness.tools import register_all_tools

            register_all_tools()
            tools = registry.get_names()
            for name in sorted(tools):
                try:
                    tool = registry.get_tool(name)
                    desc = tool.description[:60] if tool.description else "No description"
                except KeyError:
                    desc = "No description"
                lines.append(f"[#7ee787]  {name}[/] — [#8b949e]{desc}[/]")

        lines.append(f"\n[#8b949e]{len(tools)} tools available[/]")
        self.update("\n".join(lines))

    @staticmethod
    def _format_tool(name: str, description: str) -> str:
        """Format a single tool entry for display.

        Args:
            name: Tool name.
            description: Tool description.

        Returns:
            Formatted Rich markup string.
        """
        desc = description[:60] if description else "No description"
        return f"[#7ee787]  {name}[/] — [#8b949e]{desc}[/]"
