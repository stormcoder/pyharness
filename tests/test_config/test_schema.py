"""Tests for pyharness config schema models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyharness.config.schema import (
    AgentDefinition,
    AgentPermissionConfig,
    MCPServerConfig,
    MemoryConfig,
    ProviderConfig,
    PyHarnessConfig,
)

# ---------------------------------------------------------------------------
# 1. Minimal config parses correctly
# ---------------------------------------------------------------------------

def test_minimal_config_parses():
    """A config with only required fields should parse with all defaults."""
    data = {}
    config = PyHarnessConfig.model_validate(data)

    assert config.model == "anthropic:claude-sonnet-4-5"
    assert config.small_model == "anthropic:claude-haiku-4-5"
    assert config.autoupdate is True
    assert config.provider == {}
    assert config.permission == {}
    assert config.agent == {}
    assert isinstance(config.memory, MemoryConfig)
    assert config.memory.enabled is True
    assert config.mcp == {}
    assert config.command == {}
    assert config.plugin == []
    assert config.compaction.auto is True
    assert config.instructions == []


def test_minimal_config_roundtrip():
    """model_dump + model_validate round-trip should be identity for defaults."""
    config = PyHarnessConfig()
    data = config.model_dump()
    config2 = PyHarnessConfig.model_validate(data)
    assert config2.model == config.model
    assert config2.memory.enabled == config.memory.enabled


# ---------------------------------------------------------------------------
# 2. Invalid model string is rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_model",
    [
        "invalid-model-no-colon",
        "",                         # empty
        "provider:",                 # no model-id
        ":model-id",                # no provider
        "   anthropic:claude  ",    # leading space fails pattern
        "anthropic:claude sonnet",  # space in model-id
    ],
)
def test_invalid_model_string_rejected(bad_model: str):
    """Model must match 'provider:model-id' pattern."""
    with pytest.raises(ValidationError) as exc_info:
        PyHarnessConfig.model_validate({"model": bad_model})
    assert "model" in str(exc_info.value).lower() or any(
        "model" in str(e["loc"]) for e in exc_info.value.errors()
    ), f"Expected model validation error for {bad_model!r}"


# ---------------------------------------------------------------------------
# 3. Agent definition with all fields parses
# ---------------------------------------------------------------------------

def test_agent_definition_all_fields():
    """AgentDefinition should accept every documented field."""
    data = {
        "description": "Reviews code for best practices",
        "mode": "subagent",
        "model": "anthropic:claude-sonnet-4-5",
        "prompt": "You are a code reviewer. Focus on security.",
        "temperature": 0.1,
        "steps": 10,
        "permission": {
            "edit": "deny",
            "bash": {"*": "deny", "git *": "allow"},
            "read": "allow",
        },
        "hidden": True,
        "color": "#ff6b35",
        "extra_field": "should be allowed",  # extra is OK
    }

    agent = AgentDefinition.model_validate(data)
    assert agent.description == "Reviews code for best practices"
    assert agent.mode == "subagent"
    assert agent.model == "anthropic:claude-sonnet-4-5"
    assert agent.temperature == 0.1
    assert agent.steps == 10
    assert agent.permission is not None
    assert agent.permission.edit == "deny"
    assert agent.permission.bash == {"*": "deny", "git *": "allow"}
    assert agent.hidden is True
    assert agent.color == "#ff6b35"


def test_agent_definition_minimal():
    """Only description is required."""
    agent = AgentDefinition.model_validate({"description": "A test agent"})
    assert agent.description == "A test agent"
    assert agent.mode == "all"
    assert agent.hidden is False


# ---------------------------------------------------------------------------
# 4. MCP server config validates type/command consistency
# ---------------------------------------------------------------------------

def test_mcp_local_validates_command_required():
    """local MCP servers must provide a command."""
    with pytest.raises(ValidationError, match="command"):
        MCPServerConfig.model_validate({"type": "local"})


def test_mcp_local_with_command_ok():
    """local MCP server with command is valid."""
    srv = MCPServerConfig.model_validate(
        {"type": "local", "command": ["uv", "run", "my-server"]}
    )
    assert srv.type == "local"
    assert srv.command == ["uv", "run", "my-server"]


def test_mcp_remote_validates_url_required():
    """remote MCP servers must provide a url."""
    with pytest.raises(ValidationError, match="url"):
        MCPServerConfig.model_validate({"type": "remote"})


def test_mcp_remote_with_url_ok():
    """remote MCP server with url is valid."""
    srv = MCPServerConfig.model_validate(
        {"type": "remote", "url": "https://mcp.sentry.dev/mcp"}
    )
    assert srv.type == "remote"
    assert srv.url == "https://mcp.sentry.dev/mcp"


def test_mcp_defaults():
    """MCP server config should have sensible defaults."""
    srv = MCPServerConfig.model_validate(
        {"type": "local", "command": ["echo", "hello"]}
    )
    assert srv.timeout == 5000
    assert srv.enabled is True
    assert srv.environment == {}
    assert srv.headers == {}


# ---------------------------------------------------------------------------
# 5. Permission config with glob patterns
# ---------------------------------------------------------------------------

def test_permission_config_glob_patterns():
    """AgentPermissionConfig should accept string and glob-dict values."""
    perm = AgentPermissionConfig.model_validate({
        "edit": "allow",
        "bash": {
            "*": "ask",
            "git *": "allow",
            "grep *": "allow",
            "pip install *": "ask",
        },
        "read": "allow",
        "external_directory": "ask",
    })

    assert perm.edit == "allow"
    assert perm.bash == {
        "*": "ask",
        "git *": "allow",
        "grep *": "allow",
        "pip install *": "ask",
    }
    assert perm.external_directory == "ask"


def test_permission_config_defaults():
    """Empty AgentPermissionConfig should have all None values."""
    perm = AgentPermissionConfig()
    assert perm.edit is None
    assert perm.bash is None
    assert perm.read is None
    assert perm.task is None


# ---------------------------------------------------------------------------
# 6. Full config with nested objects
# ---------------------------------------------------------------------------

def test_full_config_with_providers_and_agents():
    """End-to-end: a realistic pyharness.json should parse fully."""
    data = {
        "model": "anthropic:claude-sonnet-4-5",
        "small_model": "anthropic:claude-haiku-4-5",
        "provider": {
            "anthropic": {
                "apiKey": "{env:ANTHROPIC_API_KEY}",
                "options": {"timeout": 600000},
            },
            "openai": {
                "apiKey": "{env:OPENAI_API_KEY}",
            },
        },
        "permission": {
            "edit": "allow",
            "bash": {"*": "ask", "git *": "allow"},
        },
        "agent": {
            "plan": {
                "description": "Strategic planning agent",
                "mode": "primary",
                "model": "anthropic:claude-haiku-4-5",
                "permission": {"edit": "deny", "bash": "deny"},
            },
            "code-reviewer": {
                "description": "Reviews code for quality",
                "mode": "subagent",
                "prompt": "You are a code reviewer.",
                "permission": {"edit": "deny"},
            },
        },
        "mcp": {
            "sentry": {
                "type": "remote",
                "url": "https://mcp.sentry.dev/mcp",
                "oauth": {},
            },
            "local-server": {
                "type": "local",
                "command": ["uv", "run", "my-mcp-server"],
            },
        },
        "command": {
            "test": {
                "template": "Run the full test suite with coverage",
                "description": "Run tests with coverage",
            }
        },
        "plugin": ["pyharness-helicone"],
        "compaction": {"auto": True, "reserved": 10000, "prune": False},
        "instructions": ["CONTRIBUTING.md"],
    }

    config = PyHarnessConfig.model_validate(data)

    # Providers
    assert "anthropic" in config.provider
    assert config.provider["anthropic"].apiKey == "{env:ANTHROPIC_API_KEY}"
    assert config.provider["anthropic"].options == {"timeout": 600000}

    # Agents
    assert "plan" in config.agent
    assert config.agent["plan"].mode == "primary"
    assert config.agent["plan"].permission is not None
    assert config.agent["plan"].permission.edit == "deny"

    assert "code-reviewer" in config.agent
    assert config.agent["code-reviewer"].permission is not None
    assert config.agent["code-reviewer"].permission.edit == "deny"

    # MCP
    assert "sentry" in config.mcp
    assert config.mcp["sentry"].type == "remote"
    assert "local-server" in config.mcp
    assert config.mcp["local-server"].type == "local"

    # Commands
    assert "test" in config.command
    assert config.command["test"].template == "Run the full test suite with coverage"

    # Plugins & instructions
    assert config.plugin == ["pyharness-helicone"]
    assert config.instructions == ["CONTRIBUTING.md"]


# ---------------------------------------------------------------------------
# 7. Provider config
# ---------------------------------------------------------------------------

def test_provider_config_defaults():
    """ProviderConfig should be empty by default."""
    prov = ProviderConfig()
    assert prov.apiKey is None
    assert prov.baseUrl is None
    assert prov.options == {}


def test_provider_config_with_values():
    """ProviderConfig with all fields set."""
    prov = ProviderConfig(
        apiKey="sk-123",
        baseUrl="https://api.anthropic.com",
        options={"timeout": 30000, "max_retries": 3},
    )
    assert prov.apiKey == "sk-123"
    assert prov.baseUrl == "https://api.anthropic.com"
    assert prov.options["timeout"] == 30000


# ---------------------------------------------------------------------------
# 8. Logging config (SPEC §10.5 — structured logging)
# ---------------------------------------------------------------------------
# The PyHarnessConfig must have a log_level field so that pyharness.json
# users can set "log_level": "ERROR" and have it take effect.
# Currently NO SUCH FIELD EXISTS — model_config = {"extra": "allow"}
# silently discards extra keys.  ALL TESTS BELOW MUST FAIL.


class TestLoggingConfig:
    """Logging config must be a first-class field on PyHarnessConfig.

    Currently ``PyHarnessConfig`` has no ``log_level`` field.  Setting
    ``"log_level": "ERROR"`` in ``pyharness.json`` is silently accepted
    (``extra="allow"``) but never read by ``setup_logging()``.  These
    tests define the expected behavior and should FAIL until the field
    is added.
    """

    # ------------------------------------------------------------------
    # TEST 1 — log_level field must exist in the schema model
    # ------------------------------------------------------------------

    def test_log_level_field_exists_in_schema(self) -> None:
        """PyHarnessConfig must have a log_level field.

        The field must be ``Optional[str]`` (or ``str | None``) with a
        default value of ``None`` (meaning: use default INFO logging).

        FAILS: ``PyHarnessConfig`` has no ``log_level`` field.  Extra
        keys in ``pyharness.json`` are silently accepted by
        ``model_config = {"extra": "allow"}`` but never read.
        """
        import inspect
        from typing import get_type_hints

        from pydantic.fields import FieldInfo

        # Check that the field exists on the model class
        fields: dict[str, FieldInfo] = PyHarnessConfig.model_fields
        assert "log_level" in fields, (
            "FAILS: PyHarnessConfig.model_fields does NOT contain 'log_level'.\n"
            "  Expected: Optional[str] log_level = None\n"
            f"  Current fields: {sorted(fields.keys())}\n"
            "  Impact: 'log_level' in pyharness.json is silently discarded."
        )

        # Check the type is Optional[str]
        hints = get_type_hints(PyHarnessConfig)
        assert "log_level" in hints, (
            "FAILS: PyHarnessConfig type hints don't include 'log_level'."
        )

        # Check default value is None
        field = fields["log_level"]
        assert field.default is None, (
            f"FAILS: log_level default must be None, got {field.default!r}"
        )

    # ------------------------------------------------------------------
    # TEST 2 — log_level accepts valid values, rejecting invalid ones
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "value",
        [None, "ERROR", "INFO"],
    )
    def test_log_level_accepts_valid_values(self, value: str | None) -> None:
        """log_level must accept None, 'ERROR', and 'INFO'.

        FAILS: field does not exist — validation cannot be tested.
        """
        data: dict[str, object] = {}
        if value is not None:
            data["log_level"] = value
        config = PyHarnessConfig.model_validate(data)

        if "log_level" in PyHarnessConfig.model_fields:
            actual = config.log_level  # type: ignore[attr-defined]
            assert actual == value, (
                f"FAILS: log_level was {actual!r}, expected {value!r}"
            )
        else:
            pytest.fail(
                "FAILS: PyHarnessConfig has no 'log_level' field.\n"
                "  model_validate() silently discards extra keys (extra='allow').\n"
                "  Setting 'log_level' in pyharness.json has no effect."
            )

    # ------------------------------------------------------------------
    # TEST 3 — invalid log_level values are rejected
    # ------------------------------------------------------------------

    def test_log_level_invalid_value_rejected(self) -> None:
        """log_level='DEBUG' must raise ValidationError.

        Only None, 'ERROR', and 'INFO' are valid values.

        FAILS: field does not exist, so any value is silently accepted
        as an "extra" field.
        """
        # First verify the field exists; if not, test cannot assert rejection
        if "log_level" not in PyHarnessConfig.model_fields:
            pytest.fail(
                "FAILS: PyHarnessConfig has no 'log_level' field.\n"
                "  Extra keys are silently accepted (extra='allow').\n"
                "  'log_level': 'DEBUG' would be discarded, not rejected."
            )

        with pytest.raises(ValidationError) as exc_info:
            PyHarnessConfig.model_validate({"log_level": "DEBUG"})
        errors = exc_info.value.errors()
        assert any("log_level" in str(e.get("loc", [])) for e in errors), (
            f"FAILS: 'DEBUG' must be rejected as invalid log_level.\n"
            f"  Got errors: {errors}"
        )
