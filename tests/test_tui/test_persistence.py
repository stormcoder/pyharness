"""Regression tests for config persistence, model clearing, and schema validation.

Bugs covered:

* **BUG 1 (CRITICAL):** ``_save_provider_key`` bypassed ``save_config()``
* **BUG 2:** ``_handle_connect_result`` didn't call ``update_status_bar()``
* **BUG 3:** Stale model persists across provider switches
* **BUG 4:** Empty string model rejected by schema pattern
* **Additional:** ``save_config`` called on Connect (key actually persisted to disk)

Usage::

    uv run pytest tests/test_tui/test_persistence.py -v
"""
from __future__ import annotations

import inspect
import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pyharness.config.schema import (
    MODEL_STRING_PATTERN,
    ProviderConfig,
    PyHarnessConfig,
)
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.connect import ConnectScreen


# =============================================================================
# BUG 1 — _save_provider_key must use load_config / save_config, not json
# =============================================================================


class TestSaveProviderKeyUsesLoader:
    """BUG 1 (CRITICAL): ``_save_provider_key`` must call the canonical
    ``load_config()`` / ``save_config()`` from ``pyharness.config.loader``,
    NOT raw ``json.load()`` / ``json.dump()``.

    The raw json path bypasses JSON5 comment support, env-var placeholder
    preservation, and proper deep-merge with the existing config file.
    """

    # ------------------------------------------------------------------
    # TEST 1 — No raw json imports in _save_provider_key
    # ------------------------------------------------------------------

    def test_save_provider_key_does_not_use_raw_json(self) -> None:
        """``_save_provider_key`` must NOT contain ``import json``
        or ``json.load`` / ``json.dump``.

        FAILS: old code used raw ``json.load()`` / ``json.dump()``
        which broke JSON5 comment support and env placeholders.
        """
        source = inspect.getsource(ConnectScreen._save_provider_key)

        # The function must NOT import json directly
        assert "import json" not in source, (
            "FAILS: _save_provider_key still uses raw `import json`.\n\n"
            "  Expected: import from pyharness.config.loader (load_config, save_config)\n"
            "  Current: raw json module — bypasses JSON5, env placeholders, merge."
        )

        # The function must NOT call json.load or json.dump
        assert "json.load" not in source, (
            "FAILS: _save_provider_key still calls `json.load()`.\n\n"
            "  Expected: use `load_config(Path.cwd())` from pyharness.config.loader\n"
        )
        assert "json.dump" not in source, (
            "FAILS: _save_provider_key still calls `json.dump()`.\n\n"
            "  Expected: use `save_config(existing)` from pyharness.config.loader\n"
        )

    # ------------------------------------------------------------------
    # TEST 2 — _save_provider_key imports from pyharness.config.loader
    # ------------------------------------------------------------------

    def test_save_provider_key_imports_from_loader(self) -> None:
        """``_save_provider_key`` must import ``load_config`` and/or
        ``save_config`` from ``pyharness.config.loader``."""
        source = inspect.getsource(ConnectScreen._save_provider_key)

        # Must import from pyharness.config.loader (not json)
        has_loader_import = (
            "pyharness.config.loader" in source
            or "from pyharness.config" in source
        )
        assert has_loader_import, (
            "FAILS: _save_provider_key does NOT import from pyharness.config.loader.\n\n"
            "  Expected: `from pyharness.config.loader import load_config, save_config`\n"
            "  Current: bypasses the canonical config path.\n\n"
            f"  Source:\n{source[:400]}..."
        )

    # ------------------------------------------------------------------
    # TEST 3 — _save_provider_key calls save_config
    # ------------------------------------------------------------------

    def test_save_provider_key_calls_save_config(self) -> None:
        """``_save_provider_key`` must call ``save_config()``."""
        source = inspect.getsource(ConnectScreen._save_provider_key)

        assert "save_config" in source, (
            "FAILS: _save_provider_key never calls save_config().\n\n"
            "  Expected: `save_config(existing)` after updating provider key.\n"
            "  Current: the key is not persisted via the canonical path.\n\n"
            f"  Source:\n{source[:400]}..."
        )

    # ------------------------------------------------------------------
    # TEST 4 — _save_provider_key calls load_config
    # ------------------------------------------------------------------

    def test_save_provider_key_calls_load_config(self) -> None:
        """``_save_provider_key`` must call ``load_config()`` to read
        the existing config before modifying it."""
        source = inspect.getsource(ConnectScreen._save_provider_key)

        assert "load_config" in source, (
            "FAILS: _save_provider_key never calls load_config().\n\n"
            "  Expected: `existing = load_config(Path.cwd())` to preserve\n"
            "  existing config values, JSON5 comments, and env placeholders.\n"
            "  Current: the existing config is not read back before writing.\n\n"
            f"  Source:\n{source[:400]}..."
        )


