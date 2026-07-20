# Persistence Implementation Plan

> Created: 2026-07-18 | Updated: 2026-07-19 | Phase: 1 (Foundation) | Spec: §4.5, §4.6, §7, §13.4

## Overview

pyharness currently loses all state on restart — provider configs, model selections, sessions, and token counts are all in-memory only. This plan implements end-to-end persistence so that restarts continue where the user left off.

> **Note (2026-07-19)**: Connected-provider tracking (§4.6) was implemented ahead of schedule. The `PyHarnessApp` now maintains a `_connected_providers` set that determines which models are visible in `/models`. See SPEC §4.6 and `src/pyharness/tui/app.py` for details.

### Success metrics

- [x] ~~Provider API keys survive restart (saved on connect, loaded on startup)~~ → Implemented via `_save_provider_key()` + `load_config()` in connect flow
- [x] ~~Selected model survives restart~~ → Implemented via `save_config({"model": ...})` on model switch
- [ ] Sessions survive restart (created, resumed, switched)
- [ ] Token counts persist across restarts and display live
- [x] ~~Status bar shows live `{agent} | {model} | {provider} | {tokens}`~~ → Implemented via `ChatScreen.update_status()`
- [x] ~~Shutdown saves all state; `KeyboardInterrupt` does not corrupt data~~ → Implemented via `_save_state()` in `on_unmount`

---

## Task 1: `save_config()` utility

**Priority**: P0 (blocking Tasks 6, 7)  
**Agent**: `py-dev-malcom` (backend)  
**Files**: `src/pyharness/config/loader.py`  
**Tests**: `tests/test_config/test_save_config.py` (~200 lines)  
**QA**: `qa-myron`

### Requirements

Create a `save_config()` function in `config/loader.py` that:

1. Reads the existing `pyharness.json` file using `json5.load()` to preserve comments
2. Deep-merges changes into the parsed dict (same merge logic as `_merge_configs`)
3. Serializes back with `json5.dumps()` preserving trailing commas and comments
4. Writes to the original file path (or the path from `PYHARNESS_CONFIG` env var)
5. Creates parent directories if they don't exist
6. Is async-safe — uses `aiofiles` or synchronous write in a thread

### Interface

```python
def save_config(
    changes: dict[str, Any],
    config_path: Path | None = None,
) -> None:
    """Merge *changes* into the user config file and write it back.

    JSONC comments in the original file are preserved.
    If *config_path* is None, writes to ~/.config/pyharness/pyharness.json.
    """
```

### Acceptance criteria

- [x] Write `save_config({"model": "openai:gpt-5"})` → file contains `"model": "openai:gpt-5"` with other keys unchanged
- [x] JSONC comments in original file survive round-trip
- [x] Write `save_config({"provider": {"openai": {"apiKey": "sk-xxx"}}})` → nested provider config merged correctly
- [x] Missing parent directories are created (e.g., `~/.config/pyharness/` does not exist)
- [x] Empty changes dict is a no-op (writes nothing or writes identically)
- [x] Handles `PYHARNESS_CONFIG` env var — writes to the custom path, not the default

### Implementation notes

- Reuse `_merge_configs()` helper already in `loader.py`
- `json5.dumps(obj, trailing_commas=False, quote_keys=True)` — trailing commas can cause parse issues
- Use `Path.write_text()` internally
- Add `save_config` to `config/__init__.py` exports

---

## Task 2: Wire SessionStore into app lifecycle

**Priority**: P0 (blocking Tasks 3, 5)  
**Agent**: `py-dev-malcom` (backend + TUI integration)  
**Files**: `src/pyharness/tui/app.py`, `src/pyharness/core/session.py`  
**Tests**: `tests/test_core/test_session_lifecycle.py`, `tests/test_tui/test_app_lifecycle.py`  
**QA**: `qa-myron`

### Requirements

1. **Instantiate SessionStore** at app startup with the standard path:
   - `~/.local/share/pyharness/sessions/sessions.db`
   - Ensure parent directories exist
   - Use WAL mode (already default in `SessionStore`)

2. **Current session pointer**: Read/write `~/.local/share/pyharness/current`
   - Format: single line containing the session ID
   - Create parent directory if missing

