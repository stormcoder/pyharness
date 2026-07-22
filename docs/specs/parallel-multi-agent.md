# Parallel Multi-Agent Execution — Specification

## Vision

**Run multiple agents independently, in parallel, each in its own session tab.** Users create sessions, assign models and agents to each, and run them concurrently — one session generating code while another researches, without blocking the UI or each other.

## Current State

pyharness supports a single session with a single active agent. The storage layer (libsql `SessionStore`) already supports multiple concurrent sessions. All other layers need work.

---

## 1. Session Architecture

### 1.1 Per-Screen Session Ownership

Each `ChatScreen` instance owns exactly one session. The app-level scalar `_current_session_id` is replaced by a session registry.

**Requirements**:

- **R1.1** `ChatScreen.__init__` accepts a `session_id: str` parameter.
- **R1.2** `ChatScreen` stores `session_id` as an instance attribute and uses it for all agent runs and message persistence.
- **R1.3** `PyHarnessApp` maintains `_active_sessions: dict[str, str]` mapping screen IDs to session IDs.
- **R1.4** `ChatScreen.on_input_submitted` reads `self.session_id`, not `self.app._current_session_id`.
- **R1.5** Agent messages are persisted to the session's message store via `SessionStore.add_message(self.session_id, ...)`.

### 1.2 Session Lifecycle

Sessions can be created, resumed, closed, and archived.

**Requirements**:

- **R1.6** `action_new_session()` creates a new `Session` via `SessionStore`, creates a new `ChatScreen(session_id=...)`, and switches to it.
- **R1.7** `action_sessions()` opens a `SessionBrowser` that queries `SessionStore.list_sessions()` and displays active/idle/archived sessions.
- **R1.8** `SessionBrowser` supports: create new, resume existing, archive, and delete sessions.
- **R1.9** Closing a session tab saves the session state and updates `Session.status` to `"idle"` or `"archived"`.
- **R1.10** `on_unmount` for `ChatScreen` calls `SessionStore.update_session()` to persist token counts and status.

### 1.3 Session Pointer File

**Requirements**:

- **R1.11** The `current` pointer file at `~/.local/share/pyharness/sessions/current` is replaced by `active.json` containing `{"tabs": [{"session_id": "...", "screen_id": "..."}]}`.
- **R1.12** On startup, the app restores all previously-active session tabs from `active.json`.

---

## 2. Agent Runtime

### 2.1 Session-Scoped Checkpointing

Each session gets an isolated LangGraph checkpoint space via its `thread_id`.

**Requirements**:

- **R2.1** `create_agent_graph(model, tools, checkpointer)` must be called with a real `SqliteSaver` (or `AsyncSqliteSaver`) instance.
- **R2.2** The checkpointer is created once per app instance, shared across all sessions. Thread isolation is handled by LangGraph's `thread_id` config key.
- **R2.3** `AgentRunner` config uses `configurable.thread_id = session_id` for per-session checkpoint isolation.
- **R2.4** Agent graphs are compiled once per session (not per message) and stored for the session lifetime. Recompilation happens only when the model or tools change.
- **R2.5** Each session's compiled graph is stored in a `dict[session_id, CompiledStateGraph]` on a `SessionGraphRegistry`.

### 2.2 Cancellation and Interrupt

**Requirements**:

- **R2.6** `AgentRunner.run()` accepts an optional `asyncio.Event` for cancellation. The `astream_events` loop checks the event between iterations.
- **R2.7** `action_interrupt()` cancels the running agent for the currently focused session without affecting other sessions.
- **R2.8** A cancelled agent saves its partial state via the checkpointer and appends a `"[Interrupted]"` message to the chat.

### 2.3 Per-Session Model and Agent Selection

**Requirements**:

- **R2.9** Each session stores its own `model` and `agent` in the `Session` record.
- **R2.10** `ChatScreen` reads `model` and `agent` from its session record on mount, not from the global app config.
- **R2.11** Model switching (`/model`) updates the session's stored model, not the global config.
- **R2.12** Agent switching (`Tab`) updates the session's stored agent, not the global index.

---

## 3. Concurrency Model

### 3.1 AgentManager

A central manager owns the lifecycle of all running agent tasks.

**Requirements**:

- **R3.1** `AgentManager` class with `_tasks: dict[str, asyncio.Task]` mapping `session_id` → running `asyncio.Task`.
- **R3.2** `AgentManager.launch(session_id, runner, screen)` creates an `asyncio.create_task()` for the agent run and stores it.
- **R3.3** Streaming output from the agent is routed to the correct `ChatScreen` via the `screen` reference passed at launch time.
- **R3.4** `AgentManager.cancel(session_id)` cancels the task for that session.
- **R3.5** `AgentManager.is_running(session_id)` returns whether a task is active for that session.
- **R3.6** `AgentManager.cancel_all()` cancels all running tasks (used on app shutdown).

### 3.2 Event Routing

Each agent's streaming events must go to its owning ChatScreen.

**Requirements**:

- **R3.7** The `AgentRunner.run()` async generator is consumed by `AgentManager.launch()` which dispatches events to the target screen.
- **R3.8** Content events call `screen._write(token)` on the owning screen.
- **R3.9** Tool call/result events call `screen._write(...)` on the owning screen.
- **R3.10** Done events update the session record and status bar for the owning screen.

### 3.3 Concurrency Limits

**Requirements**:

- **R3.11** Configurable `max_concurrent_agents` (default: 4) in `PyHarnessConfig`.
- **R3.12** When the limit is reached, `AgentManager.launch()` queues the request and notifies the user.
- **R3.13** Queued agents launch automatically when a running agent completes.

### 3.4 Async Tool Safety

