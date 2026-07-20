# Changelog

All notable changes to pyharness will be documented in this file.

## [Unreleased]

### Remove static model list — 2026-07-19

#### Changed
- **SPEC §4.6**: Removed all references to `_STATIC_MODELS`. Model discovery
  now uses live API fetches (OpenRouter, Ollama) or single-model
  `_VERIFY_MODELS` entries (all other providers). No static fallback.
- **SPEC §4.6.1**: New section documenting the `_VERIFY_MODELS` map —
  each non-live provider gets exactly one model ID, used for both
  connection verification and model discovery.
- **SPEC §14 Phase 1**: Updated to reflect live model discovery with
  `_VERIFY_MODELS` fallback instead of static model list.
- **`src/pyharness/core/provider.py`**: `_STATIC_MODELS` removed.
  `fetch_models()` uses live API for `openrouter`/`ollama` and
  `_VERIFY_MODELS` for all other providers. No static-list fallback
  anywhere.
- **Tests updated** to reflect new model discovery behavior.

### Connected Provider Model Filtering — 2026-07-19

#### Fixed
- **Bug: `/models` showed models from ALL configured providers**, even ones the user never connected to. Root cause: `fetch_models()` used `set(config.provider.keys())` which included every provider in the config file regardless of connection status.
- **`fetch_models()` now accepts an optional `providers` filter parameter** (`src/pyharness/core/provider.py`): When a `providers: set[str]` is passed, only models from those providers are returned.
- **`PyHarnessApp` tracks `_connected_providers`** (`src/pyharness/tui/app.py`): New attribute and `_populate_connected_providers()` method determine which providers are actually connected on startup (non-empty, non-placeholder API keys, or resolved env-var placeholders).
- **`refresh_models()` passes connected providers** to `fetch_models()`.
- **`_handle_connect_result()` adds provider** to `_connected_providers` on successful `/connect`.
- **Non-live provider fallback** (`src/pyharness/core/provider.py`): When a connected provider has no live model API (e.g. `deepseek`) and the static model list has no entries for it, `fetch_models()` now falls back to the verifier-model map (`_VERIFY_MODELS`) to ensure at least one well-known model ID is always available per connected provider.
- **SPEC §4.6 added** documenting provider connection tracking and model discovery rules, including non-live provider fallback.
- **`docs/persistence-plan.md` updated** with connected-provider tracking status and forward-reference to SPEC §4.6.

#### Added
- **Tests** (`tests/test_core/test_provider.py`): 3 tests in `TestConnectedProviderFiltering` — `test_fetch_models_only_connected_providers`, `test_fetch_models_empty_when_no_connected_providers`, `test_fetch_models_no_filter_includes_all_configured`.
- **Tests** (`tests/test_tui/test_regression.py`): 5 tests in `TestConnectedProviderModelFilter` — `test_models_list_shows_only_connected_provider_models`, `test_models_list_empty_when_no_connected_providers`, `test_connected_providers_populated_from_config`, `test_connected_providers_updated_after_connect`, `test_connected_providers_accumulates_on_multiple_connects`.
#### Audit & Fix (bubba, 2026-07-19)
- **Bug found: Mixed live/non-live provider model loss**. When both a live provider (e.g. `openrouter`) and a non-live provider (e.g. `deepseek`) were connected, `fetch_models()` only returned models from the live fetch. Non-live providers silently got zero results because their fallback path was only entered when *no* live providers were active.
- **Fix applied** (`src/pyharness/core/provider.py` lines 280-296): After the live fetch and filtering, the code now supplements results with static-fallback or verifier-model entries for any scope provider not covered by the live fetch — reusing the same logic already present in the all-non-live branch.
- **Test expectations updated** (`tests/test_core/test_provider.py`): `test_fetch_models_from_openrouter_returns_list` and `test_fetch_models_with_ollama_configured` now use `sorted()` expectations to match the documented "sorted list" return contract.
- **Verification**: All 26 provider tests pass; all 639 total tests pass (excluding pre-existing `libsql` import bug in `session.py`). Manual scenario testing confirms deepseek models appear alongside openrouter when both are connected.
#### Audit (pm-devon, 2026-07-19)
- Reviewed SPEC §4.6, CHANGES.md, persistence-plan.md, provider.py, app.py, connect.py, and all related tests.
- **Implementation matches spec**: ✅. All four conditional branches verified (None → all, set() → empty, non-live → fallback, live → fetch+filter).
- **Tests pass**: Connected provider filtering tests correctly guard against model leakage from unconnected providers.
- **connect.py verification flow confirmed**: `_save_provider_key()` saves key then `_run_verification()` calls `verify_connection()` before dismissing — correct per SPEC §4.6.

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