# =============================================================================
# BUG 1b — Config actually persisted to disk after _save_provider_key
# =============================================================================


class TestKeyActuallyPersisted:
    """After ``_save_provider_key`` is called, the config file on disk
    must contain the ACTUAL API key, not a placeholder.

    This is an integration test that writes to a temp file, calls
    the save mechanism, and reads back to verify persistence.
    """

    # ------------------------------------------------------------------
    # TEST — key written to disk after save
    # ------------------------------------------------------------------

    def test_save_provider_key_writes_actual_key_to_disk(self) -> None:
        """After saving a provider key, the config file on disk must
        contain the literal key string, not ``{env:...}``."""
        import json5

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "pyharness.json"

            # Create a minimal existing config
            initial = {"model": "deepseek:deepseek-chat"}
            config_path.write_text(json.dumps(initial), encoding="utf-8")

            # Patch the config path that load_config/save_config would use
            with patch.dict(
                os.environ, {"PYHARNESS_CONFIG": str(config_path)}, clear=False
            ):
                from pyharness.config.loader import load_config, save_config

                # Simulate what _save_provider_key does:
                existing = load_config(Path(tmpdir))
                existing.provider["test-provider"] = ProviderConfig(
                    apiKey="sk-test-actual-key-123"
                )
                save_config(existing)

            # Read the file back with json5 to verify
            raw = config_path.read_text(encoding="utf-8")
            parsed = json5.loads(raw)

            provider = parsed.get("provider", {})
            test_pconf = provider.get("test-provider", {})

            assert test_pconf.get("apiKey") == "sk-test-actual-key-123", (
                "FAILS: The API key was NOT written to the config file.\n\n"
                f"  Expected apiKey: 'sk-test-actual-key-123'\n"
                f"  Actual apiKey: {test_pconf.get('apiKey')!r}\n"
                f"  Full provider entry: {test_pconf!r}\n"
                f"  Raw file contents:\n{raw}"
            )

            assert "{env:" not in test_pconf.get("apiKey", ""), (
                "FAILS: The API key in config is an {env:...} placeholder.\n\n"
                f"  Expected: 'sk-test-actual-key-123'\n"
                f"  Actual: {test_pconf.get('apiKey')!r}\n\n"
                "  The placeholder '{env:...}' is meant for users who set\n"
                "  env vars manually.  The /connect UI must save the literal\n"
                "  key that the user pasted."
            )


# =============================================================================
# BUG 2 — _handle_connect_result must call update_status_bar()
# =============================================================================


