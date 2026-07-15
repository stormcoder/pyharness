"""pyharness configuration layer — Pydantic v2 schema + loader.

Usage::

    from pyharness.config import PyHarnessConfig, load_config

    config = load_config()
    print(config.model)
"""

from __future__ import annotations

from .loader import load_config, merge_configs, resolve_env_vars
from .schema import (
    AgentDefinition,
    AgentPermissionConfig,
    CommandConfig,
    CompactionConfig,
    DEFAULT_AGENTS,
    MCPServerConfig,
    MemoryConfig,
    ProviderConfig,
    PyHarnessConfig,
)

__all__ = [
    "PyHarnessConfig",
    "AgentDefinition",
    "AgentPermissionConfig",
    "CommandConfig",
    "CompactionConfig",
    "DEFAULT_AGENTS",
    "MCPServerConfig",
    "MemoryConfig",
    "ProviderConfig",
    "load_config",
    "merge_configs",
    "resolve_env_vars",
]
