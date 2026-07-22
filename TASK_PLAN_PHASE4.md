# Phase 4: Tabbed TUI — Implementation Plan

## Goal
Visual session management with per-session state — see spec §4.

## Phases

### 1. SessionTabBar widget (R4.1-R4.6) ✅
- [x] Create `src/pyharness/tui/widgets/session_tabs.py`
- [x] Build `SessionTabBar(Widget)` — horizontal tab bar
- [x] R4.1: Display one tab per active session with title
- [x] R4.2: Click tab → switch to that session (via app.switch_to_session)
- [x] R4.3: `+` button creates new session
- [x] R4.4: `×` button closes session (via app._close_session_tab)
- [x] R4.5: Keyboard shortcuts (Ctrl+W for close; Ctrl+Tab/Ctrl+Shift+Tab via app)
- [x] R4.6: Activity indicator (● dot) when agent running

### 2. App tab management (R4.11-R4.15) ✅
- [x] Track active session list + focused session (`_session_screens`, `_session_order`, `_focused_session_id`)
- [x] `action_new_session()` creates session + tab + ChatScreen
- [x] Tab switching via `switch_screen()` (`switch_to_session`, `next_tab`, `previous_tab`)
- [x] Scoped keybindings (Ctrl+W close, Ctrl+Tab/Ctrl+Shift+Tab)
- [x] R4.12: Ctrl+N creates new session (existing)
- [x] R4.13: Ctrl+Q saves all, cancels running agents (existing)
- [x] R4.14: Escape interrupts focused session's agent (updated to use _focused_session_id)
- [x] R4.15: Ctrl+O toggles focused session's sidebar (existing)

### 3. ChatScreen integration (R4.7-R4.10) ✅
- [x] SessionTabBar in ChatScreen compose
- [x] R4.7-R4.8: Per-session sidebar/status (already works — each ChatScreen has own)
- [x] R4.9: /models dropdown — already per-screen (each ChatScreen has its own)
- [x] R4.10: Provider global, model/tokens per-session (provider in app config, per-session sidebar)

### 4. Tests ✅
- [x] 37 tests in `tests/test_tui/test_session_tabs.py`
- [x] SessionTabBar unit tests (creation, state management, messages)
- [x] App tab management tests (bindings, attributes, lifecycle)
- [x] Integration tests (tab lifecycle, close protection, interrupt handling)

## Files Changed
- `src/pyharness/tui/widgets/session_tabs.py` — NEW widget
- `src/pyharness/tui/app.py` — tab management, scoped bindings
- `src/pyharness/tui/screens/chat.py` — SessionTabBar integration
- `src/pyharness/tui/widgets/__init__.py` — export SessionTabBar
- `tests/test_tui/test_session_tabs.py` — NEW tests

## Test Results
- 942 passed, 4 skipped, 1 xfailed (pre-existing libsql skip)
- ruff: all new files pass (0 errors)
- mypy: all new files pass (0 errors)
