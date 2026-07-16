"""Plugin discovery and loading.

Discovers plugins from local directories (``.pyharness/plugins/``,
``~/.config/pyharness/plugins/``) and from packages registered via
``pyproject.toml`` entry points under the ``pyharness`` group.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Protocol

if sys.version_info >= (3, 10):
    from importlib.metadata import entry_points
else:
    from importlib_metadata import entry_points


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class PluginLike(Protocol):
    """Structural interface for plugin objects."""

    async def on_session_idle(self, ctx: Any, session: dict) -> None: ...
    async def on_session_error(self, ctx: Any, session: dict) -> None: ...
    async def on_tool_execute_before(
        self, ctx: Any, tool_name: str, args: dict
    ) -> None: ...


# ---------------------------------------------------------------------------
# PluginLoader
# ---------------------------------------------------------------------------


class PluginLoader:
    """Discovers and loads plugins from local directories and pip entry points.

    Plugins are Python modules or packages that expose either a **class**
    whose name ends with ``Plugin`` or a top-level ``register`` callable.
    """

    def __init__(self) -> None:
        self._plugins: list[Any] = []
        self._hooks: dict[str, list[Callable[..., Any]]] = {}

    # -- Discovery -----------------------------------------------------------

    def discover(self) -> list[Any]:
        """Discover plugins from all sources.

        Returns:
            Combined list of discovered plugin instances.
        """
        plugins: list[Any] = []
        plugins.extend(self._load_local_plugins())
        plugins.extend(self._load_entry_point_plugins())
        self._plugins = plugins
        return plugins

    def _load_local_plugins(self) -> list[Any]:
        """Load plugins from ``.pyharness/plugins/``
        and ``~/.config/pyharness/plugins/``."""
        plugins: list[Any] = []
        search_dirs = [
            Path.home() / ".config" / "pyharness" / "plugins",
            Path.cwd() / ".pyharness" / "plugins",
        ]
        for d in search_dirs:
            if not d.exists():
                continue
            for py_file in sorted(d.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                instance = self._load_from_file(py_file)
                if instance is not None:
                    plugins.append(instance)
        return plugins

    def _load_entry_point_plugins(self) -> list[Any]:
        """Load plugins registered via ``project.entry-points.pyharness``."""
        plugins: list[Any] = []
        try:
            for ep in entry_points(group="pyharness"):
                try:
                    factory = ep.load()
                    plugins.append(factory())
                except Exception:
                    continue
        except Exception:
            pass
        return plugins

    # -- File loading --------------------------------------------------------

    def _load_from_file(self, path: Path) -> Any | None:
        """Attempt to load a plugin instance from *path*.

        Returns ``None`` on failure so that a single broken file doesn't
        block the loader.
        """
        module_name = f"pyharness_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:
            return None

        # 1. Find a class whose name ends with "Plugin"
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and attr_name.endswith("Plugin"):
                try:
                    return obj()
                except Exception:
                    return None

        # 2. Look for a top-level ``register`` callable
        register = getattr(module, "register", None)
        if callable(register):
            return register

        return None

    # -- Plugin access -------------------------------------------------------

    def get_plugins(self) -> list[Any]:
        """Return a copy of all loaded plugins."""
        return list(self._plugins)

    # -- Hook registry -------------------------------------------------------

    def register_hook(self, event: str, handler: Callable[..., Any]) -> None:
        """Register a *handler* for an *event*."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)

    def get_hooks(self, event: str) -> list[Callable[..., Any]]:
        """Return handlers registered for *event*."""
        return self._hooks.get(event, [])