3. **Startup flow** (implement in `PyHarnessApp.on_mount()`):
   ```python
   async def on_mount(self) -> None:
       self.store = SessionStore(_data_dir() / "sessions" / "sessions.db")
       await self.store.initialize()

       # Load or create session
       current_id = _read_current_pointer()
       try:
           if current_id:
               self.session = await self.store.get_session(current_id)
           else:
               self.session = await self.store.create_session()
               _write_current_pointer(self.session.id)
       except SessionNotFoundError:
           self.session = await self.store.create_session()
           _write_current_pointer(self.session.id)
   ```

4. **Shutdown flow** (implement in `action_quit` and `on_unmount`):
   ```python
   async def action_quit(self) -> None:
       await self._save_and_cleanup()
       self.exit()

   async def _save_and_cleanup(self) -> None:
       # Save session
       self.session.status = "idle"
       self.session.updated_at = datetime.now(UTC).isoformat()
       await self.store.update_session(self.session)

       # Save config (provider keys, model)
       save_config({"model": self.session.model}, ...)

       # Write current pointer
       _write_current_pointer(self.session.id)

       # Close DB
       await self.store.close()
   ```

5. **KeyboardInterrupt / SIGTERM** handling:
   - Register a signal handler that sets a flag
   - `on_unmount` calls the same `_save_and_cleanup()`
   - Print a clean "Session saved. Goodbye!" message

### Acceptance criteria

- [x] First run creates `~/.local/share/pyharness/sessions/sessions.db` and a new session
- [x] `~/.local/share/pyharness/current` contains the session ID
- [x] Restart loads the same session (messages preserved)
- [x] Restart with no sessions creates a new session
- [x] `Ctrl+C` (KeyboardInterrupt) saves session and exits cleanly
- [x] SQLite connection is closed on exit (no `sqlite3.ProgrammingError` on restart)

### Implementation notes

- Add a `current_session` helper module or put helpers directly in `app.py`
- The `SessionStore` already has all CRUD — this task is about wiring it into lifecycle
- No LangGraph checkpointer yet — that's Phase 2
- Use `atexit` or `signal.signal` for SIGTERM

---

## Task 3: Token tracking

**Priority**: P1  
**Agent**: `py-dev-malcom` (backend)  
**Files**: `src/pyharness/core/agent.py`  
**Tests**: `tests/test_core/test_token_tracking.py`  
**QA**: `qa-myron`

### Requirements

1. **Capture `usage_metadata`** in `AgentRunner.run()`:
   - LangChain's `on_chat_model_stream` events include a final chunk with `usage_metadata`
   - Track both `on_chat_model_stream` (per-chunk) and detect the usage chunk
   - Alternative: listen for `on_chat_model_end` event (more reliable for usage)

2. **Yield a `usage` event**:
   ```python
   yield {
       "type": "usage",
       "data": {
           "input_tokens": usage.get("input_tokens", 0),
           "output_tokens": usage.get("output_tokens", 0),
           "total_tokens": usage.get("total_tokens", 0),
       }
   }
   ```

3. **Update session in TUI** (in ChatScreen message handler):
   ```python
   if event["type"] == "usage":
       self.session.total_tokens += event["data"]["total_tokens"]
       await self.store.update_session(self.session)
       self.status_bar.update_token_count(self.session.total_tokens)
   ```

4. **Per-message token tracking** (optional, Phase 1 scope):
   - Store `token_count` in the `Message` dataclass
   - Write to `messages.token_count` column in SQLite via `SessionStore.add_message()`

### Acceptance criteria

- [x] Each assistant response updates the live token counter in the status bar
- [x] Token count is saved to `Session.total_tokens` in SQLite
- [x] On restart, token count is restored
- [x] Token count never decreases
- [x] Works with Anthropic, OpenAI, and OpenRouter models (all provide `usage_metadata`)
- [x] Token count displays with comma formatting: `4,231 tokens`

### Implementation notes

- LangChain usage_metadata format: `{"input_tokens": N, "output_tokens": N, "total_tokens": N}`
- Not all providers include `usage_metadata` on every chunk — listen for `on_chat_model_end`
- Fallback: if no `usage_metadata`, token count remains unchanged (no crash)

---

## Task 4: Status bar redesign

**Priority**: P1  
**Agent**: `ux-marry` (design), `py-dev-malcom` (implementation)  
**Files**: `src/pyharness/tui/widgets/status.py`, `src/pyharness/tui/screens/chat.py`  
**Tests**: `tests/test_tui/test_status_bar.py`  
**QA**: `qa-myron`

### Requirements

1. **New format**: `{agent} | {model} | {provider} | {tokens}`
   - Agent: always present (e.g., `build`)
   - Model: `provider:model-id` string, blank if none selected
   - Provider: short name, blank if none selected
   - Tokens: `{n:,} tokens`, `0 tokens` initially

