# DeepAgents Integration Analysis for pyharness

> July 14, 2026 | Technical Architecture Decision

---

## Executive Summary

**Recommendation: Adopt DeepAgents as pyharness' agent runtime layer. Replace the custom "Core Engine" (§2) with DeepAgents. This reduces pyharness's required code by ~60%, accelerates time-to-MVP from 12 weeks to ~6 weeks, and gives us production-grade sub-agents, HITL, compaction, filesystem tools, MCP integration, and LangSmith tracing for free.**

The key tradeoff: we accept the LangChain/LangGraph dependency chain (~12 packages) in exchange for not building and maintaining ~15,000 lines of agent runtime code. Given that DeepAgents is MIT-licensed, has 26K+ stars, and is actively maintained by LangChain (a funded company with 50+ engineers), this is the correct "buy" decision for a small-team/solo project.

---

## 1. Build vs Buy Analysis

### 1.1 What DeepAgents provides that pyharness would otherwise need to build

| Capability | Build Cost (weeks) | DeepAgents Provides | Quality Assessment |
|-----------|-------------------|-------------------|-------------------|
| **Agent loop** (ReAct pattern) | 2-3 | LangChain's `create_agent()` with configurable middleware | Production-grade; tested across 100+ model providers |
| **Sub-agents** (task tool) | 4-6 | `SubAgentMiddleware` with isolated context, structured output | Built-in general-purpose subagent; any LangGraph graph can be a subagent |
| **Filesystem tools** (read/write/edit/grep/glob) | 2-3 | `FilesystemMiddleware` with pluggable backends | Built-in; supports permissions at path level |
| **Todo list** (task tracking) | 1 | `TodoListMiddleware` | Built-in |
| **Context compaction** (summarization) | 3-4 | `SummarizationMiddleware` | Built-in; auto/manual, configurable token thresholds |
| **Human-in-the-loop** (approve/deny/edit) | 3-4 | `HumanInTheLoopMiddleware` via `interrupt_on` | Interrupts at tool level; supports approve/reject/edit; integrates with LangGraph checkpoints |
| **Persistent memory** (cross-session recall) | 2-3 | `MemoryMiddleware` + LangGraph `store` | Pluggable backends; AGENTS.md-style memory |
| **Shell execution** | 1-2 | `execute` tool via `SandboxBackendProtocol` | Built-in; sandboxed execution |
| **MCP client** | 3-4 | `langchain-mcp-adapters` + `MultiServerMCPClient` | Native; stdio + HTTP transports |
| **Skills** (SKILL.md on-demand loading) | 2-3 | `SkillsMiddleware` | Built-in; progressive disclosure via filesystem backend |
| **Structured output** | 1-2 | `response_format` parameter | Auto-strategy; picks best method per provider |
| **Streaming** | 1-2 | LangGraph streaming modes | Built-in; token-level, message-level, custom |
| **Tracing/observability** | 2-3 | LangSmith integration | Production-grade; traces, evals, monitoring |
| **Error recovery** (patch tool calls) | 1-2 | `PatchToolCallsMiddleware` | Auto-repairs dangling tool calls |
| **Model flexibility** | 1 | `provider:model` string format | 50+ providers via LangChain integrations |
| **Checkpointing** | 1-2 | LangGraph `MemorySaver` + pluggable `Checkpointer` | Built-in; thread-scoped state with DeltaChannel reducer |
| **Async sub-agents** | 3-4 | `AsyncSubAgentMiddleware` | Background tasks on remote Agent Protocol servers |
| **Prompt caching** | 1-2 | `AnthropicPromptCachingMiddleware` | Auto-applied on Anthropic models |

**Total build cost saved: ~35-50 engineering weeks** (assuming a single developer). At current rates, this represents $35K-$50K in opportunity cost.

### 1.2 What pyharness needs that DeepAgents does NOT provide

