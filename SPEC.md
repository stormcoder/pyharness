# pyharness — Specification

## Vision

**"The terminal coding agent that remembers."** — A Python-native TUI LLM harness with persistent semantic memory, powered by LangGraph and MemPalace. MCP-native, Python-first, with cross-session recall that no other terminal coding agent offers.

## Primary Functionality

> **Sending messages to a connected LLM and receiving streaming responses is the #1 core function.** Every other feature — memory, tools, sessions, autocomplete — exists to enhance this primary interaction. The TUI must:
> 1. Let the user type a message and press Enter
> 2. Resolve the user's configured model via the provider bridge
> 3. Execute a LangGraph ReAct agent loop with registered tools
> 4. **Stream each token individually** to the chat area as it arrives — no buffering, no all-at-once dump
> 5. Display tool calls and their results inline
> 6. Append a formatted markdown rendering of the complete response after streaming finishes
> 7. Update the token counter in the status bar with each message exchanged
>
> If a user has connected a provider and selected a model, sending a message MUST call the LLM — never return a stub. Graceful errors only when no provider is connected or no model is selected.

---

## 1. Tech Stack & Rationale

| Layer | Choice | Why |
|-------|--------|-----|
| TUI framework | **[Textual](https://textual.textualize.io/)** 2.x+ | Mature, CSS-like layout, built-in widgets, reactive data-binding, async-native. Only Python TUI capable of multi-panel polished experience. |
| Agent runtime | **[LangGraph](https://github.com/langchain-ai/langgraph)** | Durable execution, streaming, checkpointing, HITL, sub-agent orchestration, 50+ model providers. Production-proven at scale. |
| LLM models | **LangChain chat models** + **OpenRouter** | 18 first-party LangChain packages + OpenRouter for 200+ models across 50+ providers. Every major provider covered through a single interface. Full strategy in §10. |
| Memory | **[MemPalace](https://github.com/MemPalace/mempalace)** | Local-first semantic memory. 96.6% R@5 on LongMemEval. Verbatim storage, knowledge graph, agent diaries. Pluggable backend (ChromaDB default). |
| Configuration | **pydantic** v2 + JSON5 | Type-safe config with schema validation; `pyharness.json` mirrors `opencode.json` semantics. |
| Git integration | **GitPython** | Snapshot/restore for undo/redo; diff generation; branch-aware session tracking. |
| MCP client | **langchain-mcp-adapters** + native **mcp** SDK | MCP servers as LangChain tools; stdio + HTTP transports; OAuth support. |
| Session storage | **libsql** (Turso local/embedded) | Transactional system of record with concurrent writes (MVCC). Replaces SQLite WAL. LangGraph checkpoints for agent state. |
| File watching | **watchfiles** | Efficient recursive file watcher; powers chat context auto-refresh. |
| Logging | **structlog** | Structured from day one — agent loop traces, tool call records, provider latency. |
| Async runtime | **asyncio** + **anyio** | Textual's native async loop; anyio for structured concurrency. |
| Package manager | **uv** | Fast, reliable; single `pyproject.toml` for deps & build. |
| Testing | **pytest** + **pytest-asyncio** + **pytest-textual-snapshot** | Standard Python testing; TUI screenshot regression testing. |
| Minimum Python | **3.12** | PEP 695 type params; improved error messages; Textual 2.x compatibility. |

### Why NOT DeepAgents

[DeepAgents](https://github.com/langchain-ai/deepagents) (26.2k stars, LangChain) was evaluated as the agent runtime. **Rejected** because:

1. **Competitive conflict**: LangChain ships `deepagents-code` — a terminal coding agent ("similar to Claude Code or Cursor") via `curl -LsSf https://langch.in/dcode | bash`. Building pyharness on DeepAgents means building on infrastructure owned by a direct competitor.
2. **LangGraph is the right abstraction level**: LangGraph gives us durable execution + checkpointing without the opinionated middleware. We build our own agent harness customized for a TUI coding agent.
3. **MemPalace over DeepAgents memory**: DeepAgents has `MemoryMiddleware` but MemPalace provides deeper semantic search, knowledge graphs, and agent diaries — all purpose-built for agent memory.

### Why NOT litellm

litellm was the original choice. **Replaced by LangChain chat models** because:

1. LangGraph uses LangChain models natively — using litellm would require an adapter layer.
2. LangChain covers 50+ providers with the same unified interface.
3. Simpler dependency tree: LangChain is required by LangGraph anyway.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      TUI Layer (Textual)                          │
│  ┌──────────┐ ┌───────────┐ ┌──────────────────────────────────┐ │
│  │ ChatArea │ │ SidePanel │ │ StatusBar                        │ │
│  │ (scroll) │ │ (sessions,│ │ {agent} | {model} | {provider} | │ │
│  │          │ │  files,   │ │ {tokens}                         │ │
│  │          │ │  tools,   │ │                                  │ │
│  │          │ │  memory)  │ │                                  │ │
│  └──────────┘ └───────────┘ └──────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                Core Engine (LangGraph-powered)                    │
│  ┌──────────┐ ┌───────────┐ ┌───────────────┐ ┌───────────────┐ │
│  │ Session  │ │ Agent     │ │ Tool Registry │ │ AgentRunner   │ │
│  │ Store    │ │ Graph     │ │ (builtin+mcp  │ │ (streaming,   │ │
│  │ (SQLite) │ │           │ │  +custom)     │ │  token track) │ │
│  └──────────┘ └───────────┘ └───────────────┘ └───────────────┘ │
│  ┌──────────┐ ┌───────────┐ ┌───────────────┐ ┌───────────────┐ │
│  │ Config   │ │ Permission│ │ Git Undo/Redo │ │ Shutdown      │ │
│  │ Loader   │ │ Middleware│ │ Middleware    │ │ Handler       │ │
│  │+Saver    │ │           │ │               │ │ (save+cleanup)│ │
│  └──────────┘ └───────────┘ └───────────────┘ └───────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                Memory Layer (MemPalace)                            │
│  ┌──────────┐ ┌───────────┐ ┌───────────────────────────────────┐ │
│  │ Semantic │ │ Knowledge │ │ Agent                              │ │
│  │ Search   │ │ Graph     │ │ Diaries                            │ │
│  └──────────┘ └───────────┘ └───────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                     Storage                                       │
│  ~/.config/pyharness/   — global config, agents,                  │
│                            skills, commands                       │
│  ~/.local/share/pyharness/ — sessions (SQLite), logs,             │
│                              cache, MemPalace index               │
│  ~/.local/share/pyharness/current — current session pointer       │
│  .pyharness/             — project-local overrides                │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 Application Lifecycle

```
┌─────────────────────────────────────────────────────┐
│ STARTUP                                             │
│ 1. load_config()          — pyharness.json          │
│ 2. load last model        — config.model            │
│ 3. open SessionStore      — sessions.db (WAL)       │
│ 4. read current_session   — ~/.local/.../current    │
│ 5a. if session exists     → load session            │
│ 5b. if no session exists  → create new session      │
│ 6. refresh model list     — for selected provider   │
│ 7. verify provider status — test connect / ping     │
├─────────────────────────────────────────────────────┤
│ RUNTIME                                             │
│ • track token usage (per message, per session)      │
│ • save on: provider connect, model switch           │
│ • SessionStore.add_message() on each exchange       │
├─────────────────────────────────────────────────────┤
│ SHUTDOWN                                            │
│ 1. save current session  → SessionStore             │
│ 2. save provider config  → save_config()            │
│ 3. save selected model   → save_config()            │
│ 4. write current_session → ~/.local/.../current     │
│ 5. close SQLite          → store.close()            │
│ 6. MemPalace diary write → (if enabled)             │
└─────────────────────────────────────────────────────┘
```

### Entrypoint

`pyharness` — starts the TUI. `pyharness run "prompt"` — single-shot CLI. `pyharness serve` — HTTP server.

---

## 3. Feature Matrix (OpenCode Parity + Memory)

| Feature | OpenCode | pyharness | Notes |
|---------|----------|-----------|-------|
| **TUI** | Ink/React + Node.js | Textual (Python) | Same UX, Python stack |
| **Multi-provider LLM** | AI SDK (75+) | LangChain models (50+) | Provider config in `pyharness.json` |
| **Agent system** | Build/Plan/General/Explore/Scout | Build/Plan/General/Explore | LangGraph-powered, configurable prompts |
| **Agent switching** | Tab key | Tab key | Cycle through primary agents |
| **@ file references** | Fuzzy file search | Same | Content injected into prompt |
| **! bash commands** | Prefix `!` | Same | Output rendered as tool result |
| **Session management** | /new, /sessions, /resume, /undo, /redo | Same | Git-backed snapshots |
| **MCP servers** | Local + Remote | Same | langchain-mcp-adapters + native mcp SDK |
| **Agent Skills** | SKILL.md discovery | Same | Progressive disclosure |
| **Custom commands** | /command templates | Same | Markdown frontmatter |
| **Plugins** | JS/TS hook system | LangGraph middleware | Plugin = GraphNode in agent graph |
| **Permissions** | allow/ask/deny | Same | Glob patterns, HITL intercept |
| **Formatters** | Auto-format after edits | Same | Pluggable registry |
| **Themes** | Theme JSON files | Textual CSS themes | tui.json |
| **Keybinds** | Customizable | Same | tui.json |
| **Compaction** | Auto/manual | LangGraph context management | /compact |
| **Web search** | Exa via MCP | Same | Configurable provider |
| **TUI side panels** | Sessions, file tree, tools | + Memory tab | 4-panel sidebar |
| **Image attachments** | Drag-drop, paste | Terminal image protocol | Kitty/iTerm2 |
| **Editor mode** | /editor | Same | $EDITOR |
| **Export** | /export Markdown | Same | Session export |
| **Share** | /share | /share | Optional |
| **LSP** | Experimental | Experimental | python-lsp-server |
| **🆕 Semantic memory** | ❌ | ✅ MemPalace | Cross-session recall |
| **🆕 Knowledge graph** | ❌ | ✅ MemPalace | Structured codebase facts |
| **🆕 Agent diaries** | ❌ | ✅ MemPalace | Per-agent learnings |
| **🆕 Session briefing** | ❌ | ✅ MemPalace | Wake-up context injection |
| **🆕 Memory search** | ❌ | ✅ /memory command | Search past conversations |

---

## 4. Configuration

### 4.1 Config locations (precedence order)

1. **Remote config** — `https://org.example.com/.well-known/pyharness` (optional)
2. **Global config** — `~/.config/pyharness/pyharness.json`
3. **Custom config** — `PYHARNESS_CONFIG` env var
4. **Project config** — `.pyharness/pyharness.json` (project root)
5. **Inline config** — `PYHARNESS_CONFIG_CONTENT` env var

### 4.2 Config schema

```jsonc
{
  "$schema": "https://pyharness.dev/config.json",
  "model": "anthropic:claude-sonnet-4-5",
  "small_model": "anthropic:claude-haiku-4-5",
  "autoupdate": true,

  "provider": {
    "anthropic": {
      "apiKey": "{env:ANTHROPIC_API_KEY}",
      "options": { "timeout": 600000 }
    },
    "openai": {
      "apiKey": "{env:OPENAI_API_KEY}"
    }
  },

  "permission": {
    "edit": "allow",
    "bash": {
      "*": "ask",
      "git *": "allow",
      "grep *": "allow",
      "pip install *": "ask"
    },
    "external_directory": "ask"
  },

  "agent": {
    "plan": {
      "mode": "primary",
      "model": "anthropic:claude-haiku-4-5",
      "permission": { "edit": "deny", "bash": "deny" }
    },
    "code-reviewer": {
      "description": "Reviews code for best practices and potential issues",
      "mode": "subagent",
      "prompt": "You are a code reviewer. Focus on security, performance, and maintainability.",
      "permission": { "edit": "deny" }
    }
  },

  "memory": {
    "enabled": true,
    "wing": "{project.name}",
    "auto_index": {
      "mode": "event_driven",
      "triggers": ["session.idle", "session.compacted", "session.end"]
    },
    "wake_up": {
      "context_injection": true,
      "max_results": 5,
      "include_kg": true,
      "include_diary": true
    },
    "agent_search": {
      "enabled": true,
      "max_results": 10
    }
  },

  "mcp": {
    "sentry": {
      "type": "remote",
      "url": "https://mcp.sentry.dev/mcp",
      "oauth": {}
    },
    "local-server": {
      "type": "local",
      "command": ["uv", "run", "my-mcp-server"]
    }
  },

  "command": {
    "test": {
      "template": "Run the full test suite with coverage",
      "description": "Run tests with coverage"
    }
  },

  "plugin": ["pyharness-helicone"],

  "compaction": {
    "auto": true,
    "reserved": 10000,
    "prune": false
  },

  "watcher": {
    "ignore": ["node_modules/**", "dist/**", ".git/**"]
  },

  "instructions": ["CONTRIBUTING.md", "docs/guidelines.md"]
}
```

### 4.3 TUI config (`tui.json`)

```jsonc
{
  "$schema": "https://pyharness.dev/tui.json",
  "theme": "tokyonight",
  "scroll_speed": 3,
  "scroll_acceleration": { "enabled": true },
  "diff_style": "auto",
  "mouse": true,
  "keybinds": {
    "leader": "ctrl+x",
    "command_list": "ctrl+p",
    "switch_agent": "tab",
    "cycle_sidebar": "shift+tab"
  },
  "attention": {
    "enabled": true,
    "notifications": true,
    "sound": true
  }
}
```

### 4.5 Config Write-Back

pyharness must write back configuration changes to disk so that provider
keys, model selections, and other user preferences survive restarts.

**`save_config()` function** (in `config/loader.py`):
- Parses the existing config file with **json5** to preserve comments
- Deep-merges the changes into the parsed dict
- Writes back to `~/.config/pyharness/pyharness.json` using path
  from the original load (respecting `PYHARNESS_CONFIG` env var)

**Save triggers:**

| Trigger | What is saved | Via |
|---------|---------------|-----|
| Provider connect | Provider API key | `save_config()` |
| Model switch (`/model`) | `config.model` | `save_config()` |
| Shutdown | Provider config + model + last session | `save_config()` |

**Last model selected**: The `model` field in `pyharness.json` (§4.2)
is the canonical store for the last-used model. It is read on startup
and written on every model switch and on shutdown.

### 4.6 Model Discovery — Live API, No Static Fallback

**Design principle**: Every model ID pyharness knows about comes from
the provider's own model-listing API at runtime. No static fallback.
No hardcoded model list. No `_VERIFY_MODELS`. The provider's API is
the single source of truth.

**Provider model APIs**:

| Provider | List Endpoint | Auth Header |
|----------|--------------|-------------|
| OpenAI | `GET https://api.openai.com/v1/models` | `Bearer $KEY` |
| Anthropic | `GET https://api.anthropic.com/v1/models` | `x-api-key: $KEY` + `anthropic-version: 2023-06-01` |
| DeepSeek | `GET https://api.deepseek.com/models` | `Bearer $KEY` |
| Google Gemini | `GET https://generativelanguage.googleapis.com/v1beta/models?key=$KEY` | `x-goog-api-key: $KEY` |
| Groq | `GET https://api.groq.com/openai/v1/models` | `Bearer $KEY` |
| Mistral | `GET https://api.mistral.ai/v1/models` | `Bearer $KEY` |
| Together | `GET https://api.together.ai/v1/models` | `Bearer $KEY` |
| xAI/Grok | `GET https://api.x.ai/v1/models` | `Bearer $KEY` |
| Perplexity | `GET https://api.perplexity.ai/v1/models` | NONE (no auth required) |
| OpenRouter | `GET https://openrouter.ai/api/v1/models` | NONE |
| Ollama | `GET localhost:11434/api/tags` | NONE |

All OpenAI-compatible providers (DeepSeek, Groq, Mistral, Together,
xAI) return the standard OpenAI model-list format:

```json
{"object": "list", "data": [{"id": "model-name", "created": 1234567890, "owned_by": "org"}]}
```

**Implementation**:

`fetch_models()` queries each connected provider's `/v1/models` (or
equivalent) endpoint. The base URL is resolved from the provider's
default or `provider_config.baseUrl` if overridden. For `ollama`, the
endpoint is `/api/tags`. For Google Gemini, the endpoint includes the
API key as a query parameter.

```python
async def fetch_models(config, providers: set[str] | None = None) -> list[ModelInfo]:
    """Query live model lists from every connected provider.

    Returns a flat list of ModelInfo with provider + model_id for
    each model advertised by each connected provider's own API.
    Providers whose listing fails are skipped with a log warning.
    """
    models = []
    for provider_id in (providers or config.connected_providers):
        try:
            provider_models = await _fetch_provider_models(provider_id, config)
            models.extend(provider_models)
        except ModelDiscoveryError as exc:
            logger.warning("model_discovery_failed", provider=provider_id, error=str(exc))
            # No fallback. Provider contributes zero models.
    return models
```

**Connected provider definition**: A provider is "connected" when:

1. **On startup** — the provider's `apiKey` in the config is:
   - A non-empty, non-placeholder string (e.g. `"sk-abc123"`), OR
   - An `{env:VAR}` placeholder whose referenced environment variable is set
2. **At runtime** — `/connect` succeeds and `verify_connection()` returns `True`

**Startup flow**:

1. `load_config()` loads `pyharness.json` with all provider entries
2. `_populate_connected_providers()` scans each provider's `apiKey`:
   - Real keys → added to `_connected_providers`
   - `{env:VAR}` placeholders → added only if `$VAR` is set
   - Empty keys → skipped
3. `refresh_models()` calls `fetch_models()` with `providers=self._connected_providers`
4. Every model ID that appears in `/models` came from a live API call in step 3

**Error handling**: If a provider's model listing fails (network
error, auth failure, 404), the error is logged with `structlog`,
the provider is marked as disconnected, and zero models are returned
for that provider. No fallback to a hardcoded list. No `_VERIFY_MODELS`.
The user sees a provider-specific error indicator in the TUI.

**Caching**: Model lists are cached for the duration of the session.
They are invalidated and re-fetched on `/connect` and on startup.

**No static model list**: pyharness has no `_STATIC_MODELS`, no
`_VERIFY_MODELS`, and no hardcoded model IDs anywhere. If no
connected providers return models (all listing calls fail), the model
list is empty and the user sees an appropriate prompt to connect a
provider.

### 4.7 Connection Verification via Model Discovery

**Design principle**: Model discovery IS connection verification.
There is no separate verifier model. No hardcoded test model. The act
of successfully querying a provider's model list proves:

1. The API key is valid
2. The network is reachable
3. The provider is operational

**Implementation**: `verify_connection()` calls the provider's model
listing endpoint. If the call returns a non-empty model list, the
connection is verified AND models are discovered in a single step.

```python
async def verify_connection(provider_id: str, config: Config) -> bool:
    """Verify provider connectivity by querying its model list.

    Succeeds if the model list endpoint returns a valid response
    with at least one model. Fails on network error, auth error,
    or empty/invalid response.
    """
    try:
        models = await _fetch_provider_models(provider_id, config)
        return len(models) > 0
    except ModelDiscoveryError:
        return False
```

**Benefits over the old `_VERIFY_MODELS` approach**:

| Old (`_VERIFY_MODELS`) | New (live discovery) |
|------------------------|---------------------|
| Hardcoded verifier model per provider | No hardcoded models anywhere |
| Two code paths: verification + discovery | Single unified path |
| Stale models (new provider models require code change) | Always up-to-date from provider API |
| Connection test wasted an inference call | Connection test is free (list endpoint) |

**Providers with no model list endpoint**: If a provider has no
model-listing API, it cannot be used with pyharness. This is
intentional — a provider without a discoverable model list has
no path into the system.

**Connected status lifecycle**: A provider is marked 🟢 connected ONLY
after a successful model-list fetch. On startup, ``refresh_models()``
iterates every provider with a non-empty key. Each provider that
responds successfully is added to ``_connected_providers``. Providers
that fail or have empty keys are excluded. The sidebar reflects this
status asynchronously after verification completes.

**Logging**: ``log_level`` defaults to ``"INFO"`` for diagnostic output
during development. Set to ``null`` in ``pyharness.json`` to disable.

---

## 5. Agent System

### 5.1 Architecture: LangGraph-powered

Agents are LangGraph `CompiledStateGraph` instances. Each agent has:
- A **system prompt** (from agent definition)
- A **model binding** (default or override)
- A **tool set** (filtered by permissions)
- **Middleware** for git undo/redo, memory indexing, permission checks
- A **memory agent tool** (`mempalace_search`) for cross-session recall

```python
from pyharness.core.agent import create_agent

agent = create_agent(
    definition=agent_def,          # from pyharness.json or .md
    tools=registry.get_for(agent),  # filtered by permissions
    model=provider.get_model(),    # LangChain chat model
    memory=mem_palace,             # MemPalace instance (optional)
    middlewares=[                  # pyharness custom middleware
        GitUndoMiddleware(),
        MemoryIndexMiddleware(),
        PermissionMiddleware(config),
    ],
)
```

### 5.2 Built-in agents

| Agent | Mode | Model | Permissions | Purpose |
|-------|------|-------|-------------|---------|
| **build** | primary | default model | full | Implementation & editing |
| **plan** | primary | small_model | read-only | Analysis & planning |
| **general** | subagent | inherit | full | Multi-step parallel tasks |
| **explore** | subagent | inherit | read-only | Codebase search |

### 5.3 Agent definition

Markdown frontmatter in `~/.config/pyharness/agents/` or `.pyharness/agents/`:

```markdown
---
description: Reviews code for quality and best practices
mode: subagent
model: anthropic:claude-sonnet-4-5
temperature: 0.1
steps: 10
permission:
  edit: deny
  bash: deny
---

You are in code review mode. Focus on:
- Code quality and best practices
- Potential bugs and edge cases
- Performance implications
```

### 5.4 Agent switching

- **Tab** — cycle through primary agents (build → plan → build)
- **@mention** — invoke a subagent: `@explore find the auth middleware`
- **Arrow keys** — navigate parent/child sessions

---

## 6. Memory System (MemPalace)

MemPalace is the differentiating feature — no other terminal coding agent has semantic memory.

### 6.1 Architecture

```
Agent Loop ──► Tool Call (mempalace_*) ──► MemPalace CLI/Python API
    │                                            │
    ├── session.start ──► wake-up() ──► context injected as system preamble
    ├── session.idle  ──► auto-index last exchange
    ├── compaction     ──► capture before discard
    ├── session.end   ──► diary write + full index
    └── user requests ──► /memory search ──► TUI displays results

MemPalace runs as:
  • Direct Python library (fast, internal) — `from mempalace import MemPalace`
  • MCP tools exposed to agent — `mempalace_search`, `mempalace_remember`, etc.
```

### 6.2 The Palace metaphor

- **Wing** = Project scope (`mike/pyharness`)
- **Room** = Topic (`sessions`, `decisions`, `architecture`)
- **Drawer** = Individual content unit (a message, a fact, a decision)
- **Knowledge Graph** = Structured facts (`AuthMiddleware` → `located_in` → `src/auth/middleware.py`)
- **Diary** = Per-agent learnings written at session boundaries

### 6.3 Wake-up protocol

On session start, pyharness:
1. Queries KG for facts about the project
2. Runs semantic search using the first user message as query
3. Loads agent diary entries
4. Composes a **session briefing** shown in-chat
5. Injects context as a system preamble

### 6.4 Agent memory tools

| Tool | Description |
|------|-------------|
| `mempalace_search` | Semantic search across project memory |
| `mempalace_remember` | Store a fact or decision |
| `mempalace_search_sessions` | Find past sessions by topic |
| `mempalace_diary_read` | Read agent learnings |
| `mempalace_kg_query` | Query the knowledge graph |
| `mempalace_kg_add` | Add a fact to the knowledge graph |

### 6.5 TUI Memory tab

The sidebar gains a 4th tab: **Memory** (🧠). Shows:
- Knowledge graph facts tree (expandable)
- Related past sessions (clickable to resume)
- Agent diary preview (last entry from each agent)
- Quick actions: `/mine`, `/forget`, memory health stats

### 6.6 Configuration

```jsonc
{
  "memory": {
    "enabled": true,           // Master toggle. Disabled → graceful SQLite-only fallback
    "wing": "{project.name}",  // Auto-detected from git remote or directory name
    "auto_index": {
      "mode": "event_driven",  // "event_driven" | "manual" | "realtime"
      "triggers": ["session.idle", "session.compacted", "session.end"]
    },
    "wake_up": {
      "context_injection": true,
      "max_results": 5,         // Max semantic search results to inject
      "include_kg": true,       // Include knowledge graph facts
      "include_diary": true     // Include agent diary entries
    },
    "agent_search": {
      "enabled": true,
      "max_results": 10
    }
  }
}
```

### 6.7 Graceful degradation

If `mempalace` is not installed:
- All `mempalace_*` tools return "MemPalace not installed. Install with: `pip install mempalace`"
- TUI Memory tab shows installation prompt
- All other features work normally (SQLite session storage continues)
- Zero startup delay, zero extra dependencies

### 6.8 MemPalace MCP server

When MemPalace is installed, its 35 MCP tools are automatically available to the agent as an MCP server named `mempalace`. This provides cross-wing navigation, drawer management, knowledge graph operations, tunneling between projects, and agent diaries without any extra configuration.

---

## 7. Session System

### 7.1 Session lifecycle

```
                    ┌──────────┐
            ┌──────►│  active  │◄──────────┐
            │       └────┬─────┘           │
            │            │                 │
    [New] ──┤            ▼                 │
            │       ┌─────────┐     ┌──────┴──────┐
            │       │  idle   │────►│  compacted  │
            │       └─────────┘     └──────┬──────┘
            │                              │
            │       ┌──────────────┐       │
            └──────►│  archived    │◄──────┘
                    └──────────────┘

  ┌──────────────────────────────────────────────────────────┐
  │ PERSISTENCE BOUNDARIES                                    │
  │                                                          │
  │  [New] → active    auto-create if no sessions exist      │
  │  active → idle     after 30s of inactivity (auto)        │
  │  idle → compacted  manual (/compact) or auto             │
  │  any → archived    manual archive                        │
  │  EXIT              save current session + token counts   │
  │  STARTUP           load last session from current ptr    │
  └──────────────────────────────────────────────────────────┘
```

Key persistence rules:
- **Auto-create on first run**: If `SessionStore.list_sessions()` returns empty, a new session `sess-{ulid}` is created automatically
- **Resume on restart**: The last active session ID is written to `~/.local/share/pyharness/current`. On startup, this is read and the session is loaded
- **Save on changes**: Every message exchange increments `session.total_tokens` and `message.token_count`. The session row is updated in SQLite after each turn
- **Save on exit**: See §7.5

### 7.2 Session storage

| Lifecycle layer | Location | What |
|----------------|----------|------|
| **Session DB** | `~/.local/share/pyharness/sessions/sessions.db` | All sessions: messages, token counts, metadata. libsql (Turso local/embedded) with MVCC concurrent writes |
| **Current pointer** | `~/.local/share/pyharness/current` | Single line: the active session ID |
| **LangGraph checkpoints** | In-memory (Phase 1) / SQLite (Phase 2+) | Agent graph state for resumption |
| **Cross-session** | MemPalace (optional) | Semantic index, knowledge graph, agent diaries |

SQLite schema (in `SessionStore`):
- `sessions` table: id, title, project, model, agent, provider, status, total_tokens, created_at, updated_at
- `messages` table: id, session_id, role, content, tool_name, tool_args, tool_result, timestamp, token_count

### 7.3 Token tracking

Token usage is tracked at two levels:

| Level | Field | Updated |
|-------|-------|---------|
| **Per-message** | `Message.token_count` | After each assistant response, from LangGraph `on_chat_model_stream` `usage_metadata` |
| **Per-session** | `Session.total_tokens` | Cumulative sum. Updated after each exchange in the session |

Token capture:
- `AgentRunner.run()` listens for `on_chat_model_stream` events
- When the stream ends, LangGraph emits an `on_chat_model_end` event with `usage_metadata` containing `{input_tokens, output_tokens, total_tokens}`
- The `AgentRunner` yields a `{"type": "usage", "data": {...}}` event
- The TUI layer accumulates into the active `Session` and calls `SessionStore.update_session()`

Token display:
- **Status bar**: `build | anthropic:claude-sonnet-4-5 | anthropic | 4,231 tokens`
- **Sidebar context**: Shows per-session token counts in the Sessions tab
- **Session browser**: Column showing total tokens per session

### 7.4 Session browser

The Sessions tab in the sidebar lists all sessions from `SessionStore.list_sessions()`:

```
┌─ Sessions ─────────────────────┐
│ ● Build REST API     12.4K tok │  ← active (●)
│ ○ Fix auth bug        3.2K tok │  ← idle
│ ○ Refactor config       842 tok│  ← idle
│ ○ Archived: old impl          │  ← archived (dimmed)
│                                │
│ [New] [Switch] [Archive]       │
└────────────────────────────────┘
```

Actions:
- **Switch**: Update `current` pointer, save current session, load selected session
- **Resume**: Same as switch — the session's message history is loaded into the chat
- **Archive**: Set `status = "archived"`, remove from active list
- **New**: Create with `SessionStore.create_session()`, write `current` pointer

### 7.5 Auto-create on startup

```python
async def ensure_session(store: SessionStore) -> str:
    """Return current session ID, creating one if none exists."""
    # Read current pointer
    current_path = _data_dir() / "current"
    if current_path.exists():
        session_id = current_path.read_text().strip()
        try:
            await store.get_session(session_id)
            return session_id
        except SessionNotFoundError:
            pass  # Stale pointer — fall through

    # No sessions at all → create
    sessions = await store.list_sessions()
    if not sessions:
        session = await store.create_session(title="New Session")
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(session.id)
        return session.id

    # Sessions exist but no pointer → use most recent
    latest = sessions[0]  # ordered by updated_at DESC
    current_path.write_text(latest.id)
    return latest.id
```

### 7.6 Session persistence on exit (§7.5)

On shutdown (whether `action_quit`, `KeyboardInterrupt`, or SIGTERM):

1. **Save current session**: `SessionStore.update_session(session)` writes final `total_tokens`, `updated_at`, `status = "idle"`
2. **Save provider config**: `save_config()` writes provider API keys to `pyharness.json`
3. **Save selected model**: `save_config()` writes `model` field to `pyharness.json`
4. **Write current pointer**: `~/.local/share/pyharness/current` ← session ID
5. **Close SessionStore**: `await store.close()` closes the SQLite connection
6. **MemPalace diary**: If enabled, write agent diary entry for the session

The shutdown flow is implemented as the `on_unmount` handler in the Textual `App`
and as a signal handler for SIGINT/SIGTERM.

### 7.7 Git-backed undo/redo

Every agent action that modifies files creates a git commit on a hidden branch (`pyharness-session-{id}`). This is implemented as LangGraph middleware that intercepts file-modifying tool calls:

- **Requires clean working tree** on session start (user changes auto-stashed with warning)
- **Commit on each file-modifying tool call**; commit message includes tool name and summary
- **Journal file** maps commit SHAs to tool calls for precise undo/redo
- **Non-git fallback**: when not in a git repo, uses file backup copies in `~/.local/share/pyharness/backups/`

### 7.8 Compaction

LangGraph provides context management middleware. Pyharness adds:
- Auto-compaction when context approaches model limit
- Manual compaction via `/compact`
- Pre-compaction MemPalace capture (index before summary loss)
- Configurable `reserved` token buffer

---

## 8. Tools

### 8.1 Built-in tools

| Tool | Description | Permission key |
|------|-------------|----------------|
| `bash` | Execute shell commands (sandboxed) | `bash` |
| `read` | Read file contents | `read` |
| `write` | Create/overwrite files | `edit` |
| `edit` | Exact string replacement | `edit` |
| `grep` | Search file contents (regex) | `grep` |
| `glob` | Find files by pattern | `glob` |
| `task` | Launch subagent (LangGraph subgraph) | `task` |
| `todowrite` | Manage task lists | `todowrite` |
| `webfetch` | Fetch web content | `webfetch` |
| `websearch` | Web search | `websearch` |
| `question` | Ask user questions | `question` |
| `skill` | Load a SKILL.md file | `skill` |
| `mempalace_*` | Memory tools (see §6.4) | `memory` |

### 8.2 Tool implementation

Tools are LangChain `@tool` decorated functions. MCP tools are loaded via `langchain-mcp-adapters`. The full tool set is composed at agent creation:

```python
tools = (
    builtin_tools() +
    mcp_tools_from_config(config.mcp) +
    mempalace_tools(config.memory) +
    custom_tools_from_plugins()
)
```

### 8.3 Permission enforcement

A LangGraph middleware node intercepts every tool call:
1. Check `permission` config (agent-level overrides global)
2. Glob match on tool name and arguments
3. If `"ask"`: emit HITL interrupt → TUI shows inline permission prompt
4. If `"deny"`: block with error message
5. If `"allow"`: proceed immediately

---

## 9. MCP Server Support

### 9.1 Configuration

```jsonc
{
  "mcp": {
    "my-local-server": {
      "type": "local",
      "command": ["uv", "run", "my-mcp-server"],
      "environment": { "MY_VAR": "value" },
      "timeout": 5000,
      "enabled": true
    },
    "my-remote-server": {
      "type": "remote",
      "url": "https://mcp.example.com/mcp",
      "headers": { "Authorization": "Bearer {env:MCP_TOKEN}" },
      "oauth": {},
      "enabled": true
    }
  }
}
```

### 9.2 Tool naming

MCP tools are namespaced: `{server_name}__{tool_name}`. MemPalace is auto-registered as `mempalace__*` when the package is installed.

---

## 10. Provider Bridge — Maximum Coverage

pyharness uses a **three-layer provider strategy** to cover every LLM provider a developer might use.

### 10.1 Coverage Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: LiteLLM Gateway (optional, self-hosted)                 │
│ For enterprise: cost tracking, rate limits, virtual keys,        │
│ multi-tenant routing. Via langchain-litellm.                     │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: OpenRouter (single API key, 200+ models)                │
│ Via langchain-openrouter. Covers: Replicate, DeepInfra, Together,│
│ Fireworks, Perplexity, xAI, Cohere, and 50+ more.               │
│ ALL coverage gaps are eliminated by this single package.         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: First-Party LangChain Packages (18 bundled)             │
│ Direct API access. Best latency, full feature support.           │
│ OpenAI, Anthropic, Google, Mistral, Groq, AWS Bedrock,          │
│ HuggingFace, Ollama, DeepSeek, Cerebras, xAI, Together, etc.    │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Layer 1 — First-Party Packages (bundled)

Installed by default. Cover 90%+ of actual developer usage:

| Package | Provider(s) | Model Class |
|---------|------------|-------------|
| `langchain-openai` | OpenAI + any OpenAI-compatible endpoint | `ChatOpenAI` |
| `langchain-anthropic` | Anthropic (Claude) | `ChatAnthropic` |
| `langchain-google-genai` | Google Gemini (AI Studio) | `ChatGoogleGenerativeAI` |
| `langchain-google-vertexai` | Google Vertex AI | `ChatVertexAI` |
| `langchain-mistralai` | Mistral AI | `ChatMistralAI` |
| `langchain-groq` | Groq (ultra-fast) | `ChatGroq` |
| `langchain-aws` | AWS Bedrock (Claude, Llama, Nova) | `ChatBedrock` |
| `langchain-fireworks` | Fireworks AI | `ChatFireworks` |
| `langchain-huggingface` | Hugging Face Hub + TGI | `ChatHuggingFace` |
| `langchain-ollama` | Ollama (local: Llama, Gemma, Mistral) | `ChatOllama` |
| `langchain-deepseek` | DeepSeek | `ChatDeepSeek` |
| `langchain-xai` | xAI (Grok) | `ChatXAI` |
| `langchain-together` | Together AI | `ChatTogether` |
| `langchain-perplexity` | Perplexity AI | `ChatPerplexity` |
| `langchain-cerebras` | Cerebras | `ChatCerebras` |
| `langchain-nvidia-ai-endpoints` | Nvidia NIM | `ChatNVIDIA` |
| `langchain-ibm` | IBM watsonx | `ChatWatsonx` |
| `langchain-cohere` | Cohere | `ChatCohere` |

### 10.3 Layer 2 — OpenRouter (the silver bullet)

`langchain-openrouter` provides **200+ models from 50+ providers** through one API. This single package eliminates ALL practical coverage gaps:

```python
from langchain_openrouter import ChatOpenRouter

model = ChatOpenRouter(model="anthropic/claude-sonnet-4-5")
# Or: "openai/gpt-5", "google/gemini-3-pro",
#     "meta/llama-4-maverick", "deepseek/deepseek-v3",
#     "replicate/meta/llama-4", "nousresearch/hermes-3"
```

Providers accessible via OpenRouter that LangChain misses natively: Replicate, DeepInfra, Anyscale, ZhipuAI (GLM), Moonshot AI, MiniMax, Lambda AI, Novita AI, and dozens more.

### 10.4 Layer 3 — LiteLLM Gateway (optional, self-hosted)

For enterprises needing operational controls:

```python
from langchain_litellm import ChatLiteLLMRouter

# Users point pyharness at their own LiteLLM proxy:
# - Rate limiting per team/user
# - Cost tracking per session
# - Virtual API keys
# - Automatic fallback routing
# - Budget alerts
```

Not bundled. Users install `langchain-litellm` themselves if needed.

### 10.5 Provider Configuration

```jsonc
{
  "provider": {
    // Layer 1: Direct API keys
    "anthropic": { "apiKey": "{env:ANTHROPIC_API_KEY}" },
    "openai": { "apiKey": "{env:OPENAI_API_KEY}" },
    "google-genai": { "apiKey": "{env:GOOGLE_API_KEY}" },

    // Layer 2: Single OpenRouter key covers everything else
    "openrouter": { "apiKey": "{env:OPENROUTER_API_KEY}" },

    // Layer 3: Self-hosted LiteLLM proxy (advanced)
    "litellm": { "apiKey": "sk-proxy-key", "baseUrl": "http://localhost:4000" }
  },
  "model": "anthropic:claude-sonnet-4-5",
  "small_model": "anthropic:claude-haiku-4-5"
}
```

### 10.6 Provider Resolution

The `provider:model-id` string is resolved at runtime:
1. First-party LangChain package → native `ChatModel` (fastest)
2. `openrouter:` prefix → `ChatOpenRouter` (covers everything else)
3. `litellm:` prefix → `ChatLiteLLMRouter` (enterprise gateway)
4. `ollama:` prefix → `ChatOllama` (local models)

Any model string works: `"openrouter:replicate/meta/llama-4"` requires zero additional packages.

---

## 11. Agent Skills

Skills follow the OpenCode/Agent Skills specification exactly.

### 10.1 File format

```markdown
---
name: git-release
description: Create consistent releases and changelogs
license: MIT
---

## What I do
- Draft release notes from merged PRs
- Propose a version bump
- Provide a copy-pasteable `gh release create` command
```

### 10.2 Discovery locations

- `.pyharness/skills/<name>/SKILL.md`
- `~/.config/pyharness/skills/<name>/SKILL.md`
- `.claude/skills/<name>/SKILL.md` (Claude-compatible)
- `~/.agents/skills/<name>/SKILL.md` (Agent Skills-compatible)
- `~/.codex/skills/<name>/SKILL.md` (Codex-compatible)

---

## 12. Custom Commands & Plugin System

### 12.1 Custom commands

Markdown files in `.pyharness/commands/` or `~/.config/pyharness/commands/`:

```markdown
---
description: Run tests with coverage
agent: build
model: anthropic:claude-haiku-4-5
---

Run the full test suite with coverage report.
```

Special syntax: `$ARGUMENTS`, `$1`/`$2`, `` !`command` ``, `@filename`.

### 12.2 Plugin system (LangGraph middleware)

Plugins are Python packages that export LangGraph-compatible middleware. No custom plugin DSL needed:

```python
# .pyharness/plugins/memory_indexer.py
from pyharness.plugin import MiddlewarePlugin

class MemoryIndexer(MiddlewarePlugin):
    """Index tool outputs into MemPalace after execution."""

    async def after_tool_call(self, ctx, tool_name, args, result):
        if ctx.memory:
            await ctx.memory.index(
                content=f"Tool: {tool_name}\nArgs: {args}\nResult: {result}",
                room="tool_outputs"
            )
        return result
```

**Hook events** map to LangGraph's built-in interrupt/checkpoint system:
- `tool.execute.before` → `before_model` node
- `tool.execute.after` → `after_tool_call` callback
- `session.*` → LangGraph checkpoint events
- `permission.*` → HITL interrupt handling
- `shell.env` → environment injection

---

## 13. TUI Layout (Textual)

### 13.1 Layout zones

```
┌─ Header ───────────────────────────────────────────────┐
│ Session title    [model:provider] [agent] [tokens] [🧠]│
├─ Main ───────────────────────┬─ Side Panel ────────────┤
│                              │ ┌─ Sessions ───────────┐ │
│  ┌─ Chat Area ─────────────┐ │ │ • sess 1             │ │
│  │ [🧠 Session Briefing]   │ │ │ • sess 2 (has memory)│ │
│  │  ├ 3 related sessions   │ │ │ • sess 3             │ │
│  │  ├ 12 KG facts loaded   │ │ └──────────────────────┘ │
│  │  └ Last: "refactor auth"│ │ ┌─ File Tree ──────────┐ │
│  │                          │ │ │ src/                 │ │
│  │  [User] message          │ │ │  __init__.py         │ │
│  │  [Assistant] response    │ │ └──────────────────────┘ │
│  │  ┌ tool: bash ─────────┐ │ │ ┌─ Memory 🧠 ─────────┐ │
│  │  │ > pytest tests/      │ │ │ │ 📍 src/auth/        │ │
│  │  │ ... output ...       │ │ │ │ 🔗 "use JWT"        │ │
│  │  └──────────────────────┘ │ │ │ 📝 diary: plan agent │ │
│  │                          │ │ └──────────────────────┘ │
│  └──────────────────────────┘ │                          │
├─ Input ─────────────────────────────────────────────────┤
│ > Prompt text here...                                   │
├─ Status Bar ────────────────────────────────────────────┤
│ [Build] [🧠 12 facts]  ctrl+p  ctrl+x  /slash           │
└─────────────────────────────────────────────────────────┘
```

### 13.2 Side panel tabs

| Tab | Key | Content |
|-----|-----|---------|
| **Sessions** | F1 / Ctrl+1 | Active, child, archived sessions |
| **File Tree** | F2 / Ctrl+2 | Project file browser |
| **Tools** | F3 / Ctrl+3 | Available tools, MCP status |
| **Memory** | F4 / Ctrl+4 | KG facts, related sessions, diary |

### 13.3 Keybinds

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Tab` | Switch agent |
| `Shift+Tab` | Cycle side panel tab |
| `j`/`k` | Scroll chat (vim) |
| `gg`/`G` | Top/bottom of chat |
| `Ctrl+p` | Command palette |
| `Ctrl+x c` | Compact session |
| `Ctrl+x e` | Editor mode |
| `Ctrl+x l` | Session list |
| `Ctrl+x m` | Model list |
| `Ctrl+x n` | New session |
| `Ctrl+x q` | Exit |
| `Ctrl+x r` | Redo |
| `Ctrl+x t` | Theme list |
| `Ctrl+x u` | Undo |
| `Ctrl+[/]` | Navigate sessions |
| `Up/Down` | Navigate input history (bash-like) |
| `Ctrl+R` | Search input history |
| `Ctrl+Shift+C` | Copy selected output text |

### 13.4 Input History (bash-like)

The input widget maintains a command history like bash/readline.

**History storage**: In-memory list per session, persisted to the `sessions.db` SQLite store so history survives restarts. Maximum 1000 entries per session.

**Navigation**:
- **Up Arrow** (`key_up`): When at the end of input, replaces the input buffer with the previous history entry. When already mid-history, moves one entry further back.
- **Down Arrow** (`key_down`): When in history, moves one entry forward. When at the last history entry, restores the original (empty or unsent) input.
- **Enter** (submit): Clears the "original input" save and appends the submitted text to history.

**Search (Ctrl+R)**:
- Pressing `Ctrl+R` opens a search overlay (modal or inline, like bash's `(reverse-i-search)`) above or replacing the input.
- Typing filters the history entries by substring match (case-insensitive).
- `Ctrl+R` again cycles to the next matching entry.
- `Enter` selects the current match and fills it into the input.
- `Escape` or `Ctrl+G` cancels the search and restores original input.

**Persistence**:
- Each submitted input is written to `sessions.db` immediately.
- On session load, the history is populated from the database.
- History is scoped to the current session ID.

### 13.5 Output Formatting & Copy

The chat output area renders responses with full Rich markup formatting.

**Implementation**: Uses Textual's `RichLog` widget which natively supports:
- Rich markup (colors, bold, italic, code blocks via `rich.markdown.Markdown`)
- Auto-scroll on new messages
- Virtualized scrolling for performance

**Markdown rendering**: Model responses are accumulated as tokens, then the complete response is rendered through `rich.markdown.Markdown` → Rich markup string → `RichLog.write()`. This gives full markdown support:
- `` ``` `` code blocks in a distinct background
- `**bold**` and `*italic*` text
- Bullet lists and numbered lists
- Headers with proper sizing
- Inline code with backtick styling

**Copy support**: `Ctrl+Shift+C` extracts all chat text from RichLog as plain text and copies it to the system clipboard via `pyperclip`.

**Keybinds**:
| Key | Action |
|-----|--------|
| `Ctrl+Shift+C` | Copy entire chat content to clipboard |
| `j`/`k` | Scroll chat (vim) |
| `gg`/`G` | Top/bottom of chat |
### 14.4 Status Bar

The bottom-docked status bar provides persistent session context:

**Format**: `{agent} | {model} | {provider} | {tokens}`

Examples:
```
build | anthropic:claude-sonnet-4-5 | anthropic | 4,231 tokens
plan  | openai:gpt-5               | openai    | 12,820 tokens
build |                             |           | 0 tokens
```

**Rules**:
- **agent**: Name of the current primary agent (build, plan, general, explore). Always present.
- **model**: The full `provider:model-id` string. Blank if no model selected.
- **provider**: Short provider name (anthropic, openai, groq, etc.). Blank if no model selected.
- **tokens**: Formatted integer with commas (e.g., `4,231 tokens`). Starts at `0 tokens`. Updated in real time by capturing `usage_metadata` from LangGraph streaming events.

**Token capture mechanism**:

`AgentRunner.run()` streams LangGraph events via `astream_events`. LangChain's `on_chat_model_stream` events include `usage_metadata` on the final chunk:

```python
async for event in graph.astream_events(state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            yield {
                "type": "usage",
                "data": {
                    "input_tokens": chunk.usage_metadata.get("input_tokens", 0),
                    "output_tokens": chunk.usage_metadata.get("output_tokens", 0),
                    "total_tokens": chunk.usage_metadata.get("total_tokens", 0),
                }
            }
```

The TUI accumulates token counts into the active `Session` object and calls `SessionStore.update_session()`.
The `StatusBar` widget listens for `TokenUpdate` messages and updates the display.

**StatusBar widget** (`src/pyharness/tui/widgets/status.py`):

```python
class StatusBar(Static):
    """Reactive status bar updated via Textual messages."""

    def on_mount(self) -> None:
        self.agent_name = "build"
        self.model_name = ""
        self.provider_name = ""
        self.total_tokens = 0

    def update_status(self) -> None:
        model = self.model_name or ""
        provider = self.provider_name or ""
        tokens = f"{self.total_tokens:,} tokens" if self.total_tokens else "0 tokens"
        self.update(f"{self.agent_name} | {model} | {provider} | {tokens}")
```

**Sidebar context section**: The sidebar's context area (top of side panel) also displays token counts alongside session title, model, and project info.

---

## 14. Implementation Phases (Revised)

### Phase 1 — Foundation (Weeks 1-6)
**Goal**: Working TUI chat with LangGraph agent, tools, persistence, and memory

- Project scaffolding (uv, pyproject.toml, CI/CD, linting)
- Config loading & validation (pydantic, JSON5)
- **Config write-back**: `save_config()` with JSONC comment preservation
- LangGraph agent runtime (build agent, ReAct loop)
- LangChain model integration (Anthropic + OpenAI)
- **Live model discovery**: `fetch_models()` queries every connected
  provider's model-listing API at runtime. Every model ID comes from
  the provider's own `/v1/models` endpoint. No static fallback, no
  `_VERIFY_MODELS`, no hardcoded model IDs. Connection verification
  uses the model list endpoint directly (§4.6, §4.7)
- Tool registry: bash, read, write, edit, grep, glob, task, todowrite
- Basic TUI (chat input/output, no side panels)
- **libsql session storage** (Turso local/embedded, concurrent writes via MVCC, schema + migrations)
- **Session persistence**: auto-create, load/restore, shutdown save
- **Current session pointer**: `~/.local/share/pyharness/current`
- **Token tracking**: capture usage_metadata from LangGraph streams
- **Status bar**: `{agent} | {model} | {provider} | {tokens}` format
- **Provider persistence**: save API keys on connect/shutdown, load on startup
- **Model persistence**: save last model to config, load on startup
- MemPalace integration (auto-index, wake-up, agent tools, graceful degradation)
- Permission middleware (HITL interrupts → TUI inline prompts)
- Structured logging (structlog)
- Mock LLM provider for testing

### Phase 2 — Full Agent System (Weeks 7-10)
**Goal**: Multi-agent support, undo/redo, session browser, side panels

- Plan agent (read-only, LangGraph subgraph)
- General subagent (task tool → isolated context)
- Explore subagent (read-only search)
- @ file references & autocomplete
- ! bash command injection
- Git-backed undo/redo middleware
- Side panels (Sessions, File Tree, Tools tabs)
- **Session browser**: list, switch, resume, archive sessions
- Command palette (Ctrl+p)
- Slash commands system
- MemPalace Memory tab in sidebar
- Session briefing UX on startup

### Phase 3 — MCP, Skills & Memory UX (Weeks 11-14)
**Goal**: MCP ecosystem, skills, polished memory experience

- MCP client (langchain-mcp-adapters + native SDK)
- MCP server registry & management UI
- Agent Skills (SKILL.md discovery & loading)
- Custom commands system
- /init workflow (AGENTS.md generation)
- Web search & web fetch
- Memory search UX (`/memory` command, inline citations)
- Knowledge graph visualization (sidebar tree view)
- Session browser with memory badges
- Theme system (Textual CSS themes)
- Keybind customization

### Phase 4 — Advanced & Polish (Weeks 15-18)
**Goal**: Production readiness, plugins, ecosystem

- LangGraph middleware plugin system
- Plugin discovery (local + pip entry points)
- Custom tool registration
- Plugin examples (notifications, env protection)
- LSP integration (python-lsp-server)
- Image attachment support
- Session sharing (/share)
- Editor mode (/editor)
- Server mode (pyharness serve)
- Remote config (.well-known/pyharness)
- GitHub/GitLab integration
- Performance optimization (virtualized scrolling, lazy loading)

### Deferred (Post-v1.0)
- Multi-project workspaces
- Native Anthropic/OpenAI adapters for features LangChain misses
- Advanced reasoning visibility (chain-of-thought in TUI)
- Cross-platform terminal image protocol fallbacks
- Plugin marketplace

---

## 15. Directory Structure (Revised)

```
pyharness/
├── pyproject.toml
├── src/
│   └── pyharness/
│       ├── __init__.py
│       ├── main.py              # Entrypoint (TUI, CLI, serve)
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py        # Config discovery & merge
│       │   └── schema.py        # Pydantic models (pyharness.json + tui.json)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── agent.py         # create_agent(), LangGraph graph builder
│       │   ├── session.py       # Session lifecycle, SQLite store, LangGraph checkpointer
│       │   ├── compaction.py    # Context compaction strategy
│       │   └── memory.py        # MemPalace integration (wake-up, index, search)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py      # Tool composition (builtin + MCP + memory + custom)
│       │   ├── builtin/         # bash, file_ops, search, web, question, skill, task
│       │   ├── memory_tools.py  # mempalace_search, remember, kg_query, kg_add
│       │   └── mcp_loader.py    # langchain-mcp-adapters integration
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── git_undo.py      # Git snapshot on file-modifying tool calls
│       │   ├── permission.py    # HITL interrupt for permission checks
│       │   └── memory_index.py  # Auto-index tool outputs into MemPalace
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py           # Textual App
│       │   ├── screens/
│       │   │   ├── chat.py      # Main chat screen
│       │   │   └── sessions.py  # Session browser
│       │   ├── widgets/
│       │   │   ├── input.py     # Prompt input with autocomplete
│       │   │   ├── message.py   # Chat message (streaming, tool calls, citations)
│       │   │   ├── sidebar.py   # 4-tab side panel container
│       │   │   ├── memory.py    # Memory tab (KG tree, related sessions, diary)
│       │   │   ├── file_tree.py # Project file browser
│       │   │   ├── status.py    # Status bar (agent, model, tokens, memory indicator)
│       │   │   └── briefing.py  # Session briefing widget
│       │   └── themes/
│       ├── plugins/
│       │   ├── __init__.py
│       │   └── loader.py        # Plugin discovery (local + entry points)
│       ├── skills/
│       │   ├── __init__.py
│       │   └── loader.py        # SKILL.md discovery
│       └── commands/
│           ├── __init__.py
│           └── loader.py        # Command file discovery
├── tests/
│   ├── conftest.py              # Fixtures: mock LLM, temp SQLite, temp git repo
│   ├── test_config/
│   ├── test_core/
│   ├── test_tools/
│   ├── test_middleware/
│   ├── test_tui/                # Textual snapshot tests
│   └── test_memory/
└── docs/
    ├── mockups/                 # SVG mockups
    ├── ux-review.md
    ├── strategic-analysis.md
    ├── mempalace-integration-design.md
    └── deepagents-integration-analysis.md
```

---

## 16. Key Design Decisions (Revised)

### 15.1 Why LangGraph over custom agent loop?
LangGraph provides durable execution with checkpointing, streaming, sub-graph isolation, and HITL interrupts — all features we would otherwise spend 15+ engineering weeks building from scratch. Its middleware model maps cleanly to pyharness's plugin architecture. The LangChain ecosystem provides 50+ model providers without needing litellm.

### 15.2 Why NOT DeepAgents?
DeepAgents (LangChain's "batteries-included agent harness") was rejected because LangChain also ships `deepagents-code` — a competing terminal coding agent. Building on a competitor's runtime is strategically unsound. LangGraph at the lower abstraction level gives us the infrastructure without the competitive entanglement.

### 15.3 Why MemPalace as built-in (not plugin)?
Memory is not an optional feature — it's the primary differentiator. Every session needs wake-up context. Every tool call should be indexed. The TUI needs a Memory tab. Making it a plugin would mean the killer feature is opt-in. Built-in with graceful degradation is the right pattern.

### 15.4 Why Textual over Rich Live / prompt_toolkit / urwid?
Textual is the only Python TUI framework with CSS-like layout, a widget toolkit, reactive data binding, and built-in support for multi-panel layouts out of the box.

### 15.5 Why SQLite for session storage?
SQLite is embedded, zero-config, durable. Sessions have structured data that benefits from indexed queries. WAL mode enables concurrent reads. LangGraph checkpoints provide agent state persistence separately.

### 15.6 Why Python 3.12+?
PEP 695 type parameters, improved error messages, faster startup. Textual 2.x requires 3.10+; 3.12 gives clean generics.

---

## 17. Open Questions / Risks

1. **LangGraph dependency weight**: LangGraph + langchain-core + langchain-openai/anthropic add ~12 packages. Mitigation: acceptable for the functionality gained. Track startup time in benchmarks.

2. **MemPalace disk usage**: ChromaDB + embedding model = ~150MB on first install. Mitigation: optional dependency; graceful degradation when absent.

3. **Textual performance**: Large chat histories may degrade TUI. Mitigation: virtualized scrolling, compaction for display, lazy loading.

4. **LangGraph API stability**: LangGraph is pre-1.0. Mitigation: pin versions, test upgrades thoroughly, maintain abstraction layer.

5. **MCP Python SDK maturity**: Python MCP SDK is newer than TypeScript. Mitigation: test against common MCP servers; fall back to subprocess invocation if needed.

6. **Git undo/redo edge cases**: Dirty working trees, merge conflicts, non-git directories. Mitigation: require clean tree, stash with warning, file-backup fallback.

7. **Permission UX in TUI**: Modal permission dialogs are wrong for terminals. Mitigation: inline permission prompts that expand the chat frame (OpenCode-style).

8. **Streaming architecture**: Textual's reactive system isn't streaming-optimized. Mitigation: `asyncio.Queue` between provider stream and TUI render; Textual `Message.update()` for incremental display.

9. **DeepAgents Code competitive risk**: LangChain may add TUI capabilities to deepagents-code. Mitigation: memory-first positioning is defensible; MemPalace integration is harder to replicate than TUI polish.