2. **Reactive widget**: `StatusBar` should accept update messages
   ```python
   class StatusBar(Static):
       def on_mount(self):
           self.agent_name = "build"
           self.model_name = ""
           self.provider_name = ""
           self.total_tokens = 0
           self._render()

       def update_agent(self, name: str) -> None: ...
       def update_model(self, name: str) -> None: ...
       def update_provider(self, name: str) -> None: ...
       def update_tokens(self, count: int) -> None: ...
   ```

3. **Styling**: Use Textual Rich styles
   - Agent: `bold` (always present)
   - Model/provider: dimmed when blank
   - Tokens: dimmed
   - Separators: dimmed `#58a6ff` color
   - Background: `#161b22`, border-top: `#30363d`

4. **Live updates**: Status bar must respond to model switches, agent switches, and token increments

### Acceptance criteria

- [x] Status bar shows `build | | | 0 tokens` at startup (no model configured)
- [x] After `/model anthropic:claude-sonnet-4-5`, shows `build | anthropic:claude-sonnet-4-5 | anthropic | 0 tokens`
- [x] After sending a message, token count increases
- [x] Agent name changes when pressing Tab
- [x] Blank fields render cleanly (no trailing `|` with empty values — use the full format with blanks)

---

## Task 5: Session browser

**Priority**: P2 (Phase 2 — depends on Task 2)  
**Agent**: `ux-marry` (design), `py-dev-malcom` (implementation)  
**Files**: `src/pyharness/tui/screens/sessions.py`, `src/pyharness/tui/widgets/sidebar.py`  
**Tests**: `tests/test_tui/test_session_browser.py`  
**QA**: `qa-myron`

### Requirements

1. **Populate from SessionStore**: Replace the current static placeholder with a `ListView` or `DataTable` showing:
   - Session title
   - Date (formatted: `Jul 18`)
   - Model (if set)
   - Token count (formatted)
   - Active indicator (● for current session)

2. **Actions**:
   - **Switch/Resume**: Select a session → update `current` pointer → load session into chat
   - **New**: Create new session, save current, switch
   - **Archive**: Set status to `archived`, remove from active list

3. **Keyboard navigation**: Arrow keys to navigate, Enter to select, `n` for new

### Acceptance criteria

- [x] Session browser shows all sessions from SQLite
- [x] Switching sessions updates the chat (loads message history)
- [x] Creating a new session saves the current one first
- [x] Archiving hides the session from the active list
- [x] Empty state: "No sessions yet" with a New button
- [x] Session browser refreshes after each new session creation

---

## Task 6: Provider persistence on shutdown/startup

**Priority**: P0 (blocking Task 7)  
**Agent**: `py-dev-malcom`  
**Files**: `src/pyharness/config/loader.py`, `src/pyharness/tui/screens/connect.py`, `src/pyharness/tui/app.py`  
**Tests**: `tests/test_config/test_provider_persistence.py`  
**QA**: `qa-myron`

### Requirements

1. **Save on provider connect**: When `ConnectScreen._save_provider_key()` is called, use `save_config()` instead of the current raw `json.dump()` approach
2. **Load on startup**: Already works via `load_config()` — no changes needed for loading
3. **Re-verify connection on startup**: After loading providers, attempt a lightweight ping (e.g., list models with timeout=5s) to verify API keys are still valid
4. **Provider status UI**: After startup verification, show which providers are connected (green ✓) vs failed (red ✗)

### Acceptance criteria

- [x] Connect an Anthropic provider → restart → provider is still configured
- [x] Connect an Anthropic provider → restart → status shows "connected" (green)
- [x] Expired/revoked API key → status shows "auth failed" (red)
- [x] `pyharness.json` comments survive provider key writes
- [x] Provider keys are never written in plaintext to logs or TUI output

### Implementation notes

- Replace `ConnectScreen._save_provider_key` raw `json.dump` with `save_config()`
- On startup verification: `provider.get_model_list()` with short timeout; catch auth errors
- Provider status dict should survive restart (derived from config, not stored separately)

---

## Task 7: Model persistence

**Priority**: P0 (blocking Tasks 3, 4)  
**Agent**: `py-dev-malcom`  
**Files**: `src/pyharness/tui/screens/chat.py`, `src/pyharness/config/loader.py`  
**Tests**: `tests/test_config/test_model_persistence.py`  
**QA**: `qa-myron`

