"""Pydantic v2 configuration models for pyharness.

Mirrors OpenCode's `opencode.json` schema with Pythonic type safety.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Custom types
# ---------------------------------------------------------------------------

# PermissionValue: either a single action string or a dict of glob → action
PermissionValue = (
    str  # "allow" | "ask" | "deny" (applies to all)
    | dict[str, str]  # {"*" : "ask", "git *": "allow", ...}
)

# Model string format: "provider:model-id"
# Allows slashes for OpenRouter-style IDs like "openai/gpt-5"
MODEL_STRING_PATTERN = r"^(?:([\w][\w-]*:[\w][\w./-]+))?$"

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProviderConfig(BaseModel):
    """Provider-specific API credentials and defaults."""

    apiKey: str | None = None  # noqa: N815
    baseUrl: str | None = None  # noqa: N815
    options: dict[str, Any] = Field(default_factory=dict)


class AgentPermissionConfig(BaseModel):
    """Per-agent permission overrides."""

    edit: PermissionValue | None = None
    bash: PermissionValue | None = None  # string or glob → action
    read: PermissionValue | None = None
    task: PermissionValue | None = None
    external_directory: PermissionValue | None = None

    model_config = {"extra": "allow"}


class AgentDefinition(BaseModel):
    """Agent definition from pyharness.json or markdown frontmatter."""

    description: str
    mode: Literal["primary", "subagent", "all"] = "all"
    model: str | None = None
    prompt: str | None = None
    temperature: float | None = None
    steps: int | None = None
    permission: AgentPermissionConfig | None = None
    hidden: bool = False
    color: str | None = None

    model_config = {"extra": "allow"}


class AutoIndexConfig(BaseModel):
    """Auto-indexing behaviour for the memory layer."""

    mode: str = "event_driven"
    triggers: list[str] = Field(
        default_factory=lambda: ["session.idle", "session.compacted", "session.end"]
    )

    model_config = {"extra": "allow"}


class WakeUpConfig(BaseModel):
    """Wake-up context injection settings."""

    context_injection: bool = True
    max_results: int = 5
    include_kg: bool = True
    include_diary: bool = True

    model_config = {"extra": "allow"}


class AgentSearchConfig(BaseModel):
    """Agent-initiated memory search settings."""

    enabled: bool = True
    max_results: int = 10

    model_config = {"extra": "allow"}


class MemoryConfig(BaseModel):
    """MemPalace memory configuration."""

    enabled: bool = True
    wing: str = "{project.name}"
    auto_index: AutoIndexConfig = Field(default_factory=AutoIndexConfig)
    wake_up: WakeUpConfig = Field(default_factory=WakeUpConfig)
    agent_search: AgentSearchConfig = Field(default_factory=AgentSearchConfig)

    model_config = {"extra": "allow"}


class MCPServerConfig(BaseModel):
    """MCP server definition — local (stdio) or remote (HTTP)."""

    type: Literal["local", "remote"]
    command: list[str] | None = None
    url: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: dict[str, Any] | None = None
    timeout: int = 5000
    enabled: bool = True

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _validate_local_has_command(self) -> MCPServerConfig:
        if self.type == "local" and not self.command:
            raise ValueError("MCP server of type 'local' requires a 'command' field")
        if self.type == "remote" and not self.url:
            raise ValueError("MCP server of type 'remote' requires a 'url' field")
        return self


class CommandConfig(BaseModel):
    """Custom slash-command definition."""

    template: str
    description: str | None = None
    agent: str | None = None
    model: str | None = None
    subtask: bool = False

    model_config = {"extra": "allow"}


class CompactionConfig(BaseModel):
    """Compaction / context-window management settings."""

    auto: bool = True
    reserved: int = 10000
    prune: bool = False

    model_config = {"extra": "allow"}


class WatcherConfig(BaseModel):
    """File-watcher configuration."""

    ignore: list[str] = Field(
        default_factory=lambda: ["node_modules/**", "dist/**", ".git/**", "__pycache__/**"]
    )

    model_config = {"extra": "allow"}


class PyHarnessConfig(BaseModel):
    """Root configuration model for pyharness.json."""

    model_config = {"extra": "allow"}

    # ---- Logging ----
    log_level: Literal["ERROR", "INFO"] | None = Field(
        default=None,
        description="Log level: None (disabled), ERROR, or INFO",
    )

    # ---- Model selection ----
    model: str = Field(
        default="anthropic:claude-sonnet-4-5",
        pattern=MODEL_STRING_PATTERN,
        description="Default model in 'provider:model-id' format",
    )
    small_model: str = Field(
        default="anthropic:claude-haiku-4-5",
        pattern=MODEL_STRING_PATTERN,
        description="Small / fast model for planning & non-creative tasks",
    )
    autoupdate: bool = True

    # ---- Providers ----
    provider: dict[str, ProviderConfig] = Field(default_factory=dict)

    # ---- Permissions ----
    permission: dict[str, Any] = Field(default_factory=dict)

    # ---- Agents ----
    agent: dict[str, AgentDefinition] = Field(default_factory=dict)

    # ---- Memory ----
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # ---- MCP servers ----
    mcp: dict[str, MCPServerConfig] = Field(default_factory=dict)

    # ---- Custom commands ----
    command: dict[str, CommandConfig] = Field(default_factory=dict)

    # ---- Plugins ----
    plugin: list[str] = Field(default_factory=list)

    # ---- Compaction ----
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)

    # ---- File watcher ----
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    # ---- Instructions ----
    instructions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in default agents (SPEC §5.2)
# ---------------------------------------------------------------------------
# Project config overrides take precedence; these fill in when no definitions
# exist in the config file.

DEFAULT_AGENTS: dict[str, AgentDefinition] = {
    "build": AgentDefinition(
        description="Full tool access for implementation and editing",
        mode="primary",
        permission=AgentPermissionConfig(edit="allow", bash="allow", read="allow"),
    ),
    "plan": AgentDefinition(
        description="Read-only analysis and planning — cannot modify files or execute commands",
        mode="primary",
        model=None,  # Uses small_model from config
        permission=AgentPermissionConfig(edit="deny", bash="deny", read="allow"),
    ),
    "general": AgentDefinition(
        description="General-purpose subagent for multi-step tasks with full tool access",
        mode="subagent",
        permission=AgentPermissionConfig(edit="allow", bash="allow", read="allow"),
    ),
    "explore": AgentDefinition(
        description="Read-only codebase exploration and search — fast, cannot modify files",
        mode="subagent",
        permission=AgentPermissionConfig(edit="deny", bash="deny", read="allow"),
    ),
}
