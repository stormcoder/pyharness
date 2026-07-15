"""pyharness tool system — registry, built-ins, MCP loader, and memory tools.

Usage::

    from pyharness.tools import register_all_tools
    register_all_tools()
"""

from __future__ import annotations


def register_all_tools() -> None:
    """Register every built-in tool into the global :class:`ToolRegistry`.

    Call this once during application startup before creating any agents.
    """
    from pyharness.tools.builtin import ALL_BUILTIN_TOOLS
    from pyharness.tools.registry import get_registry

    registry = get_registry()
    for tool in ALL_BUILTIN_TOOLS:
        registry.register(tool)


# Auto-register built-in tools at import time so the registry is never empty.
register_all_tools()