| pyharness Requirement | DeepAgents Gap | Impact | Mitigation |
|----------------------|----------------|--------|------------|
| **Textual TUI** | DeepAgents is headless (no UI) | Critical | This is always pyharness's job. DeepAgents provides the agent runtime; pyharness provides the TUI. Clean separation. |
| **Permission UI dialogs** (allow/ask/deny with interactive prompts) | HITL interrupts but has no TUI rendering | High | pyharness hooks into LangGraph interrupts to render TUI permission dialogs. DeepAgents' `interrupt_on` mechanism IS the integration point. |
| **Git-backed undo/redo** | No git integration | Medium | pyharness implements this as a middleware that captures pre/post state. Can plug into DeepAgents' middleware stack. |
| **`@` file references** (fuzzy search + inject) | No fuzzy file search | Medium | pyharness implements this as a pre-processing step before invoking the agent. The result is injected into tool calls or system prompt. |
| **`!` bash injection** (prefix with `!`) | Shell access exists but no prefix convention | Low | pyharness pre-processes `!command` → injects as tool call or system prompt prefix. Trivial to implement. |
| **Session management UI** (/new, /resume, /sessions) | LangGraph has thread-based sessions but no UI | Medium | pyharness maps LangGraph thread IDs → pyharness sessions. Session list/tree is TUI-only concern. |
| **Provider config** (pyharness.json schema) | LangChain has its own model config pattern | Low | pyharness's config loader maps `pyharness.json` → LangChain model init. One-time mapping layer. |
| **Plugin system** (Python entry points) | DeepAgents uses middleware for extension | Low | pyharness's plugin system maps to DeepAgents middleware. Middleware IS the plugin API. |
| **Agent definitions** (Markdown frontmatter) | Subagents use TypedDict specs | Low | pyharness's agent loader parses Markdown → `SubAgent` TypedDict. Trivial conversion. |
| **Skill discovery** (SKILL.md in multiple locations) | SkillsMiddleware uses directory sources | Low | pyharness discovers skills from config paths → passes them as `skills=` sources. |
| **Custom commands** (slash commands) | No command concept | Low | pyharness maps command templates → pre-built `SubAgent` specs. |
| **Theme system** (Textual CSS) | N/A | None | Pure TUI concern. |
| **Keybinds** | N/A | None | Pure TUI concern. |
| **Editor mode** (/editor) | No editor concept | Low | pyharness opens $EDITOR, captures output, injects as user message. |
| **Session export** (/export) | LangGraph state is serializable | Low | pyharness reads LangGraph state → formats as Markdown. |
| **Image attachments** | No native image support in filesystem tools | Low | pyharness implements as specialized tool or middleware. |
| **LSP integration** | None | Medium | pyharness implements as separate tool. Outside agent runtime scope anyway. |

### 1.3 Integration Cost vs Build Cost

| Layer | Build from Scratch | Integrate DeepAgents | Verdict |
|-------|-------------------|---------------------|--------|
| Agent loop | 2-3 weeks | 2 days (wrap `create_deep_agent`) | **DeepAgents** |
| Sub-agents | 4-6 weeks | 1 day (define `SubAgent` specs) | **DeepAgents** |
| Filesystem tools | 2-3 weeks | 0 days (built-in) | **DeepAgents** |
| Todo list | 1 week | 0 days (built-in) | **DeepAgents** |
| Compaction | 3-4 weeks | 0 days (built-in) | **DeepAgents** |
| HITL | 3-4 weeks | 2 days (wire `interrupt_on` + TUI dialogs) | **DeepAgents** |
| MCP client | 3-4 weeks | 1 day (`langchain-mcp-adapters`) | **DeepAgents** |
| Skills | 2-3 weeks | 1 day (configure `SkillsMiddleware`) | **DeepAgents** |
| Git undo/redo | 2-3 weeks | 2-3 weeks (custom middleware) | **Build** (not in DeepAgents) |
| TUI (all) | 6-8 weeks | 6-8 weeks | **Build** (not in DeepAgents) |
| Provider bridge | 2-3 weeks | 0 days (LangChain) | **DeepAgents** |
| Plugin system | 2-3 weeks | 1-2 weeks (middleware adapters) | **Shared** |
| Config loader | 1-2 weeks | 1-2 weeks (config → LangChain mapping) | **Build** |
| Session persistence | 2-3 weeks | 0 days (LangGraph checkpointer) | **DeepAgents** |
| Streaming to TUI | 1-2 weeks | 1-2 weeks (LangGraph streaming → Textual) | **Shared** |
| Session management UI | 2-3 weeks | 2-3 weeks | **Build** (TUI concern) |

**Total: ~25 engineering weeks with DeepAgents vs ~50-60 without. That's 2x acceleration.**

---

## 2. Architecture Impact

### 2.1 What happens to the "Core Engine" layer

The current architecture diagram (§2) has a "Core Engine" layer with: Session Manager, Agent Runtime, Tool Registry, Config Loader, Provider Bridge, Plugin System.

**With DeepAgents, the Core Engine is replaced by the DeepAgents stack:**

