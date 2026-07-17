# Changelog

All notable changes to pyharness will be documented in this file.

## [Unreleased]

### @ Autocomplete Dropdown Widget — 2026-07-16

#### Changed
- **Replaced RichLog-based @ autocomplete** with a proper `AtAutocomplete` dropdown widget that appears above the PromptInput.
- **New widget** (`src/pyharness/tui/widgets/at_autocomplete.py`): `AtAutocomplete` extends `Widget` with a scrollable list showing agent names (🤖) and files (📄). Supports real-time filtering, arrow-key navigation, Enter selection, and Escape dismissal.
- **Updated `PromptInput`** (`src/pyharness/tui/widgets/input.py`): `_show_at_dropdown` and `_show_slash_dropdown` now mount and update the dropdown widget instead of writing to the chat RichLog. Arrow keys navigate, Enter selects, Escape dismisses via `_on_key`.
- **CSS** (`src/pyharness/tui/app.py`): Added styles for `.autocomplete-dropdown` with `.at-header` and `.at-item.-highlighted` classes.
- **Tests updated**: 5 regression tests now verify dropdown widget existence, item counts, filtering, and visibility instead of RichLog line counts.

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
