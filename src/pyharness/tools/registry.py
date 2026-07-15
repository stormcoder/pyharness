"""Central tool registry for pyharness.

All tools (builtin, MCP, custom plugins) are registered here and
retrieved for LangGraph agent creation.  Supports permission-aware
filtering so agents only see tools they are allowed to use.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _tool_allowed(
    tool_name: str,
    permissions: dict[str, str | dict[str, str]],
) -> bool:
    """Check whether *tool_name* is permitted under *permissions*.

    Permission keys are globbed against the tool name.  Each key maps to
    either a flat string (``"allow" | "ask" | "deny"``) or a dict of
    ``glob → action``.  A tool is allowed unless a matching key explicitly
    denies it.

    **Specificity ordering**: More specific globs are checked before
    wildcards.  ``"mock_alpha"`` is checked before ``"mock_*"``, which
    is checked before ``"*"``.  This way a specific ``"allow"`` overrides
    a broad ``"deny"``.

    If *permissions* is empty, all tools are allowed.
    """
    if not permissions:
        return True

    # Sort by specificity: exact matches > prefix globs > wildcard
    def _specificity(key: str) -> int:
        """Higher = more specific (checked first)."""
        score = 0
        score += key.count("/") * 3
        if "*" not in key:
            score += 100  # exact match
        elif key.endswith("*") and key.count("*") == 1:
            score += 50  # prefix glob like "mock_*"
        else:
            score += 0  # wildcard like "*"
        # Longer keys are more specific
        score += len(key)
        return score

    sorted_keys = sorted(permissions.keys(), key=_specificity, reverse=True)

    for perm_key in sorted_keys:
        if fnmatch.fnmatch(tool_name, perm_key):
            perm_val = permissions[perm_key]
            if isinstance(perm_val, str):
                return perm_val != "deny"
            if isinstance(perm_val, dict):
                # Sub-glob permissions — sort by specificity too.
                # If a sub-glob matches, use it. If none match,
                # continue to the next permission key (the dict
                # only adds granularity, not a blanket deny).
                sub_keys = sorted(perm_val.keys(), key=_specificity, reverse=True)
                for sub_glob in sub_keys:
                    if fnmatch.fnmatch(tool_name, sub_glob):
                        return perm_val[sub_glob] != "deny"
                # No sub-glob matched — continue checking other keys
                continue

    # No key matched → allowed by default
    return True


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry for all tools (builtin + MCP + custom).

    Each tool must be a :class:`langchain_core.tools.BaseTool` with a
    unique ``.name``.  The registry is a singleton accessed via
    :func:`get_registry`.

    Usage::

        registry = get_registry()
        registry.register(bash_tool)
        agent_tools = registry.get_for_agent(permissions)
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # -- registration ----------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool.  Replaces any existing tool with the same name."""
        self._tools[tool.name] = tool

    def register_all(self, tools: Sequence[BaseTool]) -> None:
        """Register multiple tools at once."""
        for t in tools:
            self.register(t)

    # -- queries ---------------------------------------------------------------

    def get_all(self) -> list[BaseTool]:
        """Return every registered tool, unsorted."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> BaseTool:
        """Retrieve a single tool by name.

        Raises:
            KeyError: If *name* is not registered.
        """
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' is not registered. "
                f"Available: {', '.join(sorted(self._tools))}"
            )
        return self._tools[name]

    def get_names(self) -> list[str]:
        """Return the sorted list of registered tool names."""
        return sorted(self._tools)

    def get_for_agent(
        self,
        permissions: dict[str, str | dict[str, str]] | None = None,
    ) -> list[BaseTool]:
        """Return tools filtered by agent permissions.

        A tool is included unless a matching permission rule explicitly
        sets it to ``"deny"``.  Empty or ``None`` permissions allow all.

        Args:
            permissions: Permission map (see :func:`_tool_allowed` for rules).

        Returns:
            List of allowed tools.
        """
        if not permissions:
            return self.get_all()

        return [
            t for t in self._tools.values() if _tool_allowed(t.name, permissions)
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the global :class:`ToolRegistry` singleton."""
    return _registry
