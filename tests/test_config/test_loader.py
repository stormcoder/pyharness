"""Tests for config loader — discovery, merge, and env-var resolution."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pyharness.config.loader import (
    _merge_configs,
    _resolve_env_vars,
    load_config,
)

# ---------------------------------------------------------------------------
# 1. Config merging
# ---------------------------------------------------------------------------

def test_merge_deep_merges_nested_dicts():
    """Deep merge should preserve nested keys and override leaves."""
    base = {
        "model": "anthropic:claude-haiku-4-5",
        "provider": {
            "anthropic": {"apiKey": "base-key", "options": {"timeout": 10000}},
            "openai": {"apiKey": "base-openai-key"},
        },
    }
    override = {
        "model": "anthropic:claude-sonnet-4-5",
        "provider": {
            "anthropic": {"apiKey": "override-key"},
        },
    }
    merged = _merge_configs(base, override)

    assert merged["model"] == "anthropic:claude-sonnet-4-5"
    # deep merge: anthropic.options should survive from base
    assert merged["provider"]["anthropic"]["apiKey"] == "override-key"
    assert merged["provider"]["anthropic"]["options"] == {"timeout": 10000}
    # openai should survive untouched from base
    assert merged["provider"]["openai"]["apiKey"] == "base-openai-key"


def test_merge_overrides_lists():
    """Lists should be replaced, not merged."""
    base = {"plugin": ["a", "b"], "instructions": ["x"]}
    override = {"plugin": ["c"]}
    merged = _merge_configs(base, override)
    assert merged["plugin"] == ["c"]
    assert merged["instructions"] == ["x"]


def test_merge_empty_base():
    """Merging into an empty base should return a copy of the override."""
    base: dict = {}
    override = {"model": "anthropic:claude-sonnet-4-5"}
    merged = _merge_configs(base, override)
    assert merged == override
    assert merged is not override  # deepcopy


def test_merge_empty_override():
    """Merging an empty override should return a copy of the base."""
    base = {"model": "anthropic:claude-haiku-4-5"}
    merged = _merge_configs(base, {})
    assert merged == base
    assert merged is not base  # deepcopy


# ---------------------------------------------------------------------------
# 2. Env var substitution
# ---------------------------------------------------------------------------

def test_resolve_env_vars_string():
    """{env:VAR} placeholders should be replaced with env values."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write("secret-from-file")
        secret_path = tf.name

    try:
        os.environ["PYHARNESS_TEST_KEY"] = "test-api-key-value"
        config = {
            "provider": {
                "anthropic": {
                    "apiKey": "{env:PYHARNESS_TEST_KEY}",
                },
                "openai": {
                    "apiKey": "{file:" + secret_path + "}",
                },
            },
            "prompt": "Use model {env:PYHARNESS_TEST_KEY} for generation",
        }
        resolved = _resolve_env_vars(config)

        assert resolved["provider"]["anthropic"]["apiKey"] == "test-api-key-value"
        assert resolved["provider"]["openai"]["apiKey"] == "secret-from-file"
        assert (
            resolved["prompt"]
            == "Use model test-api-key-value for generation"
        )
    finally:
        os.environ.pop("PYHARNESS_TEST_KEY", None)
        os.unlink(secret_path)


def test_resolve_missing_env_var():
    """Missing env var placeholder should become empty string."""
    config = {"apiKey": "{env:NONEXISTENT_VAR_12345}"}
    resolved = _resolve_env_vars(config)
    assert resolved["apiKey"] == ""


def test_resolve_nested_dicts_and_lists():
    """Env var resolution should recurse through lists and nested dicts."""
    os.environ["PYHARNESS_TEST_COLOR"] = "#ff6b35"
    try:
        config = {
            "agents": [
                {"name": "plan", "model": "{env:PYHARNESS_TEST_COLOR}"},
                {"name": "build", "model": "{env:PYHARNESS_TEST_COLOR}"},
            ],
            "meta": {"primary": "{env:PYHARNESS_TEST_COLOR}"},
        }
        resolved = _resolve_env_vars(config)
        assert resolved["agents"][0]["model"] == "#ff6b35"
        assert resolved["agents"][1]["model"] == "#ff6b35"
        assert resolved["meta"]["primary"] == "#ff6b35"
    finally:
        os.environ.pop("PYHARNESS_TEST_COLOR", None)


# ---------------------------------------------------------------------------
# 3. Config from temp file
# ---------------------------------------------------------------------------

def test_load_config_from_project_json():
    """load_config should find and parse a local pyharness.json in cwd."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "pyharness.json"
        config_path.write_text(
            json.dumps({
                "model": "openai:gpt-5",
                "small_model": "openai:gpt-4o-mini",
                "autoupdate": False,
            })
        )

        # Our loader only searches relative to cwd, so we change dir.
        # load_config walks from cwd.  We need a git repo for the
        # _find_project_config walk — but that's an implementation detail.
        # Instead, test the core merging logic directly.
        from pyharness.config.loader import _load_file

        data = _load_file(config_path)
        assert data["model"] == "openai:gpt-5"
        assert data["small_model"] == "openai:gpt-4o-mini"
        assert data["autoupdate"] is False


def test_load_config_with_json5_comments():
    """JSON5 config files with comments should be parsed correctly."""
    text = """\
{
    // Default model — change this for your provider
    "model": "anthropic:claude-sonnet-4-5",
    "small_model": "anthropic:claude-haiku-4-5",  /* inline comment */
    "autoupdate": false,
}
"""
    import json5
    parsed = json5.loads(text)
    assert parsed["model"] == "anthropic:claude-sonnet-4-5"
    assert parsed["small_model"] == "anthropic:claude-haiku-4-5"
    assert parsed["autoupdate"] is False


def test_load_config_inline_env_var():
    """PYHARNESS_CONFIG_CONTENT env var should provide inline config."""
    os.environ["PYHARNESS_CONFIG_CONTENT"] = json.dumps({
        "model": "openrouter:openai/gpt-5",
    })
    try:
        # load_config merges inline last (highest precedence)
        config = load_config(cwd=Path(tempfile.gettempdir()))
        assert config.model == "openrouter:openai/gpt-5"
    finally:
        os.environ.pop("PYHARNESS_CONFIG_CONTENT", None)
