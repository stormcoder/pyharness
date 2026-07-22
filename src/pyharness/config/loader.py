"""Configuration file discovery, merging, and env-var resolution.

Load order (SPEC §4.1):
1. ~/.config/pyharness/pyharness.json  (global)
2. $PYHARNESS_CONFIG                   (custom path)
3. .pyharness/pyharness.json           (project root)
4. $PYHARNESS_CONFIG_CONTENT           (inline JSON)
"""

from __future__ import annotations

import json
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

    # Load custom agents from markdown directories (global + project)
    from pyharness.config.agent_loader import discover_agent_directories, load_agents_from_directory

    project_root = cwd or Path.cwd()
    for agents_dir in discover_agent_directories(project_root):
        custom_agents = load_agents_from_directory(agents_dir)
        resolved.setdefault("agent", {})
        for name, agent_def in custom_agents.items():
            if name not in resolved.get("agent", {}):
                resolved["agent"][name] = agent_def.model_dump()

    return PyHarnessConfig.model_validate(resolved)


def save_config(config: PyHarnessConfig, target: str = "global") -> None:
    """Persist *config* to disk, preserving JSONC comments where possible.

    Args:
        config: The validated ``PyHarnessConfig`` to serialise.
        target: ``"global"`` → ``~/.config/pyharness/pyharness.json``.
                The ``PYHARNESS_CONFIG`` env var overrides the path.

    Implementation notes:
        * Reads the existing file with ``json5.loads()`` to preserve comments.
        * Deep-merges the pydantic model dump into the existing dict.
        * Writes with ``json.dumps(indent=2)`` (json5 does not support write).
        * Creates parent directories if they do not exist.
        * Provider keys already stored as ``{env:VAR}`` placeholders are
          preserved; newly-added keys are written as plain strings.
    """
    # Determine the target path.
    # PYHARNESS_CONFIG overrides only the default global path —
    # explicit targets (e.g. from test fixtures) are always honoured.
    if target != "global":
        config_path = Path(target)
    else:
        env_path = os.environ.get("PYHARNESS_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            config_path = Path.home() / ".config" / "pyharness" / "pyharness.json"

    # Read the existing file (if any) with json5 to detect env placeholders
    existing: dict[str, Any] = {}
    env_placeholders: dict[str, str] = {}  # provider_name → original apiKey
    if config_path.exists():
        try:
            raw_text = config_path.read_text(encoding="utf-8")
            existing = _parse_json(raw_text)
            # Sniff which provider keys used env placeholders
            for pname, pconf in existing.get("provider", {}).items():
                if isinstance(pconf, dict):
                    key_val = pconf.get("apiKey", "")
                    if isinstance(key_val, str) and key_val.startswith("{env:"):
                        env_placeholders[pname] = key_val
        except (ValueError, OSError):
            pass

    # Build the model dump and restore env placeholders for providers
    # that already had them — the config holds *resolved* values, but the
    # file should keep the placeholder.
    model_dump = config.model_dump(exclude_none=True, mode="python")
    model_providers = model_dump.get("provider", {})
    for pname in env_placeholders:
        if pname in model_providers and isinstance(model_providers[pname], dict):
            model_providers[pname]["apiKey"] = env_placeholders[pname]

    # Deep-merge model dump into existing dict (model dump wins except for env placeholders)
    merged = _merge_configs(existing, model_dump)

    # Provider section is a REPLACE, not a merge: the in-memory config is
    # the canonical source of truth for which providers exist.  Without
    # this, stale provider entries survive every save_config() call and
    # can never be removed.
    if "provider" in model_dump and isinstance(model_dump["provider"], dict):
        merged["provider"] = model_dump["provider"]

    # Ensure parent directories exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with json (json5 has no dump function)
    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


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

    Special case: ``provider`` dicts are merged per-provider so that
    override wins for directly-specified keys within each provider,
    while base-only providers survive.
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key == "provider" and isinstance(value, dict) and isinstance(result.get(key), dict):
            # Per-provider merge: for each provider in either base or
            # override, override keys win but base keys fill gaps.
            merged_prov: dict[str, Any] = {}
            all_providers = set(result[key]) | set(value)
            for pk in all_providers:
                base_pv = result[key].get(pk, {})
                ov_pv = value.get(pk, {})
                if isinstance(base_pv, dict) and isinstance(ov_pv, dict):
                    merged_prov[pk] = {**base_pv, **ov_pv}
                elif ov_pv:
                    merged_prov[pk] = deepcopy(ov_pv)
                else:
                    merged_prov[pk] = deepcopy(base_pv)
            result[key] = merged_prov
        elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
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