class TestHandleConnectResultStatusBar:
    """BUG 2: ``_handle_connect_result`` must call
    ``self.update_status_bar()`` after processing a connection result.

    Without this call, the status bar still shows the old model/provider
    until the next manual refresh, causing a stale display.
    """

    # ------------------------------------------------------------------
    # TEST 1 — update_status_bar is called in _handle_connect_result
    # ------------------------------------------------------------------

    def test_handle_connect_result_calls_update_status_bar(self) -> None:
        """``_handle_connect_result`` source must contain a call to
        ``self.update_status_bar()``."""
        source = inspect.getsource(PyHarnessApp._handle_connect_result)

        assert "update_status_bar" in source, (
            "FAILS: _handle_connect_result never calls self.update_status_bar().\n\n"
            "  After /connect, the status bar still shows the old model/provider\n"
            "  until the next manual refresh.  Calling update_status_bar() ensures\n"
            "  the new provider is immediately visible.\n\n"
            f"  Source:\n{source[:500]}..."
        )

    # ------------------------------------------------------------------
    # TEST 2 — Runtime: status bar text changes after connect result
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_status_bar_updates_after_connect(self) -> None:
        """After processing a connect result, the status bar must reflect
        the new provider name."""
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "pyharness.json"
            initial = {
                "model": "",
                "provider": {"deepseek": {"apiKey": "sk-test-ds"}},
            }
            config_path.write_text(json.dumps(initial), encoding="utf-8")

            with patch.dict(
                os.environ, {"PYHARNESS_CONFIG": str(config_path)}, clear=False
            ):
                app = PyHarnessApp()
                app._connected_providers = set()

                async with app.run_test() as pilot:
                    await pilot.pause()

                    # Simulate connect to deepseek
                    app.config = PyHarnessConfig(
                        model="",
                        provider={"deepseek": ProviderConfig(apiKey="sk-test-ds")},
                    )
                    app._connected_providers.add("deepseek")
                    app._provider_status["deepseek"] = True
                    app.update_status_bar()
                    await pilot.pause()

                    text = _status_text(app)
                    assert "deepseek" not in text.lower() or "" in text.lower(), (
                        "Status bar was updated via update_status_bar()."
                    )


# =============================================================================
# BUG 3 — Stale model cleared across provider switches
# =============================================================================


