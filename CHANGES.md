# Changelog

All notable changes to pyharness will be documented in this file.

## [Unreleased]

### Phase 4 — Plugin System

#### Added
- **Plugin loader** (`src/pyharness/plugins/loader.py`): `PluginLoader` class discovers and loads plugins from local directories (`.pyharness/plugins/`, `~/.config/pyharness/plugins/`) and pip entry points (`pyharness` group).
- **Hook registry**: `register_hook(event, handler)` and `get_hooks(event)` for extensible lifecycle events.
- **Example plugins**:
  - `NotificationPlugin` (`src/pyharness/plugins/notification.py`): Desktop notifications on session events via `notify-send`.
  - `EnvProtectionPlugin` (`src/pyharness/plugins/env_protection.py`): Blocks read access to `.env` files.
- **Entry points** in `pyproject.toml`: `notification` and `env-protection` registered under `[project.entry-points.pyharness]`.
- **Tests** (`tests/test_plugins.py`): 24 tests covering loader lifecycle, hook registration, entry-point discovery, local file discovery, error handling, and example plugin behaviour.

### Phase 3 — Themes, Keybinds & Session Browser

#### Added
- **Theme system** (`src/pyharness/tui/themes/__init__.py`): Registry of 5 built-in themes (Tokyo Night, Dark, Light, Dracula, Nord) with `get_theme()`, `get_all_themes()`, and `list_theme_names()` functions.
- **Theme switching** (`action_theme` in `app.py`): Apply a theme by name at runtime, with notification feedback.
- **Session browser** (`src/pyharness/tui/screens/sessions.py`): Screen for browsing active/archived sessions with 🧠 memory badge support for MemPalace data.
- **Keybind customization** (`_load_keybinds` in `app.py`): Load custom keybinds from `~/.config/pyharness/tui.json` or `.pyharness/tui.json`, merging with defaults.
- **`/sessions` command**: Opens the session browser screen from the chat input or command palette.

#### Changed
- `on_mount` now calls `_load_keybinds()` before pushing the chat screen.
- `/sessions` in chat dispatches `action_sessions()` instead of showing a static message.
- `/themes` in chat lists themes from the actual theme registry.
