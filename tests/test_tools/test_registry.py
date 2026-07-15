"""Tests for the ToolRegistry."""

from __future__ import annotations

import pytest
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Helpers (tool name = function name)
# ---------------------------------------------------------------------------


@tool
def mock_alpha(query: str) -> str:
    """Alpha tool."""
    return f"alpha: {query}"


@tool
def mock_beta(value: int) -> str:
    """Beta tool."""
    return f"beta: {value}"


@tool
def mock_gamma(name: str) -> str:
    """Gamma tool."""
    return f"gamma: {name}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_and_retrieve():
    """Tools can be registered and retrieved by name."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(mock_alpha)
    reg.register(mock_beta)

    assert len(reg) == 2
    assert "mock_alpha" in reg
    assert "mock_beta" in reg
    assert "mock_gamma" not in reg

    tool = reg.get_tool("mock_alpha")
    assert tool.name == "mock_alpha"

    # get_all returns both
    all_tools = reg.get_all()
    assert len(all_tools) == 2
    names = {t.name for t in all_tools}
    assert names == {"mock_alpha", "mock_beta"}


def test_get_tool_missing_raises():
    """get_tool raises KeyError for unknown names."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(mock_alpha)

    with pytest.raises(KeyError, match="nope"):
        reg.get_tool("nope")


def test_permission_filtering():
    """get_for_agent filters tools by deny rules."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register_all([mock_alpha, mock_beta, mock_gamma])

    # No permissions → all tools allowed
    assert len(reg.get_for_agent()) == 3
    assert len(reg.get_for_agent(permissions={})) == 3

    # Deny mock_beta only
    filtered = reg.get_for_agent(permissions={"mock_beta": "deny"})
    filtered_names = {t.name for t in filtered}
    assert filtered_names == {"mock_alpha", "mock_gamma"}

    # Allow only mock_alpha
    filtered = reg.get_for_agent(
        permissions={"*": "deny", "mock_alpha": "allow"}
    )
    assert {t.name for t in filtered} == {"mock_alpha"}

    # Sub-glob deny
    filtered = reg.get_for_agent(
        permissions={"mock_*": {"mock_beta": "deny"}}
    )
    assert "mock_beta" not in {t.name for t in filtered}
    assert "mock_alpha" in {t.name for t in filtered}


def test_register_all():
    """register_all adds multiple tools at once."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register_all([mock_alpha, mock_beta, mock_gamma])

    assert len(reg) == 3
    assert reg.get_names() == ["mock_alpha", "mock_beta", "mock_gamma"]


def test_register_replaces_existing():
    """Registering a tool with the same name replaces the old one."""

    @tool
    def mock_alpha(x: int) -> str:  # noqa: F811
        """Alpha v2."""
        return f"v2: {x}"

    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(mock_alpha)

    assert len(reg) == 1
    result = reg.get_tool("mock_alpha").invoke({"x": "1"})
    assert result == "v2: 1"


def test_singleton_consistency():
    """get_registry always returns the same instance."""
    from pyharness.tools.registry import get_registry

    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_get_for_agent_none_permissions():
    """None permissions returns all tools."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register_all([mock_alpha, mock_beta])
    assert len(reg.get_for_agent(permissions=None)) == 2


def test_len_and_contains():
    """__len__ and __contains__ work correctly."""
    from pyharness.tools.registry import ToolRegistry

    reg = ToolRegistry()
    assert len(reg) == 0
    assert "mock_alpha" not in reg

    reg.register(mock_alpha)
    assert len(reg) == 1
    assert "mock_alpha" in reg
