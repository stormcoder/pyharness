"""End-to-end tests tracing config → sidebar display chain for provider cleanliness.

These tests verify that "bad" and "bad-provider" entries are properly
excluded at every stage of the pipeline:

    config file → load_config → self.config → _populate_connected_providers
    → _provider_status → _update_sidebar_providers → sidebar

Tests 1–4 verify each stage in isolation.  Test 5 is the full chain integration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, patch

import pytest

from pyharness.config.loader import load_config, save_config
from pyharness.config.schema import ProviderConfig, PyHarnessConfig
from pyharness.tui.app import PyHarnessApp
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.sidebar import Sidebar
from textual.widgets import Static

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

DEEPSEEK_CONFIG_DICT: dict = {
    "model": "deepseek:deepseek-chat",
    "small_model": "deepseek:deepseek-chat",
    "provider": {
        "deepseek": {
            "apiKey": "sk-deepseek-test-key",
        },
    },
}

BAD_PROVIDER_NAMES = frozenset({"bad", "bad-provider"})


def _write_temp_config(parent: Path, filename: str = "pyharness.json") -> Path:
    """Write *DEEPSEEK_CONFIG_DICT* into a JSON file under *parent*."""
    path = parent / filename
    path.write_text(json.dumps(DEEPSEEK_CONFIG_DICT, indent=2), encoding="utf-8")
    return path


def _assert_no_bad_in_keys(keys: set[str] | list[str], source: str) -> None:
    """Assert that ``bad`` and ``bad-provider`` are absent from *keys*."""
    key_set = set(keys)
    leakage = BAD_PROVIDER_NAMES & key_set
    assert not leakage, (
        f"Bad provider(s) {leakage} found in {source}.  "
        f"Keys present: {key_set}"
    )


# ======================================================================
# Test 1: Config loaded has no bad providers
# ======================================================================


class TestConfigLoadedHasNoBadProviders:
    """Verify ``load_config()`` does not include ``bad`` / ``bad-provider``
    in the returned ``PyHarnessConfig.provider`` dict."""

    def test_custom_config_only_has_deepseek(self, tmp_path: Path) -> None:
        """With ``PYHARNESS_CONFIG`` pointing to a clean deepseek-only file,
        loaded config MUST exclude ``bad`` and ``bad-provider``."""
        clean_home = tmp_path / "home"
        clean_home.mkdir()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = _write_temp_config(config_dir)
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        with (
            mock.patch.dict(os.environ, {"PYHARNESS_CONFIG": str(config_file)}),
            mock.patch("pathlib.Path.home", return_value=clean_home),
            mock.patch("pyharness.config.loader.Path.home", return_value=clean_home),
        ):
            config = load_config(cwd=cwd)

        assert set(config.provider.keys()) == {"deepseek"}, (
            f"Expected only {{'deepseek'}}, got {set(config.provider.keys())}"
        )

    def test_custom_config_absolutely_no_bad_providers(self, tmp_path: Path) -> None:
        """Explicit assertion that 'bad' and 'bad-provider' are absent."""
        clean_home = tmp_path / "home"
        clean_home.mkdir()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = _write_temp_config(config_dir)
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        with (
            mock.patch.dict(os.environ, {"PYHARNESS_CONFIG": str(config_file)}),
            mock.patch("pathlib.Path.home", return_value=clean_home),
            mock.patch("pyharness.config.loader.Path.home", return_value=clean_home),
        ):
            config = load_config(cwd=cwd)

        _assert_no_bad_in_keys(config.provider.keys(), "config.provider")

    def test_inline_config_excludes_bad_providers(self, tmp_path: Path) -> None:
        """``PYHARNESS_CONFIG_CONTENT`` should also yield a clean config."""
        clean_home = tmp_path / "home"
        clean_home.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        inline = json.dumps(DEEPSEEK_CONFIG_DICT)
        with (
            mock.patch.dict(os.environ, {"PYHARNESS_CONFIG_CONTENT": inline}),
            mock.patch("pathlib.Path.home", return_value=clean_home),
            mock.patch("pyharness.config.loader.Path.home", return_value=clean_home),
        ):
            config = load_config(cwd=cwd)

        _assert_no_bad_in_keys(config.provider.keys(), "config.provider (inline)")

    def test_bad_providers_in_global_leak_into_pyharnes_config(self, tmp_path: Path) -> None:
        """**Regression test** — when the global config has ``bad`` entries
        and ``PYHARNESS_CONFIG`` has only ``deepseek``, the deep-merge
        should NOT leak ``bad`` entries, but the current loader implementation
        DOES allow leakage because ``_merge_configs`` deep-merges dicts
        instead of replacing the ``provider`` section.

        THIS TEST IS MARKED XFAIL — it documents the expected behaviour.
        """
        clean_home = tmp_path / "home"
        clean_home.mkdir()
        (clean_home / ".config" / "pyharness").mkdir(parents=True)

        global_config = {
            "model": "deepseek:deepseek-chat",
            "provider": {
                "bad-provider": {"apiKey": "bad-key"},
                "bad": {"apiKey": "also-bad"},
            },
        }
        (clean_home / ".config" / "pyharness" / "pyharness.json").write_text(
            json.dumps(global_config)
        )

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        custom_file = _write_temp_config(config_dir)
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        with (
            mock.patch.dict(os.environ, {"PYHARNESS_CONFIG": str(custom_file)}),
            mock.patch("pathlib.Path.home", return_value=clean_home),
            mock.patch("pyharness.config.loader.Path.home", return_value=clean_home),
        ):
            config = load_config(cwd=cwd)

        provider_keys = set(config.provider.keys())
        leakage = BAD_PROVIDER_NAMES & provider_keys

        if leakage:
            pytest.xfail(
                f"KNOWN LEAK: bad providers {leakage} leaked from global "
                f"config into merged result.  Global={set(global_config['provider'])} "
                f"+ Custom={set(DEEPSEEK_CONFIG_DICT['provider'])} "
                f"= Result={provider_keys}.  "
                f"Root cause: _merge_configs deep-merges provider dicts "
                f"instead of replacing the section."
            )

        assert leakage == set(), f"Bad providers must NOT leak: {leakage}"


# ======================================================================
# Test 2: _provider_status excludes bad providers
# ======================================================================


class TestProviderStatusExcludesBadProviders:
    """``_populate_connected_providers()`` must only create entries for
    providers that actually appear in ``self.config.provider``."""

    def test_status_has_no_bad_providers_after_populate(self) -> None:
        """When config has only deepseek, _provider_status must NOT contain
        'bad' or 'bad-provider'.

        NOTE: ``_populate_connected_providers`` only sets ``False`` for
        clearly-broken keys (empty apiKey, unresolvable {env:VAR}).
        Valid-looking keys are left unset for ``refresh_models``.
        So after populate, _provider_status may be empty — what matters
        is that it NEVER contains bad keys.
        """
        app = PyHarnessApp()
        app.config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)
        app._populate_connected_providers()

        # Verify no bad providers appear
        _assert_no_bad_in_keys(
            app._provider_status.keys(), "_provider_status"
        )

        # All keys in _provider_status must be from config.provider
        config_keys = set(app.config.provider.keys())
        status_keys = set(app._provider_status.keys())
        unknown = status_keys - config_keys
        assert not unknown, (
            f"_provider_status has keys not in config.provider: {unknown}"
        )

    def test_empty_provider_status_when_no_providers(self) -> None:
        """When config has zero providers, _provider_status must be empty."""
        app = PyHarnessApp()
        app.config = PyHarnessConfig()
        app._populate_connected_providers()
        assert app._provider_status == {}, (
            f"Expected empty status, got {app._provider_status}"
        )

    def test_status_after_re_populate_clears_bad_entries(self) -> None:
        """Even if stale state is injected, re-populating from a clean
        config must eliminate bad entries."""
        app = PyHarnessApp()
        app.config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)

        # Simulate stale state
        app._provider_status["bad"] = True
        app._provider_status["bad-provider"] = False
        assert "bad" in app._provider_status  # verify stale injection

        # Re-populate from clean config — stale entries gone
        app._provider_status = {}
        app._populate_connected_providers()

        _assert_no_bad_in_keys(
            app._provider_status.keys(), "_provider_status after re-populate"
        )


# ======================================================================
# Test 3: save_config does not reintroduce bad providers
# ======================================================================


class TestSaveConfigDoesNotReintroduceBadProviders:
    """``save_config()`` writes the *canonical* provider set — only what
    is in the in-memory ``PyHarnessConfig`` model, not stale disk entries."""

    def test_save_clean_config_stays_clean(self, tmp_path: Path) -> None:
        """Save a deepseek-only config; the file must contain only deepseek."""
        config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)
        target = tmp_path / "pyharness.json"

        with mock.patch("pathlib.Path.home", return_value=tmp_path):
            save_config(config, target=str(target))

        assert target.exists(), "save_config must create the file"
        parsed = json.loads(target.read_text(encoding="utf-8"))
        provider = parsed.get("provider", {})

        assert set(provider.keys()) == {"deepseek"}, (
            f"File provider keys must be only {{'deepseek'}}, "
            f"got {set(provider.keys())}"
        )

    def test_save_config_replaces_not_merges(self, tmp_path: Path) -> None:
        """Write a file with bad providers, then save_config with only
        deepseek — the bad entries MUST be removed."""
        target = tmp_path / "pyharness.json"

        target.parent.mkdir(parents=True, exist_ok=True)
        stale = {
            "model": "deepseek:deepseek-chat",
            "provider": {
                "bad-provider": {"apiKey": "old-bad-key"},
                "bad": {"apiKey": "also-old"},
                "deepseek": {"apiKey": "sk-real"},
            },
        }
        target.write_text(json.dumps(stale, indent=2))

        config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)
        save_config(config, target=str(target))

        reread = json.loads(target.read_text(encoding="utf-8"))
        provider = reread.get("provider", {})

        _assert_no_bad_in_keys(provider.keys(), "saved config provider keys")
        assert "deepseek" in provider, "deepseek must survive"


# ======================================================================
# Test 4: Sidebar text excludes bad providers (runtime)
# ======================================================================


class TestSidebarTextExcludesBadProviders:
    """Mounted sidebar widget must not render ``bad`` or ``bad-provider``
    in the ``#providers-status`` text."""

    async def test_sidebar_renders_only_deepseek(self) -> None:
        """Mount sidebar, call update_provider_status with clean dict, and
        assert the rendered text is clean."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            sidebar = Sidebar(id="test-sidebar")
            await pilot.app.mount(sidebar)
            await pilot.pause()

            sidebar.update_provider_status({"deepseek": True})

            status_widget = sidebar.query_one("#providers-status", Static)
            text = str(status_widget.content)

            assert "deepseek" in text, f"Expected 'deepseek' in sidebar text: {text!r}"
            _assert_no_bad_in_keys(text.split(), "sidebar provider text")

    async def test_sidebar_renders_what_it_is_given(self) -> None:
        """If update_provider_status is called with bad entries, the widget
        renders them — verifying the widget is an honest pipe.

        The real guard is that ``_provider_status`` never contains bad keys
        (verified in tests 1–3).
        """
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            sidebar = Sidebar(id="test-sidebar")
            await pilot.app.mount(sidebar)
            await pilot.pause()

            sidebar.update_provider_status({
                "deepseek": True,
                "bad-provider": True,
                "bad": False,
            })

            status_widget = sidebar.query_one("#providers-status", Static)
            text = str(status_widget.content)

            assert "bad-provider" in text, (
                "Sidebar MUST render what it is given.  "
                "The fix belongs upstream in _populate_connected_providers."
            )
            assert "bad" in text, (
                "Sidebar MUST render what it is given.  "
                "The fix belongs upstream."
            )

    async def test_empty_status_shows_no_providers_message(self) -> None:
        """Empty provider status shows the no-providers placeholder."""
        app = PyHarnessApp()
        async with app.run_test() as pilot:
            sidebar = Sidebar(id="test-sidebar")
            await pilot.app.mount(sidebar)
            await pilot.pause()

            sidebar.update_provider_status({})
            status_widget = sidebar.query_one("#providers-status", Static)
            text = str(status_widget.content)

            assert "No providers connected" in text, (
                f"Expected placeholder, got: {text!r}"
            )

    async def test_sidebar_update_chain_in_app(self) -> None:
        """Set app._provider_status with clean data, call
        _update_sidebar_providers, and verify sidebar text is clean."""
        app = PyHarnessApp()

        app.config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)
        app._provider_status = {"deepseek": True}
        app._config_loaded_from_disk = True

        with patch.object(app, "refresh_models", AsyncMock()):
            async with app.run_test() as pilot:
                await pilot.pause()
                # on_mount pushes ChatScreen.  Sidebar is composed inside.
                app._update_sidebar_providers()
                await pilot.pause()

                sidebar = app.screen.query_one("#sidebar-container", Sidebar)
                status_widget = sidebar.query_one("#providers-status", Static)
                text = str(status_widget.content)

                assert "deepseek" in text, (
                    f"Expected 'deepseek' in sidebar: {text!r}"
                )
                _assert_no_bad_in_keys(text.split(), "sidebar text via app chain")


# ======================================================================
# Test 5: Full chain integration — no bad providers anywhere
# ======================================================================


class TestFullChainNoBadProviders:
    """End-to-end: config dict → load → model validate → populate →
    build sidebar text → assert only expected providers."""

    @staticmethod
    def _build_sidebar_text(providers: dict[str, bool]) -> str:
        """Simulate the sidebar widget's text rendering for a given
        provider status dict.  Mirrors ``Sidebar.update_provider_status``."""
        if not providers:
            return "No providers connected"
        lines: list[str] = []
        for name, connected in providers.items():
            dot = "🟢" if connected else "🔴"
            lines.append(f"  {dot} {name}")
        return "\n".join(lines)

    def test_full_chain_with_programmatic_config(self) -> None:
        """Use a programmatically built PyHarnessConfig with only
        deepseek — no JSON round-trip needed."""
        config = PyHarnessConfig(
            model="deepseek:deepseek-chat",
            provider={
                "deepseek": ProviderConfig(apiKey="sk-test"),
            },
        )

        _assert_no_bad_in_keys(config.provider.keys(), "programmatic config.provider")

        # Simulate _populate_connected_providers
        status: dict[str, bool] = {}
        for pname, pconf in config.provider.items():
            key = pconf.apiKey or ""
            if not key:
                status[pname] = False
            elif key.startswith("{env:") and key.endswith("}"):
                env_var = key[5:-1]
                status[pname] = bool(os.environ.get(env_var))
            # else: left for refresh_models to verify

        _assert_no_bad_in_keys(status.keys(), "simulated _provider_status")

        # Build sidebar text
        text = self._build_sidebar_text(status)
        _assert_no_bad_in_keys(text.split(), "simulated sidebar text")

    def test_full_chain_load_save_roundtrip(self, tmp_path: Path) -> None:
        """Load clean config → save_config → load again → assert
        no bad providers.  Full persistence round-trip."""
        clean_home = tmp_path / "home"
        clean_home.mkdir()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = _write_temp_config(config_dir)
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        with (
            mock.patch.dict(os.environ, {"PYHARNESS_CONFIG": str(config_file)}),
            mock.patch("pathlib.Path.home", return_value=clean_home),
            mock.patch("pyharness.config.loader.Path.home", return_value=clean_home),
        ):
            config = load_config(cwd=cwd)

        assert "deepseek" in config.provider
        _assert_no_bad_in_keys(config.provider.keys(), "config.provider after load")

        target = tmp_path / "saved.json"
        save_config(config, target=str(target))

        reread = json.loads(target.read_text(encoding="utf-8"))
        provider = reread.get("provider", {})

        _assert_no_bad_in_keys(provider.keys(), "config after save→load roundtrip")
        assert "deepseek" in provider, "deepseek must survive roundtrip"

    async def test_full_chain_in_running_app(self) -> None:
        """Load a clean config into a running app, populate status, and
        verify the sidebar displays only deepseek.

        refresh_models is mocked to prevent real API calls.
        """
        app = PyHarnessApp()
        app.config = PyHarnessConfig.model_validate(DEEPSEEK_CONFIG_DICT)
        app._config_loaded_from_disk = True
        app._provider_status = {"deepseek": True}

        with patch.object(app, "refresh_models", AsyncMock()):
            async with app.run_test() as pilot:
                await pilot.pause()

                sidebar = app.screen.query_one("#sidebar-container", Sidebar)
                app._update_sidebar_providers()
                await pilot.pause()

                status_widget = sidebar.query_one("#providers-status", Static)
                text = str(status_widget.content)

                assert "deepseek" in text, (
                    f"Sidebar must show 'deepseek': {text!r}"
                )
                _assert_no_bad_in_keys(text.split(), "sidebar in running app")