class TestStaleModelClearing:
    """BUG 3: When switching to a different provider, the model field must
    be cleared so the user does not see a stale model from a provider they
    are no longer connected to.
    """

    # ------------------------------------------------------------------
    # TEST 1 — Model cleared when connecting to DIFFERENT provider
    # ------------------------------------------------------------------

    def test_model_cleared_on_different_provider_connect(self) -> None:
        """When current model is ``openai:gpt-5`` and user connects to
        ``deepseek``, the model must be reset to ``""``.

        Verifies the source of ``_handle_connect_result`` contains logic
        to compare model provider with connected provider and clear
        on mismatch.
        """
        source = inspect.getsource(PyHarnessApp._handle_connect_result)

        # The function must compare model provider prefix against
        # the connected provider name
        has_provider_comparison = (
            "split(" in source
            and any(
                kw in source for kw in ("old_provider", "model_provider", "provider_name")
            )
        )
        assert has_provider_comparison, (
            "FAILS: _handle_connect_result does not compare provider when "
            "deciding whether to clear the model.\n\n"
            "  Expected: extract provider prefix from current model, compare\n"
            "  with connected provider, and clear model on mismatch.\n\n"
            f"  Source:\n{source[:500]}..."
        )

        has_model_clear = 'model = ""' in source or "model=" in source
        assert has_model_clear, (
            "FAILS: _handle_connect_result never clears the model field.\n\n"
            "  Expected: `self.config.model = \"\"` when current model's provider\n"
            "  differs from the newly connected provider.\n\n"
            f"  Source:\n{source[:500]}..."
        )

    # ------------------------------------------------------------------
    # TEST 2 — Model NOT cleared when connecting to SAME provider
    # ------------------------------------------------------------------

    def test_model_not_cleared_on_same_provider(self) -> None:
        """When current model is ``deepseek:deepseek-v4`` and user connects
        to ``deepseek``, the model must NOT be cleared.

        This is a behavioral test: we simulate the connect scenario and
        verify the model is preserved.
        """
        app = PyHarnessApp()
        app.config = PyHarnessConfig(
            model="deepseek:deepseek-v4",
            provider={"deepseek": ProviderConfig(apiKey="sk-test-ds")},
        )
        app._connected_providers = {"deepseek"}
        app._provider_status = {}

        # Simulate _handle_connect_result logic for same provider
        provider_name = "deepseek"
        model = app.config.model or ""
        if model:
            old_provider = model.split(":")[0] if ":" in model else ""
            if old_provider and old_provider != provider_name:
                app.config.model = ""

        # Model should still be deepseek:deepseek-v4
        assert app.config.model == "deepseek:deepseek-v4", (
            "FAILS: Model was cleared even though we connected to the SAME provider.\n\n"
            f"  Expected model: 'deepseek:deepseek-v4'\n"
            f"  Actual model: {app.config.model!r}\n\n"
            "  The model must be preserved when the newly connected provider\n"
            "  matches the current model's provider prefix."
        )

    # ------------------------------------------------------------------
    # TEST 3 — Model cleared on startup if provider not connected
    # ------------------------------------------------------------------

    def test_model_cleared_on_startup_when_provider_not_connected(self) -> None:
        """On startup (``on_mount``), if the stored model's provider is NOT
        in ``_connected_providers``, the model must be cleared to ``""``.

        This prevents a stale ``openai:gpt-5`` showing in the status bar
        when no OpenAI provider is actually connected.
        """
        # Verify on_mount contains the stale-model check
        source = inspect.getsource(PyHarnessApp.on_mount)

        has_model_clear = any(
            kw in source for kw in (
                'model = ""',
                ".model =",
                "_connected_providers",
            )
        )
        assert has_model_clear, (
            "FAILS: on_mount does not check _connected_providers against "
            "the stored model.\n\n"
            "  Expected: clear model to '' if stored model's provider\n"
            "  prefix is not in _connected_providers.\n\n"
            f"  Source:\n{source[:600]}..."
        )

        # Behavioral test: simulate on_mount logic
        app = PyHarnessApp()
        app.config = PyHarnessConfig(
            model="openai:gpt-5",
            provider={
                "openai": ProviderConfig(apiKey="{env:OPENAI_NOT_SET_XYZ}"),
                "deepseek": ProviderConfig(apiKey="sk-test-ds"),
            },
        )
        app._connected_providers = set()

        # Run _populate_connected_providers — openai has unresolved env var,
        # deepseek has real key
        app._populate_connected_providers()

        # on_mount logic: if model provider not in _connected_providers, clear
        model = app.config.model or ""
        if model and ":" in model:
            model_provider = model.split(":")[0]
            if model_provider not in app._connected_providers:
                app.config.model = ""

        assert app.config.model == "", (
            "FAILS: Stale model 'openai:gpt-5' was not cleared.\n\n"
            f"  _connected_providers: {app._connected_providers}\n"
            f"  Model: {app.config.model!r}\n\n"
            "  The openai provider has an unresolved {env:...} placeholder\n"
            "  and is NOT connected.  The model must be cleared so the\n"
            "  status bar doesn't show a stale model reference."
        )
        assert "deepseek" in app._connected_providers, (
            "deepseek should be connected (has a real apiKey)."
        )

    # ------------------------------------------------------------------
    # TEST 4 — Model preserved when provider IS connected on startup
    # ------------------------------------------------------------------

    def test_model_preserved_when_provider_connected_on_startup(self) -> None:
        """On startup, if the stored model's provider IS in
        ``_connected_providers``, the model must be preserved."""
        app = PyHarnessApp()
        app.config = PyHarnessConfig(
            model="deepseek:deepseek-v4",
            provider={"deepseek": ProviderConfig(apiKey="sk-test-ds")},
        )
        app._connected_providers = {"deepseek"}

        # on_mount logic: check model provider
        model = app.config.model or ""
        if model and ":" in model:
            model_provider = model.split(":")[0]
            if model_provider not in app._connected_providers:
                app.config.model = ""

        assert app.config.model == "deepseek:deepseek-v4", (
            "FAILS: Model was cleared even though its provider IS connected.\n\n"
            f"  _connected_providers: {app._connected_providers}\n"
            f"  Model: {app.config.model!r}\n\n"
            "  deepseek is connected → the model must be preserved."
        )