### Requirements

1. **Save on model switch**: When user runs `/model anthropic:claude-sonnet-4-5`, call `save_config({"model": "anthropic:claude-sonnet-4-5"})`
2. **Load on startup**: Read `config.model` from `PyHarnessConfig` (already loaded via `load_config()`)
3. **Refresh model list on startup**: If a model is selected, refresh the model list for that provider so the UI shows available models
4. **Handle missing model**: If the saved model is no longer available (e.g., provider removed), clear the model field and show blank in status bar
5. **Model list empty on startup** if no provider is configured — shows blank model

### Acceptance criteria

- [x] `/model openai:gpt-5` → restart → model is `openai:gpt-5`
- [x] Provider removed but model still set → model cleared on next provider refresh
- [x] No provider configured → model blank in status bar
- [x] Model switch updates status bar immediately (no restart needed)
- [x] Model list refreshes after provider connect

---

## Task 8: Integration tests

**Priority**: P1  
**Agent**: `qa-myron` (test author), `py-dev-malcom` (fixtures)  
**Files**: `tests/test_integration/test_persistence_e2e.py`  
**Approx**: 300-400 lines

### Test scenarios

1. **Full lifecycle**: Start app, connect provider, select model, send message, verify token count, quit, restart, verify all state restored
2. **Session CRUD**: Create, switch, archive — verify SQLite state after each
3. **Token accumulation**: Send 3 messages, verify cumulative token count
4. **Config round-trip**: Write config, restart, verify same values
5. **Graceful shutdown on SIGTERM**: Send SIGTERM, verify SQLite is not corrupted
6. **Empty state**: First run with no config, no sessions — verify app starts without errors

### Test fixtures needed

- `tmp_config_dir` — `tmp_path` fixture that creates `~/.config/pyharness/` structure
- `tmp_data_dir` — `tmp_path` fixture that creates `~/.local/share/pyharness/` structure
- `mock_llm_with_usage` — Mock LLM that returns `usage_metadata` in streaming
- `session_store(tmp_path)` — SessionStore connected to temp SQLite

---

## Dependencies

```
Task 1 (save_config)
  ├──► Task 6 (provider persistence)
  │      └──► Task 7 (model persistence)
  │             └──► Task 4 (status bar)
  └──► Task 7 (model persistence)

Task 2 (SessionStore lifecycle)
  ├──► Task 3 (token tracking)
  │      └──► Task 4 (status bar)
  ├──► Task 4 (status bar: session context)
  └──► Task 5 (session browser)

Task 8 (integration tests) ← all tasks
```

## Agent assignments

| Task | Agents | Est. effort |
|------|--------|-------------|
| Task 1: save_config | `py-dev-malcom`, `qa-myron` | 1 day |
| Task 2: SessionStore lifecycle | `py-dev-malcom`, `qa-myron` | 2 days |
| Task 3: Token tracking | `py-dev-malcom`, `qa-myron` | 1 day |
| Task 4: Status bar | `ux-marry`, `py-dev-malcom`, `qa-myron` | 1 day |
| Task 5: Session browser | `ux-marry`, `py-dev-malcom`, `qa-myron` | 1.5 days |
| Task 6: Provider persistence | `py-dev-malcom`, `qa-myron` | 0.5 days |
| Task 7: Model persistence | `py-dev-malcom`, `qa-myron` | 0.5 days |
| Task 8: Integration tests | `qa-myron`, `py-dev-malcom` (fixtures) | 1.5 days |

**Total estimated effort**: ~9 days (1.8 weeks)

## Execution order (recommended)

1. **Task 1** first — `save_config()` is a dependency for Tasks 6 and 7
2. **Task 2** next — SessionStore lifecycle is needed for Tasks 3, 4, 5
3. **Task 6 + Task 7** in parallel — both depend only on Task 1
4. **Task 3** after Task 2 — token tracking depends on SessionStore being wired
5. **Task 4** after Tasks 3, 6, 7 — status bar needs all data sources
6. **Task 5** after Task 2 — session browser uses SessionStore directly
7. **Task 8** last — integration tests verify the full chain

## Handoff to dev-lead-bubba

Once this plan is approved, dev-lead-bubba should:
1. Create GitHub issues for each task (or use Linear/Jira)
2. Dispatch tasks in execution order
3. Ensure `ux-marry` completes Task 4 + Task 5 design before `py-dev-malcom` starts implementation
4. Coordinate Task 8 fixtures between `qa-myron` and `py-dev-malcom`
