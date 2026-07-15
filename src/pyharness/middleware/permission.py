"""Permission enforcement middleware for tool calls.

Implements SPEC.md §8.3: a synchronous check that runs before every tool
invocation and returns an allow / ask / deny decision.

Resolution order
----------------
1. Agent-level permission rules override global rules.
2. Glob match on tool name (``fnmatch``-style).
3. For ``bash``: also glob match on the ``command`` string inside args.
4. Last matching rule wins (most-specific glob checked first).

The middleware is intentionally synchronous — it is called inline before
the tool executor node in the agent graph so that the TUI can inject
a human-in-the-loop prompt for ``"ask"`` decisions.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Literal

from pyharness.config.schema import PyHarnessConfig

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PermissionAction = Literal["allow", "ask", "deny"]


@dataclass
class PermissionResult:
    """The outcome of a permission check.

    Attributes
    ----------
    action:
        ``"allow"``, ``"ask"``, or ``"deny"``.
    reason:
        Human-readable explanation of the decision.
    """

    action: PermissionAction
    reason: str = ""


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class PermissionMiddleware:
    """Intercepts tool calls and enforces permission rules.

    Parameters
    ----------
    config:
        The full pyharness configuration.
    agent_name:
        The active agent (e.g. ``"build"``, ``"plan"``) whose agent-level
        override rules are consulted first.
    parent_agent_name:
        When running as a subagent, the name of the parent agent.  Subagents
        **inherit** their parent's permission ceiling — they can never exceed
        what the parent allows.  For example, a ``"general"`` subagent spawned
        by ``"plan"`` cannot use ``edit`` or ``bash`` even though its own
        configuration allows them.
    """

    def __init__(
        self,
        config: PyHarnessConfig,
        agent_name: str = "build",
        parent_agent_name: str | None = None,
    ) -> None:
        self._config = config
        self._agent_name = agent_name
        self._parent_agent_name = parent_agent_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> PermissionResult:
        """Check whether *tool_name* is permitted.

        When a ``parent_agent_name`` is configured (subagent mode), the
        subagent's effective permission is the **stricter** of its own
        rules and the parent's — it can never exceed the parent ceiling.

        Parameters
        ----------
        tool_name:
            The tool being invoked (e.g. ``"bash"``, ``"edit"``, ``"read"``).
        args:
            Tool arguments.  For ``"bash"`` tools the ``command`` key is
            inspected for per-command glob matching.

        Returns
        -------
        PermissionResult
        """
        # ----- resolve effective permission value ---------------------------
        permission_value = self._resolve_permission(tool_name)

        # If the permission value is a dict of glob → action (only used for
        # bash commands), match the command string.
        if isinstance(permission_value, dict) and tool_name == "bash":
            command = self._extract_command(args)
            permission_value = self._match_glob_dict(permission_value, command)

        # If permission_value is a bare string, cast to the action name;
        # otherwise fall back to "allow".
        action = self._to_action(permission_value) if isinstance(permission_value, str) else "allow"

        # ----- subagent inheritance: enforce parent ceiling -----------------
        if self._parent_agent_name is not None:
            parent_action = self._resolve_agent_action(
                self._parent_agent_name, tool_name, args
            )
            action = _min_action(action, parent_action)

        # ----- produce result -----------------------------------------------
        if action == "deny":
            return PermissionResult("deny", f"Permission denied for {tool_name}")
        if action == "ask":
            return PermissionResult("ask", f"Approval required for {tool_name}")
        return PermissionResult("allow")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_permission(self, tool_name: str) -> Any:
        """Return the raw permission value for *tool_name*.

        Agent-level rules are checked first (they win if set), then global.
        ``"write"`` and ``"edit"`` tools are grouped under the ``"edit"``
        permission key (matching OpenCode's model).
        """
        # Normalise tool name for permission lookup
        lookup_name = "edit" if tool_name in ("write", "edit") else tool_name

        # --- agent-level ----------------------------------------------------
        agent_def = self._config.agent.get(self._agent_name)
        agent_perms = agent_def.permission if agent_def else None

        if agent_perms is not None:
            value = self._lookup_permission(agent_perms, lookup_name)
            if value is not None:
                return value

        # --- global ---------------------------------------------------------
        value = self._lookup_permission(
            self._config.permission, lookup_name
        )
        if value is not None:
            return value

        # --- default --------------------------------------------------------
        return "allow"

    @staticmethod
    def _lookup_permission(perms: Any, key: str) -> Any:
        """Return the permission value for *key* in *perms*, or ``None``.

        *perms* may be an ``AgentPermissionConfig`` (has attribute access)
        or a plain ``dict`` (from ``PyHarnessConfig.permission``).
        """
        if isinstance(perms, dict):
            return perms.get(key)
        # AgentPermissionConfig — duck-type attribute access
        if hasattr(perms, key):
            return getattr(perms, key)
        return None

    @staticmethod
    def _match_glob_dict(
        rules: dict[str, str],
        target: str,
    ) -> str | None:
        """Find the best-matching rule in *rules* for *target*.

        Rules are sorted by specificity (exact match > prefix glob >
        wildcard) so that the most specific match wins.
        """
        if not rules:
            return None

        def _specificity(pattern: str) -> int:
            score = 0
            if "*" not in pattern:
                score += 100
            elif pattern.endswith("*") and pattern.count("*") == 1:
                score += 50
            score += len(pattern)
            return score

        sorted_patterns = sorted(rules.keys(), key=_specificity, reverse=True)
        for pattern in sorted_patterns:
            if fnmatch.fnmatch(target, pattern):
                return rules[pattern]
        return None

    @staticmethod
    def _extract_command(args: dict[str, Any] | None) -> str:
        """Extract the command string from bash tool arguments."""
        if args is None:
            return ""
        return str(args.get("command", ""))

    @staticmethod
    def _to_action(value: str) -> PermissionAction:
        """Normalise a permission value string to a ``PermissionAction``."""
        return value.lower() if value.lower() in ("allow", "ask", "deny") else "allow"  # type: ignore[return-value]

    def _resolve_agent_action(
        self,
        agent_name: str,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> PermissionAction:
        """Resolve the effective action for *agent_name* on *tool_name*.

        This mirrors the logic in :meth:`check` but resolves against a
        specific agent name rather than ``self._agent_name``. Used by
        the subagent inheritance mechanism.
        """
        # Normalise tool name
        lookup_name = "edit" if tool_name in ("write", "edit") else tool_name

        # Check agent-level
        agent_def = self._config.agent.get(agent_name)
        if agent_def is not None and agent_def.permission is not None:
            value = self._lookup_permission(agent_def.permission, lookup_name)
            if value is not None:
                if isinstance(value, dict) and tool_name == "bash":
                    command = self._extract_command(args)
                    matched = self._match_glob_dict(value, command)
                    if matched is not None:
                        return self._to_action(matched)
                    return "allow"  # no glob matched in bash dict → default allow
                if isinstance(value, str):
                    return self._to_action(value)
                return "allow"

        # Check global
        value = self._lookup_permission(self._config.permission, lookup_name)
        if value is not None:
            if isinstance(value, dict) and tool_name == "bash":
                command = self._extract_command(args)
                matched = self._match_glob_dict(value, command)
                if matched is not None:
                    return self._to_action(matched)
                return "allow"
            if isinstance(value, str):
                return self._to_action(value)

        return "allow"  # default


def _action_order(action: PermissionAction) -> int:
    """Map an action to its strictness rank (higher = more restrictive)."""
    return {"allow": 0, "ask": 1, "deny": 2}.get(action, 0)


def _min_action(a: PermissionAction, b: PermissionAction) -> PermissionAction:
    """Return the more restrictive of two actions.

    ``deny`` > ``ask`` > ``allow`` — the subagent can never exceed
    the parent's permission ceiling.
    """
    return a if _action_order(a) >= _action_order(b) else b