```
┌─────────────────────────────────────────────┐
│  pyharness TUI Layer (unchanged)              │
│  ChatArea | SidePanel | StatusBar/CmdBar      │
├─────────────────────────────────────────────┤
│  pyharness Integration Layer (NEW)            │
│  ┌───────────┐ ┌────────────┐ ┌────────────┐ │
│  │ Session   │ │ Git Undo/  │ │ TUI → HITL  │ │
│  │ Manager   │ │ Redo       │ │ Bridge      │ │
│  │ (threads) │ │ Middleware │ │             │ │
│  └───────────┘ └────────────┘ └────────────┘ │
│  ┌───────────┐ ┌────────────┐ ┌────────────┐ │
│  │ Config →  │ │ Skill      │ │ Agent       │ │
│  │ LangChain │ │ Discovery  │ │ Loader      │ │
│  │ Adapter   │ │            │ │             │ │
│  └───────────┘ └────────────┘ └────────────┘ │
├─────────────────────────────────────────────┤
│  DeepAgents Runtime (REPLACES Core Engine)    │
│  ┌──────────────────────────────────────────┐ │
│  │  create_deep_agent(model, tools, ...)     │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │ TodoList │ │ File-    │ │ SubAgent │ │ │
│  │  │ MW       │ │ system MW│ │ MW       │ │ │
│  │  ├──────────┤ ├──────────┤ ├──────────┤ │ │
│  │  │Summarize │ │ PatchTool│ │ Skills MW│ │ │
│  │  │MW        │ │ MW       │ │          │ │ │
│  │  ├──────────┤ ├──────────┤ ├──────────┤ │ │
│  │  │ Memory MW│ │ HITL MW  │ │ Custom MW│ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ │ │
│  └──────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│  LangChain `create_agent`                     │
│  Model → Tools → Loop → Streaming             │
├─────────────────────────────────────────────┤
│  LangGraph Runtime                             │
│  State | Checkpoints | Streaming | Interrupts  │
├─────────────────────────────────────────────┤
│  Storage (unchanged)                           │
│  ~/.config/pyharness/ | ~/.local/share/...    │
│  SQLite (supplemental) | LangGraph Store       │
└─────────────────────────────────────────────┘
```

**Key changes:**
- **Session Manager** → now wraps LangGraph thread management (thread_id = session_id)
- **Agent Runtime** → `create_deep_agent(...)` replaces custom ReAct loop
- **Tool Registry** → DeepAgents tools + MCP tools + pyharness custom tools
- **Config Loader** → maps `pyharness.json` → `create_deep_agent()` parameters
- **Provider Bridge** → LangChain's `init_chat_model("provider:model")` replaces litellm
- **Plugin System** → DeepAgents middleware replaces hook events

### 2.2 DeepAgents Sub-Agents → pyharness Agent Mapping

DeepAgents' `SubAgent` concept maps cleanly to pyharness's agent system:

```python
# pyharness agent definition (from SPEC.md §5.2)
# becomes a DeepAgents SubAgent spec:

from deepagents.middleware.subagents import SubAgent

build_agent: SubAgent = {
    "name": "build",
    "description": "Full tool access. Default agent for implementation.",
    "system_prompt": """You are in build mode...""",
    "model": "anthropic:claude-sonnet-4-5",
    "tools": ALL_TOOLS,
    "permissions": [{"path": "/**", "mode": "allow"}],
}

plan_agent: SubAgent = {
    "name": "plan",
    "description": "Read-only. For analysis and planning.",
    "system_prompt": "You are in plan mode...",
    "model": "anthropic:claude-haiku-4-5",
    "tools": READ_ONLY_TOOLS,
    "permissions": [{"path": "/**", "mode": "read"}],
}

general_subagent: SubAgent = {
    "name": "general",
    "description": "Multi-step tasks, parallel execution.",
    "system_prompt": "You are a general-purpose subagent...",
    "model": "anthropic:claude-haiku-4-5",
    "tools": ALL_TOOLS,
}

explore_subagent: SubAgent = {
    "name": "explore",
    "description": "Read-only. Fast codebase exploration and search.",
    "system_prompt": "You are in explore mode...",
    "model": "anthropic:claude-haiku-4-5",
    "tools": READ_ONLY_TOOLS,
}
```

**Agent switching** (Tab key) changes the **main agent** between `build` and `plan`. Sub-agents are invoked via the `task` tool.

**@mention** (`@explore find the auth middleware`) is pre-processed by pyharness TUI → creates a `task` tool call with `subagent_type: "explore"`.

### 2.3 HITL → Permission System Mapping

DeepAgents' `HumanInTheLoopMiddleware` has two modes:
1. **`interrupt_on`**: Declarative `{tool_name: bool | InterruptOnConfig}` config
2. **Interrupt flow**: Agent runs → hits tool → LangGraph pauses → external code resumes

