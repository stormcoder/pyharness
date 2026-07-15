"""Configuration file discovery, merging, and env-var resolution.

Load order (SPEC §4.1):
1. ~/.config/pyharness/pyharness.json  (global)
2. $PYHARNESS_CONFIG                   (custom path)
3. .pyharness/pyharness.json           (project root)
4. $PYHARNESS_CONFIG_CONTENT           (inline JSON)
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import json5

from .schema import DEFAULT_AGENTS, PyHarnessConfig

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(cwd: Path | None = None) -> PyHarnessConfig:
    """Discover and merge configs in precedence order, returning a validated config."""
    merged: dict[str, Any] = {}

    # 1. Global config
    global_path = Path.home() / ".config" / "pyharness" / "pyharness.json"
    if global_path.exists():
        merged = _load_file(global_path)

    # 2. Custom config path via env var
    custom_path = os.environ.get("PYHARNESS_CONFIG")
    if custom_path:
        custom = _load_file(Path(custom_path))
        merged = _merge_configs(merged, custom)

    # 3. Project config — walk up to git root
    if cwd is None:
        cwd = Path.cwd()
    project_config = _find_project_config(cwd)
    if project_config:
        project = _load_file(project_config)
        merged = _merge_configs(merged, project)

    # 4. Inline config via env var
    inline = os.environ.get("PYHARNESS_CONFIG_CONTENT")
    if inline:
        parsed = _parse_json(inline)
        merged = _merge_configs(merged, parsed)

    # Resolve {env:VAR} and {file:path} placeholders
    resolved = _resolve_env_vars(merged)

    # Inject built-in default agent definitions (project config overrides win)
    for agent_name, agent_def in DEFAULT_AGENTS.items():
        resolved.setdefault("agent", {})
        if agent_name not in resolved.get("agent", {}):
            resolved["agent"][agent_name] = agent_def.model_dump()

    return PyHarnessConfig.model_validate(resolved)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_file(path: Path) -> dict[str, Any]:
    """Load a JSON or JSONC file, returning parsed dict."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return _parse_json(path.read_text(encoding="utf-8"))


def _parse_json(text: str) -> dict[str, Any]:
    """Parse JSON or JSONC text into a dict."""
    parsed = json5.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Config must be a JSON object (dict)")
    return parsed


def _find_project_config(start: Path) -> Path | None:
    """Walk from *start* up to the nearest git root looking for
    ``pyharness.json`` or ``.pyharness/pyharness.json``.
    """
    root = _git_root(start) or start
    current = start.resolve()
    while current != root.parent:
        for name in ("pyharness.json", ".pyharness/pyharness.json"):
            candidate = current / name
            if candidate.is_file():
                return candidate
            # also try .jsonc variant
            candidate_jsonc = current / name.replace(".json", ".jsonc")
            if candidate_jsonc.is_file():
                return candidate_jsonc
        if current == root:
            break
        current = current.parent
    return None


def _git_root(path: Path) -> Path | None:
    """Find the git root directory for *path*."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def _merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base*.  Dicts merge recursively;
    lists and scalars are replaced.
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _resolve_env_vars(obj: Any) -> Any:
    """Walk *obj* recursively, replacing ``{env:VAR}`` and ``{file:path}``
    placeholders in string values.
    """
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    if isinstance(obj, str):
        return _resolve_placeholders(obj)
    return obj


_PLACEHOLDER_RE = re.compile(r"\{(env|file):([^}]+)\}")


def _resolve_placeholders(value: str) -> str:
    """Replace ``{env:VAR}`` / ``{file:PATH}`` inside a single string."""
    def _replacer(match: re.Match[str]) -> str:
        kind, key = match.groups()
        if kind == "env":
            return os.environ.get(key, "")
        if kind == "file":
            try:
                return Path(key).read_text(encoding="utf-8").strip()
            except Exception:
                return ""
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replacer, value)


# Compatibility aliases
merge_configs = _merge_configs
resolve_env_vars = _resolve_env_vars
