"""Pyharness plugin system.

Public API:
    PluginLoader – discovers and loads plugins from local dirs and entry points.
"""

from __future__ import annotations

from pyharness.plugins.loader import PluginLoader

__all__ = ["PluginLoader"]