**pyharness's permission dialogs integrate here:**

```python
# pyharness TUI hooks into LangGraph interrupt:

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=ALL_TOOLS,
    interrupt_on={
        "bash": {"allowed_decisions": ["approve", "reject"]},
        "write": {"allowed_decisions": ["approve", "reject"]},
        "external_directory": {"allowed_decisions": ["approve", "reject"]},
    },
    checkpointer=LangGraphCheckpointer(),
)

# When the agent hits an interrupted tool, LangGraph pauses.
# pyharness TUI reads the interrupt, renders a permission dialog,
# and resumes the graph with the user's decision.
```

**Permission glob patterns** (e.g., `"edit": "allow"` for `*.py` files) are handled by:
- DeepAgents' `FilesystemMiddleware` with `permissions` parameter for filesystem tools
- pyharness custom middleware for non-filesystem permission checks

```python
# Filesystem permissions in DeepAgents:
permissions=[
    {"path": "src/**", "mode": "allow"},
    {"path": "/etc/**", "mode": "deny"},
]
```

### 2.4 Context Management → Compaction Mapping

DeepAgents' `SummarizationMiddleware` handles auto-compaction. pyharness adds:
- **Manual compaction** (`/compact` command): sends a tool call or system instruction
- **TUI indicators**: shows token usage, compaction events in status bar
- **Reserved buffer**: configured via `system_prompt` and summarization settings

```python
# DeepAgents' summarization is configurable:
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    # The SummarizationMiddleware auto-compacts at thresholds
    # pyharness can configure these thresholds
)
```

### 2.5 Filesystem Tools → Tool Registry Mapping

DeepAgents' built-in tools **completely replace** pyharness's built-in tool implementations:

| pyharness Tool | DeepAgents Tool | Notes |
|---------------|-----------------|-------|
| `bash` | `execute` (from `SandboxBackendProtocol`) | Same semantics; sandbox support |
| `read` | `read_file` (from `FilesystemMiddleware`) | Same; supports offset/limit |
| `write` | `write_file` (from `FilesystemMiddleware`) | Same |
| `edit` | `edit_file` (from `FilesystemMiddleware`) | Same exact string replacement |
| `grep` | `grep` (from `FilesystemMiddleware`) | Same |
| `glob` | `glob` (from `FilesystemMiddleware`) | Same |
| `task` | `task` (from `SubAgentMiddleware`) | Same; subagent delegation |
| `todowrite` | `write_todos` (from `TodoListMiddleware`) | Same |
| `webfetch` | Custom tool via `tools=` parameter | Still custom |
| `websearch` | Custom tool via `tools=` parameter | Still custom |
| `question` | Custom tool or `interrupt_on` | Custom |
| `skill` | `SkillsMiddleware` (auto-loads) | Different; skills load at start |

**Custom tools** (webfetch, websearch, question, and any plugin tools) are passed as:
```python
agent = create_deep_agent(
    tools=[webfetch_tool, websearch_tool, question_tool, *mcp_tools],
)
```

---

## 3. What Changes in SPEC.md

### Section 5 (Agent System) — **Adapted, not replaced**

- **Keep**: Agent definitions (Markdown frontmatter), agent modes (primary/subagent), agent switching (Tab), @mention (inline subagent invocation)
- **Replace**: Agent loop implementation details → reference DeepAgents
- **Add**: DeepAgents SubAgent spec → pyharness agent definition mapping
- **Remove**: Custom ReAct loop implementation plan

### Section 6 (Session System) — **Supplemented by LangGraph**

- **Keep**: Session lifecycle (start→active→idle→compacted→archived), git-backed undo/redo
- **Supplement**: Session storage → LangGraph `checkpointer` + `store` for conversation state, pyharness SQLite for metadata (session titles, git refs, token counts)
- **Change**: "Sessions stored as SQLite" → "Conversation state stored by LangGraph checkpoint; session metadata stored in SQLite"

### Section 7 (Tools) — **Simplified**

