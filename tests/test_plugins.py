"""Tests for the Phase 4 plugin system."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pyharness.plugins import PluginLoader


# ---------------------------------------------------------------------------
# PluginLoader – basic lifecycle
# ---------------------------------------------------------------------------


class TestPluginLoaderBasic:
    """Test core PluginLoader behaviour."""

    def test_initial_state_empty(self):
        loader = PluginLoader()
        assert loader.get_plugins() == []

    def test_discover_returns_list(self):
        loader = PluginLoader()
        result = loader.discover()
        assert isinstance(result, list)

    def test_get_plugins_returns_copy(self):
        loader = PluginLoader()
        loader._plugins = ["alpha"]
        copy = loader.get_plugins()
        assert copy == ["alpha"]
        copy.append("beta")
        assert loader.get_plugins() == ["alpha"]


# ---------------------------------------------------------------------------
# Hook registration
# ---------------------------------------------------------------------------


class TestHooks:
    """Test hook registration and retrieval."""

    def test_register_and_get_hooks(self):
        loader = PluginLoader()

        def handler_a():
            pass

        def handler_b():
            pass

        loader.register_hook("before_tool", handler_a)
        loader.register_hook("before_tool", handler_b)
        loader.register_hook("after_tool", handler_a)

        assert loader.get_hooks("before_tool") == [handler_a, handler_b]
        assert loader.get_hooks("after_tool") == [handler_a]
        assert loader.get_hooks("nonexistent") == []

    def test_get_hooks_unknown_event(self):
        loader = PluginLoader()
        assert loader.get_hooks("unknown") == []


# ---------------------------------------------------------------------------
# Entry-point discovery
# ---------------------------------------------------------------------------


class TestEntryPointPlugins:
    """Test discovery via pip entry points."""

    def test_loads_entry_point_plugins(self):
        class DummyPlugin:
            pass

        dummy_entry = MagicMock()
        dummy_entry.load.return_value = DummyPlugin

        with patch(
            "pyharness.plugins.loader.entry_points",
            return_value=[dummy_entry],
        ):
            loader = PluginLoader()
            plugins = loader._load_entry_point_plugins()
            assert len(plugins) == 1
            assert isinstance(plugins[0], DummyPlugin)

    def test_handles_entry_point_load_failure(self):
        bad_entry = MagicMock()
        bad_entry.load.side_effect = ImportError("nope")

        with patch(
            "pyharness.plugins.loader.entry_points",
            return_value=[bad_entry],
        ):
            loader = PluginLoader()
            plugins = loader._load_entry_point_plugins()
            assert plugins == []

    def test_entry_points_attribute_error_handled(self):
        with patch(
            "pyharness.plugins.loader.entry_points",
            side_effect=AttributeError,
        ):
            loader = PluginLoader()
            assert loader._load_entry_point_plugins() == []


# ---------------------------------------------------------------------------
# Local file discovery
# ---------------------------------------------------------------------------


class TestLocalPlugins:
    """Test discovery from ``.pyharness/plugins/`` directories."""

    def _write_plugin(
        self, dir_path: Path, name: str, source: str
    ) -> Path:
        dir_path.mkdir(parents=True, exist_ok=True)
        file = dir_path / f"{name}.py"
        file.write_text(textwrap.dedent(source))
        return file

    def test_loads_local_plugin_with_class(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "myplugin",
            """
            class MyPlugin:
                pass
            """,
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert len(plugins) == 1
        assert type(plugins[0]).__name__ == "MyPlugin"

    def test_loads_local_plugin_with_register_func(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "regplugin",
            """
            def register():
                return "registered"
            """,
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert len(plugins) == 1
        assert callable(plugins[0])

    def test_skips_private_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "_internal",
            """
            class InternalPlugin:
                pass
            """,
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert plugins == []

    def test_handles_syntax_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "broken",
            "this is not valid python !!!!",
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert plugins == []

    def test_handles_instantiation_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "badinit",
            """
            class BadInitPlugin:
                def __init__(self):
                    raise RuntimeError("boom")
            """,
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert plugins == []

    def test_skips_missing_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # no .pyharness/plugins directory created
        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        assert plugins == []

    def test_finds_multiple_plugins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "alpha",
            "class AlphaPlugin: pass",
        )
        self._write_plugin(
            tmp_path / ".pyharness" / "plugins",
            "beta",
            "class BetaPlugin: pass",
        )

        loader = PluginLoader()
        plugins = loader._load_local_plugins()
        names = {type(p).__name__ for p in plugins}
        assert names >= {"AlphaPlugin", "BetaPlugin"}


# ---------------------------------------------------------------------------
# discover() combined
# ---------------------------------------------------------------------------


class TestDiscoverCombined:
    """Test the full ``discover()`` pipeline."""

    def test_discover_with_local_and_entry_points(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        # Write a local plugin
        plugins_dir = tmp_path / ".pyharness" / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "local.py").write_text(
            "class LocalPlugin: pass"
        )

        # Mock entry points
        class EntryPlugin:
            pass

        mock_ep = MagicMock()
        mock_ep.load.return_value = EntryPlugin

        with patch(
            "pyharness.plugins.loader.entry_points",
            return_value=[mock_ep],
        ):
            loader = PluginLoader()
            plugins = loader.discover()
            assert len(plugins) == 2

        assert loader.get_plugins() == plugins


# ---------------------------------------------------------------------------
# Example plugin behavioural tests
# ---------------------------------------------------------------------------


class TestNotificationPlugin:
    """Verify the notification example plugin."""

    async def test_on_session_idle_calls_notify_send(self):
        from pyharness.plugins.notification import NotificationPlugin

        p = NotificationPlugin()
        session = {"title": "My Session"}

        with patch("subprocess.run") as mock_run:
            await p.on_session_idle(None, session)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[:2] == ["notify-send", "pyharness"]
            assert "My Session" in " ".join(args)

    async def test_on_session_error_calls_critical(self):
        from pyharness.plugins.notification import NotificationPlugin

        p = NotificationPlugin()
        with patch("subprocess.run") as mock_run:
            await p.on_session_error(None, {})
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "-u" in args
            assert "critical" in args

    async def test_subprocess_failure_is_silent(self):
        from pyharness.plugins.notification import NotificationPlugin

        p = NotificationPlugin()
        with patch("subprocess.run", side_effect=OSError):
            await p.on_session_idle(None, {})  # no exception


class TestEnvProtectionPlugin:
    """Verify the env-protection example plugin."""

    async def test_blocks_read_of_env_file(self):
        from pyharness.plugins.env_protection import EnvProtectionPlugin

        p = EnvProtectionPlugin()
        with pytest.raises(RuntimeError, match=".env files"):
            await p.on_tool_execute_before(
                None, "read", {"path": ".env"}
            )

    async def test_blocks_read_of_nested_env_file(self):
        from pyharness.plugins.env_protection import EnvProtectionPlugin

        p = EnvProtectionPlugin()
        with pytest.raises(RuntimeError, match=".env files"):
            await p.on_tool_execute_before(
                None, "read", {"path": "some/deep/.env"}
            )

    async def test_blocks_read_case_insensitive(self):
        from pyharness.plugins.env_protection import EnvProtectionPlugin

        p = EnvProtectionPlugin()
        with pytest.raises(RuntimeError, match=".env files"):
            await p.on_tool_execute_before(
                None, "read", {"path": ".ENV"}
            )

    async def test_allows_read_of_other_files(self):
        from pyharness.plugins.env_protection import EnvProtectionPlugin

        p = EnvProtectionPlugin()
        await p.on_tool_execute_before(None, "read", {"path": "src/main.py"})
        await p.on_tool_execute_before(None, "read", {"path": "config.yaml"})

    async def test_ignores_other_tools(self):
        from pyharness.plugins.env_protection import EnvProtectionPlugin

        p = EnvProtectionPlugin()
        # Should not raise — tool name is not "read"
        await p.on_tool_execute_before(
            None, "write", {"path": ".env"}
        )
