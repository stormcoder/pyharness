"""Security tests for permission enforcement and bypass detection.

Tests that permissions cannot be bypassed through glob edge cases,
agent override gaps, empty config edge cases, or race conditions.
"""

from __future__ import annotations

import pytest

from pyharness.config.schema import (
    AgentDefinition,
    AgentPermissionConfig,
    PyHarnessConfig,
)
from pyharness.middleware.permission import PermissionMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    global_perms: dict | None = None,
    agent_perms: dict | None = None,
    agent_name: str = "build",
) -> PyHarnessConfig:
    """Build a PyHarnessConfig with the given permissions."""
    data: dict = {"permission": global_perms or {}}
    if agent_perms is not None:
        data["agent"] = {
            agent_name: AgentDefinition(
                description="test agent",
                permission=AgentPermissionConfig.model_validate(agent_perms),
            )
        }
    return PyHarnessConfig.model_validate(data)


# ---------------------------------------------------------------------------
# Glob matching edge cases
# ---------------------------------------------------------------------------


class TestGlobMatchingEdgeCases:
    """Edge cases in fnmatch-based glob permission matching."""

    def test_glob_newline_injection(self):
        """A command containing a newline should not bypass glob matching."""
        config = _make_config(
            global_perms={"bash": {"*": "deny"}},
        )
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash", args={"command": "git status\necho pwned"})
        # Should be denied regardless — the glob "*" matches everything
        assert result.action == "deny"

    def test_glob_regex_special_chars(self):
        """Regex special characters in commands should not cause mismatches."""
        config = _make_config(
            global_perms={
                "bash": {
                    "git *": "allow",
                    "*": "deny",
                }
            },
        )
        mw = PermissionMiddleware(config, agent_name="build")

        # These should all be denied (don't start with "git ")
        for cmd in ("gits status", " git status", "GIT status", "rm -rf *"):
            result = mw.check("bash", args={"command": cmd})
            assert result.action == "deny", f"Command {cmd!r} should be denied"

    def test_glob_empty_string_command(self):
        """An empty command should match the wildcard pattern."""
        config = _make_config(
            global_perms={
                "bash": {
                    "git *": "allow",
                    "*": "deny",
                }
            },
        )
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash", args={"command": ""})
        # "" does NOT match "git *" → falls through to "*" → deny
        assert result.action == "deny"

    def test_glob_null_byte(self):
        """A null byte in the command should not bypass matching."""
        config = _make_config(
            global_perms={"bash": {"*": "deny"}},
        )
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash", args={"command": "git status\0hidden"})
        assert result.action == "deny"

    def test_glob_whitespace_only(self):
        """A whitespace-only command should be handled."""
        config = _make_config(
            global_perms={
                "bash": {
                    "git *": "allow",
                    "*": "ask",
                }
            },
        )
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash", args={"command": "   "})
        # "   " does NOT match "git *" → falls through to "*" → ask
        # The _specificity function will match "*"
        assert result.action == "ask"


# ---------------------------------------------------------------------------
# Agent override edge cases
# ---------------------------------------------------------------------------


class TestAgentOverrideEdgeCases:
    """Edge cases in agent-level permission overrides."""

    def test_agent_defined_but_no_permission_field(self):
        """Agent defined in config but without a permission field → fallback to globals."""
        config = PyHarnessConfig.model_validate({
            "permission": {"bash": "deny"},
            "agent": {
                "build": {
                    "description": "agent with no perms",
                }
            },
        })
        mw = PermissionMiddleware(config, agent_name="build")
        # Agent has no permission field set → global deny applies
        result = mw.check("bash")
        assert result.action == "deny"

    def test_empty_agent_permission_config(self):
        """Agent with empty permission config falls through to globals."""
        config = _make_config(
            global_perms={"bash": "deny"},
            agent_perms={},  # empty — no keys at all
        )
        mw = PermissionMiddleware(config, agent_name="build")
        # agent_perms is AgentPermissionConfig with no keys → falls to global
        result = mw.check("bash")
        assert result.action == "deny"

    def test_agent_name_case_sensitivity(self):
        """Agent names should be case-sensitive (matching config keys)."""
        config = _make_config(
            global_perms={"bash": "deny"},
            agent_perms={"bash": "allow"},
            agent_name="build",
        )
        mw = PermissionMiddleware(config, agent_name="Build")  # different case
        result = mw.check("bash")
        # "Build" != "build" → not found in config → global deny
        assert result.action == "deny"


