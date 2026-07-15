"""Tests for PermissionMiddleware."""

from __future__ import annotations

from pyharness.config.schema import (
    AgentDefinition,
    AgentPermissionConfig,
    PyHarnessConfig,
)
from pyharness.middleware.permission import PermissionMiddleware, PermissionResult

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
                permission=AgentPermissionConfig.model_validate(
                    agent_perms
                ),
            )
        }
    return PyHarnessConfig.model_validate(data)


# ---------------------------------------------------------------------------
# 1.  Default allow
# ---------------------------------------------------------------------------


def test_default_allow() -> None:
    """No config rules → every tool is allowed."""
    config = PyHarnessConfig()  # empty
    mw = PermissionMiddleware(config, agent_name="build")

    for tool in ("read", "bash", "edit", "write", "task"):
        result = mw.check(tool)
        assert result.action == "allow", f"{tool} should be allow by default"


# ---------------------------------------------------------------------------
# 2.  Global deny
# ---------------------------------------------------------------------------


def test_global_deny_bash() -> None:
    """Global ``bash: deny`` blocks bash invocations."""
    config = _make_config(global_perms={"bash": "deny"})
    mw = PermissionMiddleware(config, agent_name="build")

    result = mw.check("bash")
    assert result.action == "deny"
    assert "Permission denied" in result.reason

    # Other tools are still allowed
    assert mw.check("read").action == "allow"
    assert mw.check("edit").action == "allow"


# ---------------------------------------------------------------------------
# 3.  Agent override
# ---------------------------------------------------------------------------


def test_agent_override_allows() -> None:
    """An agent-level ``allow`` overrides a global ``deny``."""
    config = _make_config(
        global_perms={"bash": "deny"},
        agent_perms={"bash": "allow"},
    )
    mw = PermissionMiddleware(config, agent_name="build")

    result = mw.check("bash")
    assert result.action == "allow"


def test_agent_override_denies() -> None:
    """An agent-level ``deny`` overrides a global ``allow``."""
    config = _make_config(
        global_perms={"edit": "allow"},
        agent_perms={"edit": "deny"},
    )
    mw = PermissionMiddleware(config, agent_name="build")

    result = mw.check("edit")
    assert result.action == "deny"


# ---------------------------------------------------------------------------
# 4.  Glob pattern matching for bash commands
# ---------------------------------------------------------------------------


def test_glob_pattern_matching() -> None:
    """``"git *"`` glob matches ``"git status"``."""
    config = _make_config(
        global_perms={
            "bash": {
                "*": "ask",
                "git *": "allow",
            }
        }
    )
    mw = PermissionMiddleware(config, agent_name="build")

    # "git status" matches "git *" → allow
    result = mw.check("bash", args={"command": "git status"})
    assert result.action == "allow"

    # "git diff" also matches
    result = mw.check("bash", args={"command": "git diff"})
    assert result.action == "allow"


def test_glob_pattern_no_match() -> None:
    """A glob that doesn't match falls through to the wildcard default."""
    config = _make_config(
        global_perms={
            "bash": {
                "*": "ask",
                "git *": "allow",
            }
        }
    )
    mw = PermissionMiddleware(config, agent_name="build")

    # "rm file" doesn't match "git *" → falls through to "*" → ask
    result = mw.check("bash", args={"command": "rm file"})
    assert result.action == "ask"


def test_glob_pattern_asterisk_only() -> None:
    """"*" alone should match any bash command."""
    config = _make_config(
        global_perms={"bash": {"*": "allow"}}
    )
    mw = PermissionMiddleware(config, agent_name="build")

    result = mw.check("bash", args={"command": "anything at all"})
    assert result.action == "allow"


# ---------------------------------------------------------------------------
# 5.  Ask action
# ---------------------------------------------------------------------------


def test_ask_action_returns_ask_result() -> None:
    """Permission level ``ask`` returns an ask result with reason."""
    config = _make_config(
        global_perms={"bash": "ask"},
    )
    mw = PermissionMiddleware(config, agent_name="build")

    result = mw.check("bash", args={"command": "rm file"})
    assert result.action == "ask"
    assert "Approval required" in result.reason


# ---------------------------------------------------------------------------
# 6.  write/edit grouping
# ---------------------------------------------------------------------------


def test_write_uses_edit_permission() -> None:
    """``write`` tools are grouped under the ``edit`` permission key."""
    config = _make_config(
        global_perms={"edit": "deny"},
    )
    mw = PermissionMiddleware(config, agent_name="build")

    assert mw.check("edit").action == "deny"
    assert mw.check("write").action == "deny"

    # read is unaffected
    assert mw.check("read").action == "allow"


# ---------------------------------------------------------------------------
# 7.  Agent-specific bash globs
# ---------------------------------------------------------------------------


def test_agent_bash_globs_override_global() -> None:
    """Agent-level bash dict overrides global bash dict entirely."""
    config = _make_config(
        global_perms={
            "bash": {
                "*": "deny",
            }
        },
        agent_perms={
            "bash": {
                "git *": "allow",
                "*": "ask",
            }
        },
    )
    mw = PermissionMiddleware(config, agent_name="build")

    # Agent rules take precedence
    assert mw.check("bash", args={"command": "git push"}).action == "allow"
    assert mw.check("bash", args={"command": "rm file"}).action == "ask"


# ---------------------------------------------------------------------------
# 8.  Missing agent permission falls back to global
# ---------------------------------------------------------------------------


def test_missing_agent_perm_falls_back_to_global() -> None:
    """If the agent has no override for a tool, global rules apply."""
    config = _make_config(
        global_perms={"read": "ask"},
        agent_perms={"bash": "deny"},  # only bash overridden
    )
    mw = PermissionMiddleware(config, agent_name="build")

    # Agent didn't override read → global "ask" applies
    assert mw.check("read").action == "ask"
    # Agent did override bash → agent's "deny" applies
    assert mw.check("bash").action == "deny"


# ---------------------------------------------------------------------------
# 9.  PermissionResult dataclass
# ---------------------------------------------------------------------------


def test_permission_result_defaults() -> None:
    """PermissionResult defaults to empty reason."""
    r = PermissionResult("allow")
    assert r.action == "allow"
    assert r.reason == ""

    r2 = PermissionResult("deny", reason="nope")
    assert r2.action == "deny"
    assert r2.reason == "nope"


# ---------------------------------------------------------------------------
# 10.  Unknown agent name
# ---------------------------------------------------------------------------


def test_unknown_agent_falls_back_to_global() -> None:
    """When the agent name isn't in config, only global rules apply."""
    config = _make_config(
        global_perms={"bash": "deny"},
        agent_perms={"bash": "allow"},  # only for "build"
    )
    mw = PermissionMiddleware(config, agent_name="plan")  # not in config

    # plan agent has no override → global deny applies
    result = mw.check("bash")
    assert result.action == "deny"


# ---------------------------------------------------------------------------
# 11.  Edge case: no args provided
# ---------------------------------------------------------------------------


def test_no_args_bash_uses_empty_command() -> None:
    """When bash is called with no args, command defaults to ''."""
    config = _make_config(
        global_perms={
            "bash": {
                "*": "ask",
                "git *": "allow",
            }
        },
    )
    mw = PermissionMiddleware(config, agent_name="build")

    # No args → command is ""
    result = mw.check("bash", args=None)
    assert result.action == "ask"  # falls through to "*"