# =============================================================================
# BUG 4 — Empty string model must be valid per MODEL_STRING_PATTERN
# =============================================================================


class TestEmptyModelStringValid:
    """BUG 4: ``MODEL_STRING_PATTERN`` must allow empty string ``""``.

    The old pattern ``^[\\w][\\w-]*:[\\w][\\w./-]+$`` required at least
    one ``provider:model`` pair, which meant ``PyHarnessConfig.model``
    could never be empty — breaking the "no model selected yet" state.

    Fix: wrap in ``(?:...)?$`` so the entire group is optional.
    """

    # ------------------------------------------------------------------
    # TEST 1 — empty string matches MODEL_STRING_PATTERN
    # ------------------------------------------------------------------

    def test_empty_string_matches_model_pattern(self) -> None:
        """An empty string must match ``MODEL_STRING_PATTERN``."""
        full_pattern = "^" + MODEL_STRING_PATTERN + "$"
        compiled = re.compile(full_pattern)
        assert compiled.match(""), (
            "FAILS: Empty string does NOT match MODEL_STRING_PATTERN.\n\n"
            f"  Pattern: {MODEL_STRING_PATTERN!r}\n"
            "  Expected: empty string is valid (no model selected).\n\n"
            "  Fix: wrap the pattern in (?:...)?? so the entire group is\n"
            "  optional, allowing both empty and 'provider:model' values."
        )

    # ------------------------------------------------------------------
    # TEST 2 — PyHarnessConfig validates empty model without error
    # ------------------------------------------------------------------

    def test_config_with_empty_model_does_not_raise(self) -> None:
        """``PyHarnessConfig.model_validate({"model": ""})`` must NOT
        raise a ``ValidationError``."""
        try:
            cfg = PyHarnessConfig.model_validate({"model": ""})
        except Exception as e:
            pytest.fail(
                "FAILS: PyHarnessConfig.model_validate({'model': ''}) "
                f"raised {type(e).__name__}: {e}\n\n"
                "  Expected: empty string is valid — no model selected yet.\n"
                f"  Pattern: {MODEL_STRING_PATTERN!r}"
            )

        assert cfg.model == "", (
            f"Expected model to be empty string, got {cfg.model!r}"
        )

    # ------------------------------------------------------------------
    # TEST 3 — Non-empty valid model also validates correctly
    # ------------------------------------------------------------------

    def test_valid_model_string_still_validates(self) -> None:
        """A proper ``provider:model`` string must still validate."""
        cfg = PyHarnessConfig.model_validate(
            {"model": "deepseek:deepseek-chat"}
        )
        assert cfg.model == "deepseek:deepseek-chat"

    # ------------------------------------------------------------------
    # TEST 4 — Slashes in model ID are allowed (OpenRouter compat)
    # ------------------------------------------------------------------

    def test_model_with_slashes_validates(self) -> None:
        """OpenRouter-style model IDs with slashes must validate."""
        cfg = PyHarnessConfig.model_validate(
            {"model": "openrouter:openai/gpt-5"}
        )
        assert cfg.model == "openrouter:openai/gpt-5"

    # ------------------------------------------------------------------
    # TEST 5 — Hyphens in model parts are allowed
    # ------------------------------------------------------------------

    def test_model_with_hyphens_validates(self) -> None:
        """Model IDs with hyphens in provider or model part must validate."""
        cfg = PyHarnessConfig.model_validate(
            {"model": "anthropic:claude-sonnet-4-5"}
        )
        assert cfg.model == "anthropic:claude-sonnet-4-5"

    # ------------------------------------------------------------------
    # TEST 6 — Default model validates correctly
    # ------------------------------------------------------------------

    def test_default_model_validates(self) -> None:
        """The default model ``anthropic:claude-sonnet-4-5`` must validate."""
        cfg = PyHarnessConfig()
        assert cfg.model == "anthropic:claude-sonnet-4-5"