- **Replace**: Built-in tool implementations → DeepAgents built-in tools + custom tools
- **Keep**: Tool permission model, tool namespacing for MCP
- **Remove**: `@tool` decorator (use LangChain's `@tool`)
- **Add**: How custom tools integrate with DeepAgents' middleware stack

### Section 8 (MCP) — **Simplified**

- **Replace**: Custom MCP client → `langchain-mcp-adapters`
- **Keep**: MCP config schema (maps to `MultiServerMCPClient` config)
- **Add**: `pyharness mcp init` command (unchanged from strategic analysis)

### Section 9 (Plugins) — **Renamed to Middleware**

- **Change**: Plugin system → Middleware system (DeepAgents-native extension)
- **Keep**: Hook event names (but implement as middleware methods)
- **Add**: Mapping of pyharness hook events → DeepAgents middleware hooks:
  - `tool.execute.before` → `AgentMiddleware.wrap_tool_call`
  - `tool.execute.after` → `AgentMiddleware.wrap_tool_call`
  - `session.created` → pyharness wrapper around `create_deep_agent`
  - `session.compacted` → `SummarizationMiddleware` events
  - `session.idle` → LangGraph state change
  - `permission.asked` → LangGraph interrupt
  - `permission.replied` → LangGraph resume

### Section 10 (Agent Skills) — **Unchanged API, different backend**

- **Keep**: SKILL.md format, discovery locations
- **Change**: Implementation via `SkillsMiddleware(sources=[...])`
- **Remove**: Custom skill loader → use DeepAgents' built-in

### Section 11 (Custom Commands) — **Unchanged API, implemented as SubAgents**

- **Keep**: Command format (Markdown frontmatter), variable syntax
- **Change**: Implementation → commands compile to pre-built `SubAgent` specs

### Section 12 (TUI Layout) — **Unchanged**

- DeepAgents is headless. TUI remains 100% pyharness code.
- **Add**: LangGraph streaming → Textual widget bridge

### Section 13 (Provider Bridge) — **Replaced**

**DROP litellm. Use LangChain's model abstraction.**

Rationale:
1. DeepAgents **requires** LangChain chat models. You can't use litellm with DeepAgents.
2. LangChain supports 50+ model providers natively — more than enough.
3. litellm's 100+ provider count includes many low-quality providers. The ones that matter are all in LangChain.
4. For providers LangChain doesn't natively support, the `ChatOpenAI`-compatible API works with any OpenAI-compatible endpoint (Ollama, vLLM, local servers).
5. Anthropic-specific features (prompt caching) are handled by `AnthropicPromptCachingMiddleware` — not litellm.

**New provider architecture:**
```python
# pyharness.json
{
    "model": "anthropic:claude-sonnet-4-5",
    "provider": {
        "anthropic": {"apiKey": "{env:ANTHROPIC_API_KEY}"},
        "openai": {"apiKey": "{env:OPENAI_API_KEY}"},
        "ollama": {"base_url": "http://localhost:11434"}
    }
}

# Maps to:
from langchain.chat_models import init_chat_model

model = init_chat_model("anthropic:claude-sonnet-4-5")
agent = create_deep_agent(model=model, ...)
```

### Section 14 (Implementation Phases) — **Major restructure**

See §4 below.

### Section 15 (Directory Structure) — **Simplified**

```
pyharness/
├── pyproject.toml
├── src/
│   └── pyharness/
│       ├── __init__.py
│       ├── main.py
│       ├── config/
│       │   ├── loader.py
│       │   └── schema.py
│       ├── agents/
│       │   ├── definitions.py    # build, plan, general, explore SubAgent specs
│       │   └── loader.py         # Markdown → SubAgent converter
│       ├── agent_runtime/
│       │   └── factory.py        # create_deep_agent wrapper + config → params
│       ├── middleware/           # pyharness custom middleware
│       │   ├── git_undo.py       # Git-backed undo/redo
│       │   ├── permission_ui.py  # TUI permission dialog bridge
│       │   └── streaming.py      # LangGraph → Textual streaming
│       ├── tools/
│       │   ├── custom/           # webfetch, websearch, question
│       │   └── mcp_config.py     # MCP server config → MultiServerMCPClient
│       ├── tui/
│       │   ├── app.py
│       │   ├── screens/
│       │   │   ├── chat.py
│       │   │   └── sessions.py
│       │   ├── widgets/
│       │   │   ├── input.py
│       │   │   ├── message.py
│       │   │   ├── tool_result.py
│       │   │   ├── permission.py  # HITL permission dialog widget
│       │   │   ├── sidebar.py
│       │   │   ├── file_tree.py
│       │   │   └── status.py
│       │   └── themes/
│       ├── skills/
│       │   └── loader.py         # SKILL.md discovery → SkillsMiddleware sources
│       ├── commands/
│       │   └── loader.py
│       └── sessions/
│           └── manager.py        # Thread ID → pyharness session mapping
├── tests/
└── docs/
```

**Files REMOVED** (replaced by DeepAgents):
- `core/agent.py` — replaced by DeepAgents
- `core/compaction.py` — replaced by SummarizationMiddleware
- `tools/registry.py` — replaced by DeepAgents middleware
- `tools/builtin/` — all replaced by DeepAgents built-in tools
- `tools/mcp_client.py` — replaced by langchain-mcp-adapters
- `providers/base.py` — replaced by LangChain models
- `providers/litellm_.py` — replaced by LangChain models
- `providers/native/` — replaced by LangChain integrations
- `plugins/hooks.py` — replaced by DeepAgents middleware hooks
- `plugins/manager.py` — replaced by DeepAgents middleware system (simpler)

---

## 4. Phase Planning Impact

### 4.1 Revised Implementation Phases

**Phase A — Launch (weeks 1-6, previously 1-12):**
1. Config loading (pydantic + JSON5 → `create_deep_agent()` params)
2. Provider setup (LangChain `init_chat_model` with Anthropic + OpenAI + Ollama)
3. Agent runtime (`create_deep_agent` wrapper with build/plan agents)
4. Tools: all built-in via DeepAgents filesystem + custom (webfetch, websearch)
5. **Permission system** via `interrupt_on` + TUI permission dialogs
6. Simple scrollable TUI (input → response, no side panels)
7. Session persistence (LangGraph checkpointer + SQLite metadata)
8. Git-backed undo/redo (custom middleware)

**Phase B — Differentiators (weeks 7-12, previously 13-20):**
9. **MCP client** (`langchain-mcp-adapters` + `MultiServerMCPClient`)
10. **`pyharness mcp init`** scaffolding command
11. @ file references (TUI pre-processing)
12. Side panel (sessions + file tree)
13. Command palette

**Phase C — Polish (weeks 13-18, previously 21-28):**
14. SKILL.md discovery (`SkillsMiddleware` with discovered paths)
15. Custom commands (SubAgent specs from Markdown)
16. General + Explore subagents
17. Theme system (Textual CSS)
18. Editor mode (/editor)

**Phase D — Growth (post-initial adoption):**
19. Plugin/middleware ecosystem
20. Web search & webfetch (if not already in Phase A)
21. LSP integration
22. Image attachments
23. Server mode

### 4.2 Can We Skip Phases?

**Yes — significantly.** With DeepAgents:

| Original Phase | DeepAgents Impact | New Scope |
|---------------|-------------------|-----------|
| Phase 1 (Core Engine) | ~60% done by DeepAgents | 2 weeks config + wrapper, not 8-10 weeks |
| Phase 2 (Full Agent System) | Sub-agents, permissions, HITL are built-in | 3 weeks glue code, not 6-8 weeks |
| Phase 3 (TUI Polish) | Unchanged | 4-6 weeks (pure TUI code) |
| Phase 4 (MCP & Skills) | MCP client, skills are built-in | 1-2 weeks config, not 4-6 weeks |
| Phase 5 (Plugins) | Middleware replaces plugins | 2-3 weeks, not 4-6 weeks |
| Phase 6 (Advanced) | Unchanged | Deferred as before |

### 4.3 New Phase 1 MVP Scope (6 weeks)

**Week 1-2: DeepAgents Integration**
- `pyharness/agent_runtime/factory.py`: `create_pyharness_agent()` wrapping `create_deep_agent()`
- `pyharness/config/loader.py` + `schema.py`: pydantic models → `create_deep_agent()` params
- Provider config mapping

**Week 3-4: Tools + Permissions**
- Custom tools: `webfetch`, `websearch`, `question`
- `interrupt_on` config → TUI permission dialogs
- Git undo/redo middleware

**Week 5-6: TUI + Sessions**
- Simple scrollable TUI (input → response)
- LangGraph checkpointer integration
- SQLite session metadata
- First end-to-end: type prompt → agent responds → see tool calls → TUI renders

### 4.4 Integration Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LangGraph version conflicts | Medium | High | Pin all LangChain packages; use `uv lock` |
| DeepAgents API instability (pre-1.0?) | Medium | Medium | Pin specific version; wrap in adapter layer |
| LangChain dependency weight (~12 packages) | Low | Low | `uv add deepagents` handles this; acceptable for a desktop/terminal tool |
| LangSmith optional but encouraged | Low | Low | Completely optional; disable by default |
| DeepAgents moves away from open-core model | Low | High | MIT license protects against this; fork if needed |
| TUI + LangGraph async loop conflict | Medium | High | Textual and LangGraph both use asyncio; test early |

---

## 5. Provider Bridge Impact

### Recommendation: Drop litellm, adopt LangChain model abstraction

| Factor | litellm | LangChain |
|--------|---------|-----------|
| Provider count | 100+ | 50+ |
| Works with DeepAgents? | **No** (requires LangChain chat models) | **Yes** (native) |
| Anthropic prompt caching | Manual via native adapter | Auto via `AnthropicPromptCachingMiddleware` |
| OpenAI reasoning effort | Manual | Built-in |
| Streaming | Yes | Yes (via LangGraph) |
| Tool calling | Yes | Yes (via LangGraph) |
| Ollama support | Yes | Yes (`ollama:model-name`) |
| Local servers (vLLM, llama.cpp) | Yes | Yes (OpenAI-compatible endpoint) |
| Vision | Yes | Yes |
| Dependency weight | Light | Heavier (but we already need LangChain) |
| Config format | litellm-specific | LangChain `provider:model` format |

**The decision is forced: DeepAgents requires LangChain models.** Even if we kept litellm, we'd need a litellm→LangChain adapter. At that point, just use LangChain natively.

### Config mapping

```python
# pyharness.json → LangChain model init
def model_from_config(config: PyharnessConfig) -> BaseChatModel:
    """Map pyharness config to LangChain chat model."""
    provider = config.provider  # { "anthropic": {...}, "openai": {...} }

    # Set env vars from config
    for name, cfg in provider.items():
        if "apiKey" in cfg:
            os.environ[f"{name.upper()}_API_KEY"] = resolve_env(cfg["apiKey"])

    return init_chat_model(config.model)
    # config.model = "anthropic:claude-sonnet-4-5"
```

---

## 6. MemPalace + DeepAgents Synergy

### 6.1 Can MemPalace be the backend for DeepAgents' persistent memory?

**Yes — with an adapter.** DeepAgents' `MemoryMiddleware` uses a `BackendProtocol` to read memory sources. The default reads AGENTS.md files from the filesystem. MemPalace could serve as a semantic memory backend:

```python
# Conceptual: MemPalaceBackend for DeepAgents
class MemPalaceBackend(BackendProtocol):
    """DeepAgents backend that routes memory reads through MemPalace."""

    async def read_memory_source(self, source: str) -> str:
        """Read a memory source.
        If source starts with 'mempalace:', query MemPalace.
        Otherwise fall back to filesystem.
        """
        if source.startswith("mempalace:"):
            query = source[len("mempalace:"):]
            results = await mempalace_search(query=query, wing="pyharness")
            return format_mempalace_results(results)
        return await self.fs_backend.read(source)
```

### 6.2 How do DeepAgents' checkpointing + MemPalace's semantic memory complement?

They solve **different problems** and complement perfectly:

| Layer | What It Stores | Retrieval Method |
|-------|---------------|-----------------|
| **LangGraph Checkpoints** | Conversation state, message history, tool results | By `thread_id` (exact match) |
| **DeepAgents Memory** | AGENTS.md files, loaded at startup | As system prompt text |
| **MemPalace** | Semantic search across ALL project knowledge (design docs, past decisions, architecture) | By semantic similarity |

**Synergy pattern:**
1. Agent starts → MemPalace injects project context into system prompt
2. Agent runs → conversation state stored in LangGraph checkpoints
3. Agent completes → MemPalace stores key decisions/findings
4. Next session → MemPalace provides context without re-reading entire project

**Implementation:**
```python
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    memory=[
        "./AGENTS.md",                          # Filesystem memory
        "mempalace:pyharness architecture",      # MemPalace semantic memory
        "mempalace:pyharness decisions",         # MemPalace decisions
        "mempalace:pyharness patterns",          # MemPalace code patterns
    ],
)
```

---

## 7. Revised SPEC.md Outline

### Proposed Structure

```
1.  Vision (updated: "MCP-native, Python-terminal coding agent powered by DeepAgents")
2.  Tech Stack & Rationale (updated: DeepAgents replaces custom agent runtime)
3.  Architecture Overview (updated: DeepAgents stack diagram)
4.  Feature Matrix (simplified; remove "Same" for deferred features)
5.  Configuration (unchanged schema, updated provider mapping)
6.  Agent System (adapted: agents as DeepAgents SubAgent specs)
7.  Session System (supplemented: LangGraph checkpoint + SQLite metadata)
8.  Tools (simplified: built-in from DeepAgents + custom + MCP)
9.  MCP Server Support (simplified: langchain-mcp-adapters)
10. Middleware System (renamed from Plugins: DeepAgents middleware = plugin API)
11. Agent Skills (unchanged API; SkillsMiddleware backend)
12. Custom Commands (unchanged API; SubAgent implementation)
13. TUI Layout (unchanged)
14. Provider Bridge (replaced: LangChain model abstraction)
15. Implementation Phases (restructured: 4 phases, ~18 weeks to MVP+)
16. Directory Structure (simplified)
17. Key Design Decisions (updated: why DeepAgents, why LangChain over litellm)
18. MemPalace Integration (NEW: semantic memory + checkpointing complement)
19. Open Questions / Risks (updated: LangChain dependency risk, DeepAgents API stability)
20. Appendix A: Competitive Landscape (from strategic analysis)
21. Appendix B: Aider Migration Path (from strategic analysis)
22. Appendix C: DeepAgents Integration Details (NEW: middleware hook mapping, SubAgent spec examples)
```

---

## 8. Key Decisions Summary

| # | Decision | Rationale | Impact |
|---|----------|-----------|--------|
| 1 | **Adopt DeepAgents** | Saves 35-50 eng weeks; 26K stars, MIT, production-grade | Reduces Phase 1 from 12 to 6 weeks |
| 2 | **Drop litellm** | DeepAgents requires LangChain models; LangChain covers 50+ providers | One-time config mapping cost (~2 days) |
| 3 | **Keep SQLite** for session metadata | LangGraph handles conversation state; SQLite for titles, git refs, token counts | No migration needed |
| 4 | **Middleware replaces Plugins** | DeepAgents middleware IS the extension point; simpler than custom plugin system | Hook event mapping needed (~1 week) |
| 5 | **Git undo/redo as middleware** | DeepAgents middleware can wrap tool calls to capture git snapshots | ~2-3 weeks implementation |
| 6 | **TUI permission dialogs via LangGraph interrupts** | HITL interrupts are the integration point between DeepAgents and TUI | ~2-3 days to wire |
| 7 | **MemPalace as optional memory backend** | Complements DeepAgents' filesystem memory with semantic search | ~1 week adapter |
| 8 | **MCP via langchain-mcp-adapters** | Production-grade MCP client; stdio + HTTP transports | Saves 3-4 weeks of MCP client development |

---

## 9. Dependency Manifest

```toml
# pyproject.toml (deepagents integration)
[project]
dependencies = [
    "deepagents>=0.7.0",           # Agent harness (MIT, 26K stars)
    "langchain>=0.3.0",            # Agent abstraction (MIT)
    "langgraph>=0.3.0",            # Graph runtime, checkpoints, streaming (MIT)
    "langchain-anthropic",         # Anthropic Claude models (MIT)
    "langchain-openai",            # OpenAI models (MIT)
    "langchain-ollama",            # Ollama local models (MIT)
    "langchain-mcp-adapters",      # MCP client integration (MIT)
    "pydantic>=2.0",               # Config validation (MIT)
    "json5",                       # JSON5 config parsing (Apache 2.0)
    "textual>=2.0",                # TUI framework (MIT)
    "gitpython",                   # Git undo/redo (BSD)
    "watchfiles",                  # File watching (MIT)
    "mempalace",                   # Semantic memory (pyharness-specific)
]

[tool.uv.sources]
deepagents = { git = "https://github.com/langchain-ai/deepagents" }
```

**Total new dependencies (vs original spec):** +`deepagents`, +`langchain-*` packages (~8 packages, all MIT licensed). Removed: `litellm` and native provider adapters.

---

## 10. Risk Register

| Risk | Severity | Probability | Mitigation | Contingency |
|------|----------|-------------|------------|-------------|
| DeepAgents API changes break pyharness | High | Medium | Pin version; adapter layer; CI tests on every DeepAgents release | Fork and freeze DeepAgents |
| LangChain dependency chain too heavy | Low | Low | Acceptable for terminal tool (users install once via uv) | Vendor critical LangChain modules |
| TUI + LangGraph async loop conflict | High | Medium | Both use asyncio; test early | Textual worker + LangGraph in separate thread |
| DeepAgents lacks feature we need later | Medium | Low | Middleware system is extensible; LangGraph gives escape hatch | Custom LangGraph graph, bypass DeepAgents |
| LangChain model init fails for some provider | Medium | Low | Provider config in pyharness.json → try multiple init methods | Fallback to `ChatOpenAI`-compatible endpoint |
| Textual performance with streaming | Medium | Medium | LangGraph streaming modes are configurable; buffer in TUI | Reduce streaming granularity |
| DeepAgents goes proprietary | Low | Very Low | MIT license; 26K stars on GitHub | Fork from last MIT release |

---

*This analysis reflects DeepAgents v0.7.0+ architecture as documented at docs.langchain.com, combined with pyharness SPEC.md as of July 14, 2026. All recommendations assume a solo/small-team development context where "build" costs are measured in engineering weeks and "buy" costs are measured in integration days.*