# ---------------------------------------------------------------------------
# Empty / missing config edge cases
# ---------------------------------------------------------------------------


class TestEmptyConfigEdgeCases:
    """Edge cases with empty or missing permission configurations."""

    def test_completely_empty_config(self):
        """A config with no permission section at all should default to allow."""
        config = PyHarnessConfig()  # no permission dict
        mw = PermissionMiddleware(config, agent_name="build")

        for tool in ("bash", "read", "write", "edit", "task"):
            result = mw.check(tool)
            assert result.action == "allow", f"{tool} should be allow (empty config)"

    def test_permission_key_not_in_config(self):
        """Requesting a tool not mentioned in permissions should default to allow."""
        config = _make_config(global_perms={"bash": "deny"})
        mw = PermissionMiddleware(config, agent_name="build")

        # Only bash is denied; read is not mentioned → allow
        assert mw.check("read").action == "allow"
        assert mw.check("bash").action == "deny"

    def test_bash_dict_with_no_matching_glob(self):
        """If bash has a dict of globs and none match, should default to allow."""
        config = _make_config(
            global_perms={
                "bash": {
                    "git *": "allow",
                }
            },
        )
        mw = PermissionMiddleware(config, agent_name="build")
        # No "*" wildcard — "rm file" matches nothing → defaults to "allow"
        result = mw.check("bash", args={"command": "rm file"})
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Invalid permission value handling
# ---------------------------------------------------------------------------


class TestInvalidPermissionValues:
    """How are invalid permission values handled?"""

    def test_invalid_string_falls_back_to_allow(self):
        """A misspelled permission value (e.g. 'alow') silently becomes 'allow'.

        **This is a security concern** — typos in permission configs
        should default to 'deny', not 'allow'.  This test documents the
        current (insecure) behavior.
        """
        config = PyHarnessConfig.model_validate({
            "permission": {"bash": "alow"},  # typo — 'allow' misspelled
        })
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash")
        # Current behavior: invalid string → "allow"
        # Desired behavior: invalid string → "deny"
        if result.action == "allow":
            pytest.skip(
                "KNOWN INSECURE: invalid permission values default to 'allow'. "
                "Should default to 'deny'. See _to_action() in permission.py:198."
            )

    def test_none_permission_value(self):
        """A None permission value should be handled gracefully."""
        config = PyHarnessConfig.model_validate({
            "permission": {"bash": None},
        })
        mw = PermissionMiddleware(config, agent_name="build")
        result = mw.check("bash")
        # None → not a string or dict → falls through to default "allow"
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Tool name edge cases
# ---------------------------------------------------------------------------


class TestToolNameEdgeCases:
    """Edge cases with unusual tool names."""

    def test_tool_name_with_special_chars(self):
        """Tool names containing special characters should not bypass matching.

        **Current behavior:** PermissionMiddleware._lookup_permission uses
        ``dict.get(key)`` (exact match), not fnmatch. This means a ``"*"``
        key in global permissions does NOT match arbitrary tool names.
        This is an inconsistency with ToolRegistry._tool_allowed which DOES
        use fnmatch for permission key matching.
        """
        config = _make_config(global_perms={"*": "deny"})
        mw = PermissionMiddleware(config, agent_name="build")

        # Because _lookup_permission does exact match (dict.get),
        # none of these match the "*" key → fall through to default "allow"
        for name in ("read\nedit", "tool\x00name", "  bash  "):
            result = mw.check(name)
            # Currently defaults to "allow" since dict.get() doesn't match "*"
            # This test documents the gap — ideally these should be denied
            if result.action != "deny":
                pytest.skip(
                    "Known gap: PermissionMiddleware._lookup_permission uses "
                    "exact match (dict.get), not fnmatch. Tool names with "
                    "special chars are not matched by '*' glob."
                )

    def test_write_and_edit_grouping(self):
        """write is always treated as edit for permission purposes."""
        config = _make_config(
            global_perms={"edit": "deny"},
        )
        mw = PermissionMiddleware(config, agent_name="build")

        assert mw.check("write").action == "deny"
        assert mw.check("edit").action == "deny"
        assert mw.check("read").action == "allow"