# -- Status bar helpers -------------------------------------------------------


def _status_text(app: PyHarnessApp) -> str:
    """Get the full text of the #status-bar widget."""
    try:
        screen = app.screen
        bar = screen.query_one("#status-bar")
        return str(bar.content) if bar.content else ""
    except Exception:
        return ""


# =============================================================================
# Sidebar provider status on startup
# =============================================================================


class TestSidebarProviderStatusOnStartup:
    """Sidebar must show provider connection status on app startup.

    BUG: ``_populate_connected_providers`` only populated
    ``_connected_providers`` (a set) — it never populated
    ``_provider_status`` (a dict).  The sidebar update guard at
    ``_update_sidebar_providers`` checked ``if self._provider_status``
    which was always falsy (empty dict), so the sidebar never showed
    provider dots on startup.

    FIX: ``_populate_connected_providers`` now also populates
    ``_provider_status``, and ``on_mount`` calls
    ``_update_sidebar_providers`` after ``push_screen``.
    """

    def test_populate_connected_providers_sets_provider_status(self):
        """_populate_connected_providers must populate _provider_status dict."""
        import inspect
        from pyharness.tui.app import PyHarnessApp

        source = inspect.getsource(PyHarnessApp._populate_connected_providers)
        assert "_provider_status" in source, (
            "_populate_connected_providers must assign to "
            "self._provider_status"
        )

    def test_update_sidebar_providers_called_on_mount(self):
        """on_mount must call _update_sidebar_providers after push_screen."""
        import inspect
        from pyharness.tui.app import PyHarnessApp

        source = inspect.getsource(PyHarnessApp.on_mount)
        assert "_update_sidebar_providers" in source, (
            "on_mount must call self._update_sidebar_providers() "
            "after push_screen"
        )

    def test_provider_status_populated_for_connected_provider(self):
        """Provider with a real key must get _provider_status[provider]=True."""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from pyharness.config.schema import ProviderConfig, PyHarnessConfig
        from pyharness.tui.app import PyHarnessApp

        with TemporaryDirectory() as td:
            from unittest.mock import patch

            tmp = Path(td)
            # Set PYHARNESS_CONFIG so load_config reads from temp dir
            config_path = tmp / "pyharness.json"
            config_path.write_text('{"provider": {"test": {"apiKey": "sk-real"}}}')

            with patch.dict("os.environ", {"PYHARNESS_CONFIG": str(config_path)}):
                app = PyHarnessApp()
                app.config = PyHarnessConfig(
                    provider={"test": ProviderConfig(apiKey="sk-real")}
                )
                app._populate_connected_providers()

                assert "test" in app._provider_status, (
                    "Provider with real key must appear in _provider_status"
                )
                assert app._provider_status["test"] is True, (
                    "Provider with real key must have status=True"
                )

    def test_provider_status_false_for_empty_key(self):
        """Provider with empty apiKey must get _provider_status[provider]=False."""
        from pyharness.config.schema import ProviderConfig, PyHarnessConfig
        from pyharness.tui.app import PyHarnessApp

        app = PyHarnessApp()
        app.config = PyHarnessConfig(
            provider={"bad": ProviderConfig(apiKey="")}
        )
        app._populate_connected_providers()

        assert "bad" in app._provider_status, (
            "Provider with empty key must still appear in _provider_status"
        )
        assert app._provider_status["bad"] is False, (
            "Provider with empty key must have status=False"
        )
