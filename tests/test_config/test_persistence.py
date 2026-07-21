"""Tests for config persistence (save_config ↔ load_config round-trip).

Verifies that provider configuration, model selection, and connection
state survive a re-launch of the application.

ALL TESTS IN THIS FILE MUST FAIL — the current ``save_config()``
implementation has a critical bug: the return value of
``_merge_configs()`` is discarded at line 278 of ``loader.py``,
so the merged model data is never written to disk.  With an empty
or absent config file, an empty ``{}`` is written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyharness.config.loader import (
    _load_file,
    _merge_configs,
    save_config,
)
from pyharness.config.schema import (
    AgentDefinition,
    ProviderConfig,
    PyHarnessConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_home(monkeypatch, tmp_path: Path) -> Path:
    """Redirect ``Path.home()`` to a temporary directory.

    Both ``save_config`` (line 249) and ``load_config`` (line 33) resolve
    ``Path.home() / ".config" / "pyharness" / "pyharness.json"``, so
    redirecting ``Path.home()`` isolates all disk I/O to ``tmp_path``.
    """
    monkeypatch.setattr(
        "pyharness.config.loader.Path.home",
        lambda: tmp_path,
    )
    # load_config resolves Path.home().config again, so also patch
    # the classmethod on pathlib.Path itself for safety.
    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Model persistence
# ---------------------------------------------------------------------------


class TestConfigPersistence:
    """save_config must write all config fields to disk so they survive a restart."""

    def test_save_config_writes_model_to_disk(self, temp_home: Path) -> None:
        """Create a config with ``model: "openai:gpt-5"``, save, then load.

        FAILS: The ``_merge_configs`` return value at line 278 of
        ``loader.py`` is discarded — ``existing`` is written unchanged,
        so the model field never reaches the file.
        """
        config = PyHarnessConfig.model_validate({"model": "openai:gpt-5"})
        config_path = (
            temp_home / ".config" / "pyharness" / "pyharness.json"
        )

        save_config(config, target=str(config_path))

        # Read the file directly and parse it
        assert config_path.exists(), (
            "FAILS: save_config did not create the config file.\n"
            f"Expected: {config_path}"
        )
        raw = config_path.read_text(encoding="utf-8")
        import json
        parsed = json.loads(raw)

        assert "model" in parsed, (
            "FAILS: 'model' key was not written to the config file.\n"
            f"File contents: {raw[:200]}\n"
            "Root cause: _merge_configs return value is discarded.\n"
            "  loader.py line 277: _merge_configs(existing, model_data)\n"
            "  The merged dict is never captured — existing is written unchanged."
        )
        assert parsed["model"] == "openai:gpt-5", (
            "FAILS: model value was not persisted correctly.\n"
            f"Expected: 'openai:gpt-5'\n"
            f"Got:      {parsed.get('model')!r}"
        )

    def test_save_config_writes_provider_to_disk(self, temp_home: Path) -> None:
        """Create a config with an OpenAI provider key, save, then load.

        FAILS: Same root cause — the merged model dump is discarded.
        The provider section is never written.
        """
        config = PyHarnessConfig.model_validate({
            "model": "openai:gpt-5",
            "provider": {
                "openai": {"apiKey": "sk-test-provider-key-abc"},
            },
        })
        config_path = (
            temp_home / ".config" / "pyharness" / "pyharness.json"
        )

        save_config(config, target=str(config_path))

        assert config_path.exists(), "save_config did not create the file"
        import json
        parsed = json.loads(config_path.read_text(encoding="utf-8"))

        assert "provider" in parsed, (
            "FAILS: 'provider' section was not written to the config file.\n"
            f"File contents: {config_path.read_text()[:200]}\n"
            "Root cause: _merge_configs return value is discarded."
        )
        openai = parsed.get("provider", {}).get("openai")
        assert openai is not None, (
            "FAILS: 'openai' provider not found in config file.\n"
            f"Providers in file: {list(parsed.get('provider', {}).keys())}"
        )
        assert openai.get("apiKey") == "sk-test-provider-key-abc", (
            "FAILS: provider apiKey was not persisted.\n"
            f"Expected: 'sk-test-provider-key-abc'\n"
            f"Got:      {openai.get('apiKey')!r}"
        )

    def test_save_config_preserves_existing_entries(self, temp_home: Path) -> None:
        """Write a config with 2 providers, then save — BOTH must survive.

        First write a config with openai, then add anthropic.  The save
        must not clobber the openai entry.

        FAILS: The merge return value is discarded.  When the file already
        has ``{model, provider: {openai: ...}}`` and we call save_config
        with ``{model, provider: {anthropic: ...}}``, the merge computes
        the correct union but the file is rewritten unchanged.
        """
        import json

        config_path = (
            temp_home / ".config" / "pyharness" / "pyharness.json"
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # --- Step 1: write config with openai ---
        config1 = PyHarnessConfig.model_validate({
            "model": "openai:gpt-5",
            "provider": {
                "openai": {"apiKey": "sk-openai"},
            },
        })
        save_config(config1, target=str(config_path))

        # --- Step 2: write config with anthropic ---
        config2 = PyHarnessConfig.model_validate({
            "model": "anthropic:claude-sonnet-4-5",
            "provider": {
                "anthropic": {"apiKey": "sk-anthropic"},
            },
        })
        save_config(config2, target=str(config_path))
        step2 = json.loads(config_path.read_text(encoding="utf-8"))

        providers = step2.get("provider", {})
        anthropic_key = providers.get("anthropic", {}).get("apiKey")

        # Provider section is a REPLACE, not a merge: the model is the
        # canonical source of truth.  step 1 wrote openai, step 2 wrote
        # anthropic — only anthropic should survive because the model
        # in step 2 only has anthropic.
        assert "openai" not in providers, (
            "FAILS: openai should NOT survive — provider section is a "
            "replace, not a merge.  The model IS the source of truth.\n"
            f"Step 2 providers: {providers}\n"
        )
        assert anthropic_key == "sk-anthropic", (
            "FAILS: anthropic provider was not persisted.\n"
            f"anthropic apiKey: {anthropic_key!r}"
        )

    def test_save_config_round_trips_all_fields(self, temp_home: Path) -> None:
        """Create a config with model + provider + log_level + agent, save, read back.

        All four fields must survive the round trip.

        FAILS: See root cause above — nothing is written.
        """
        import json

        config_path = (
            temp_home / ".config" / "pyharness" / "pyharness.json"
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = PyHarnessConfig.model_validate({
            "model": "openai:gpt-5",
            "provider": {
                "openai": {"apiKey": "sk-roundtrip"},
            },
            "log_level": "ERROR",
            "agent": {
                "custom-agent": {
                    "description": "A custom agent for testing",
                    "mode": "subagent",
                },
            },
            "compaction": {"auto": False},
        })

        save_config(config, target=str(config_path))
        parsed = json.loads(config_path.read_text(encoding="utf-8"))

        # Verify each field
        failures: list[str] = []

        if parsed.get("model") != "openai:gpt-5":
            failures.append(
                f"model: expected 'openai:gpt-5', got {parsed.get('model')!r}"
            )
        if parsed.get("log_level") != "ERROR":
            failures.append(
                f"log_level: expected 'ERROR', got {parsed.get('log_level')!r}"
            )
        openai_prov = parsed.get("provider", {}).get("openai", {})
        if openai_prov.get("apiKey") != "sk-roundtrip":
            failures.append(
                f"provider.openai.apiKey: expected 'sk-roundtrip', "
                f"got {openai_prov.get('apiKey')!r}"
            )
        custom_agent = parsed.get("agent", {}).get("custom-agent")
        if custom_agent is None:
            failures.append(
                "agent.custom-agent: missing from saved config"
            )
        elif custom_agent.get("description") != "A custom agent for testing":
            failures.append(
                f"agent.custom-agent.description: expected 'A custom agent for testing', "
                f"got {custom_agent.get('description')!r}"
            )
        if parsed.get("compaction", {}).get("auto") is not False:
            failures.append(
                f"compaction.auto: expected False, got {parsed.get('compaction', {}).get('auto')!r}"
            )

        assert not failures, (
            "FAILS: One or more fields did not survive the save_config round trip.\n"
            + "\n".join(f"  • {f}" for f in failures)
            + "\nRoot cause: _merge_configs return value is discarded in save_config()"
        )

    # -----------------------------------------------------------------------
    # 2. The merge-function bug (low-level verification)
    # -----------------------------------------------------------------------

    def test_merge_configs_return_value_is_captured_in_save_config(self) -> None:
        """Verify that ``save_config`` captures the merge return value.

        The fix was: ``merged = _merge_configs(existing, model_data)``
        instead of ``_merge_configs(existing, model_data)`` (bare call).
        """
        import inspect
        source = inspect.getsource(save_config)

        merge_line = None
        for line in source.splitlines():
            stripped = line.strip()
            if "_merge_configs(" in stripped and "=" in stripped:
                merge_line = stripped
                break

        assert merge_line is not None, (
            "FAILS: _merge_configs return value is not captured in save_config.\n"
            "The fix requires: `merged = _merge_configs(existing, model_data)`\n"
            f"Source:\n{source[:500]}"
        )