**Requirements**:

- **R3.14** All sync tools that call `asyncio.run()` are converted to use `loop.run_until_complete()` or replaced with async-native equivalents.
- **R3.15** `memory_tools.py` wrappers are tested for safe operation under a running event loop.

---

## 4. TUI Architecture

### 4.1 Session Tabs

A tabbed interface replaces the single-ChatScreen model.

**Requirements**:

- **R4.1** A `SessionTabBar` widget displays one tab per active session, showing the session title (or "New Session" for unnamed sessions).
- **R4.2** Clicking a tab switches to that session's ChatScreen. Textual's `TabbedContent` or a custom tab widget is used.
- **R4.3** `+` button on the tab bar creates a new session.
- **R4.4** `×` button on each tab closes the session (saves state, removes tab).
- **R4.5** Tab keyboard shortcuts: `Ctrl+Tab` next tab, `Ctrl+Shift+Tab` previous tab, `Ctrl+W` close current tab.
- **R4.6** Each tab shows an activity indicator (spinner/dot) when its agent is running.

### 4.2 Per-Session State Isolation

**Requirements**:

- **R4.7** Each `ChatScreen` has its own `Sidebar` reflecting that session's context (token count, provider, model, agent).
- **R4.8** Each `ChatScreen` has its own `StatusBar` showing `{agent} | {model} | {provider} | {tokens}` for that session.
- **R4.9** The model dropdown (`/models`) scopes to the active session — showing models for that session's provider.
- **R4.10** Provider connection status in the sidebar is global (connections are app-level), but the "active model" and token counts are per-session.

### 4.3 Keyboard Binding Scoping

**Requirements**:

- **R4.11** `Tab` switches agents for the **focused** session, not globally.
- **R4.12** `Ctrl+N` creates a new session tab.
- **R4.13** `Ctrl+Q` quits the app (saves all sessions, cancels running agents).
- **R4.14** `Escape` interrupts the agent in the **focused** session.
- **R4.15** `Ctrl+O` toggles the sidebar of the **focused** session.

### 4.4 TUI Component Tree

```
PyHarnessApp
├── SessionTabBar            (global — always visible)
│   ├── Tab "Session 1" 🟢
│   ├── Tab "Session 2" ⏳
│   └── [+] New Session
├── TabContent
│   ├── ChatScreen(session_id="s1")
│   │   ├── ChatArea (RichLog)  
│   │   ├── PromptInput
│   │   ├── Sidebar (per-session)
│   │   └── StatusBar (per-session)
│   └── ChatScreen(session_id="s2")
│       └── ... (same structure)
└── (overlays: ConnectScreen, SessionBrowser, CommandPalette)
```

---

## 5. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Session decoupling — screens own their sessions.

- Pass `session_id` to `ChatScreen.__init__` **(R1.1, R1.2)**
- Build `SessionRegistry` replacing scalar `_current_session_id` **(R1.3, R1.4)**
- Persist messages per-session **(R1.5)**
- Build real `SessionBrowser` with `SessionStore.list_sessions()` **(R1.7, R1.8)**
- Replace `current` pointer with `active.json` **(R1.11, R1.12)**

### Phase 2: Agent Checkpointing (Week 1-2)
**Goal**: Durable execution with per-session isolation.

- Add `SqliteSaver` checkpointer to `create_agent_graph` **(R2.1, R2.2)**
- Compile graphs once per session **(R2.4, R2.5)**
- Per-session model/agent storage **(R2.9, R2.10, R2.11, R2.12)**
- Cancellation support in `AgentRunner` **(R2.6)**
- Real `action_interrupt` **(R2.7, R2.8)**

### Phase 3: Concurrency Manager (Week 2-3)
**Goal**: Multiple agents run simultaneously without conflicts.

- Build `AgentManager` with task lifecycle **(R3.1 - R3.6)**
- Route streaming events per-screen **(R3.7 - R3.10)**
- Concurrency limits and queuing **(R3.11 - R3.13)**
- Fix async tool safety **(R3.14, R3.15)**

### Phase 4: Tabbed TUI (Week 3-4)
**Goal**: Visual session management with per-session state.

- Build `SessionTabBar` widget **(R4.1 - R4.6)**
- Per-session sidebar and status bar **(R4.7 - R4.10)**
- Scoped keyboard bindings **(R4.11 - R4.15)**
- Session lifecycle: create, switch, close, restore **(R1.6, R1.9, R1.10)**

### Phase 5: Polish & Testing (Week 4-5)
**Goal**: Production readiness.

- Snapshot tests for multi-tab layout
- Concurrency stress tests (4 agents × 100 messages)
- Checkpoint restore tests (crash recovery)
- Session migration tests (upgrade from single-session config)
- Performance profiling for tab switching and agent launch

---

## 6. Migration Path

Existing single-session users upgrade seamlessly:

1. On first startup with the new version, the existing `current` pointer file is migrated to `active.json` with a single entry.
2. The existing single ChatScreen becomes the first tab.
3. `action_new_session()` creates additional tabs.
4. The global `pyharness.json` config remains for defaults; per-session overrides are stored in each `Session` record.

---

## 7. Non-Goals (Explicitly Out of Scope)

- **Inter-agent communication**: Agents in different sessions do not message each other. This is session-scoped parallelism, not swarm orchestration.
- **Shared memory between sessions**: Each session has its own message history. MemPalace wings may span sessions but that is an orthogonal feature.
- **Distributed execution**: Agents run on the local machine within the same Python process. Remote agent execution is a separate feature.
- **GPU/multi-process parallelism**: Agents share the same asyncio event loop. CPU-bound tool execution would need a separate process pool (future work).
