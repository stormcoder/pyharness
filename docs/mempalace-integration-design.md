# MemPalace Integration Design for pyharness

> **Date**: 2026-07-14
> **Author**: Technical Architect
> **Status**: Proposal (Phase 0)
> **Dependencies**: MemPalace 0.x (MIT, Python-native, ChromaDB/SQLite)

---

## 1. Built-in vs Plugin

### Decision: **First-class built-in component** (Phase 2 — Full Agent System)

**Rationale:**

1. **Every session needs memory.** Memory is not an optional feature like theme color or a specific MCP server. It's core infrastructure — the agent must know what happened before, the user must be able to resume context, and sub-agents need shared awareness. A plugin that might not be installed creates a degraded core experience.

2. **The TUI needs memory-aware UI.** The session tree, the side panel, the "resume" flow, and the context loading indicators are all TUI elements that must exist whether or not a plugin is installed. Building them as conditional UI (hidden when no plugin) adds complexity without benefit.

3. **MCP tools must be available to the agent out of the box.** The `mempalace_search`, `mempalace_kg_query`, and `mempalace_diary_write` tools need to be in the agent's tool list from session start. If they're only available when a plugin MCP server is running, there's a chicken-and-egg problem: the agent can't search memory at session start, which is when it needs it most.

4. **Progressive disclosure is possible.** Even as a built-in, MemPalace can be gracefully disabled if the `mempalace` Python package is not installed. The session system still works with SQLite-only storage; cross-session semantic memory and KG are simply unavailable.

**How it works:**

- `mempalace` becomes a documented **optional dependency** in `pyproject.toml` under `[project.optional-dependencies]`
- At import time, `pyharness.memory` checks `importlib.util.find_spec("mempalace")` and creates either a real `MemoryStore` or a `NoopMemoryStore`
- The config key `memory.enabled: false` can explicitly disable it even when the package is installed
- The TUI always renders memory-aware UI tabs; they show "Install mempalace" guidance when unavailable

---

## 2. Architecture Integration Points

### 2.1 MemPalace ↔ SQLite Relationship

MemPalace does NOT replace SQLite session storage. They serve different purposes:

| Concern | SQLite (existing) | MemPalace (new) |
|---------|-------------------|------------------|
| Message storage | ✅ Primary store — every message is persisted in SQLite | Not used for structured message persistence |
| Semantic recall | Not possible | ✅ Vector search across all sessions |
| Cross-session context | Manual session loading only | ✅ Automatic: "what did we discuss yesterday?" |
| Fact memory (KG) | Not possible | ✅ "AuthMiddleware lives in src/auth/" |
| Agent diaries | Not possible | ✅ Per-agent learning journal |
| Session state machine | ✅ Session lifecycle, git refs, token counts | Not used for lifecycle |
| Work-in-progress | ✅ Current conversation state | Not used for WIP |

**Design principle: SQLite is the transactional system of record. MemPalace is the long-term memory. Do not store the same message in both; instead, store messages in SQLite and index them into MemPalace.**

### 2.2 Agent Loop Integration

The agent loop writes to MemPalace at specific boundaries, not on every message:

```
┌─────────────────────────────────────────────────────────┐
│                   Agent Loop (ReAct)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │  Think   │→ │  Act     │→ │ Observe  │→ (loop)       │
│  └──────────┘  └──────────┘  └──────────┘               │
│       ↑                         │                        │
│       │                         ↓                        │
│  [wake-up]              ┌───────────────┐                │
│  load context           │ Write triggers:│               │
│  from MemPalace         │                │               │
│                         │ session.begin  │               │
│                         │ session.idle   │               │
│                         │ compaction     │               │
│                         │ session.end    │               │
│                         │ tool: file.edit│               │
│                         └───────────────┘                │
└─────────────────────────────────────────────────────────┘
```

**Write timing:**

| Event | What's written | Rationale |
|-------|----------------|-----------|
| `session.begin` | Load context (search kg) | Agent needs prior decisions before first message |
| `session.idle` | Index last N exchanges | Agent just finished a turn; capture conclusions |
| `compaction` | Write compacted summary + index | Old messages being removed from context window; capture them before they're gone |
| `session.end` | Full session index + diary write | Final checkpoint of everything learned |
| `tool: file.edit` | KG fact update | "File X was modified" — lightweight, batched |
| `tool: task` (subagent launch) | Child session link | Parent → child relationship in KG |

**What's NOT written live:** Every single LLM token/response. That stays in SQLite. MemPalace gets semantic chunks (conclusions, decisions, facts), not raw message streams.

### 2.3 Wake-Up Protocol

When a session starts (new or resume), pyharness calls:

```python
# pyharness/memory/wake.py
async def wake_up(memory: MemoryStore, session_id: str, project: str) -> WakeUpContext:
    """Load relevant context for session start."""
    # 1. Load KG facts about this project
    kg_facts = await memory.kg_query(entity=project)

    # 2. Semantic search for the N most relevant past conversations
    #    Uses the first user message of this session as query
    relevant_memories = await memory.search(
        query=first_user_message,
        wing=project,
        limit=5
    )

    # 3. Load recent agent diary entries
    diary = await memory.diary_read(agent_name="build", last_n=3)

    return WakeUpContext(
        kg_facts=kg_facts,
        relevant_memories=relevant_memories,
        diary=diary,
    )
```

This context is injected as a system message preamble:

```
[MEMORY CONTEXT — prior decisions and context for this session]

## Architecture Decisions (from knowledge graph)
- AuthMiddleware lives in src/auth/middleware.py
- We decided to use JWT over sessions on 2026-07-10
- Database schema is in src/db/schema.py

## Related Past Conversations
- "implemented password reset flow" (2026-07-12, session abc123)
  → We used Flask-Mail for email sending, not SMTP directly.
- "added rate limiting to login endpoint" (2026-07-11, session def456)
  → Used slowapi with Flask-Limiter. 5 attempts per minute.

## Recent Agent Learnings
- build agent: "Flask-Mail needs MAIL_SERVER configured in .env"
- build agent: "Test DB uses in-memory SQLite, not PostgreSQL"
```

### 2.4 Sub-Agent Sessions

Sub-agents write to the same project wing but in separate rooms:

```
┌───────────────────────────────────────────────────────┐
│  Wing: pyharness_project (project root)                │
│                                                        │
│  Room: sessions/          ← Parent session memories    │
│  Room: sessions/{child}   ← Sub-agent memories         │
│  Room: decisions/         ← Architecture decisions     │
│  Room: codebase/          ← KG facts about files       │
│                                                        │
│  Wing: agent_diary_build  ← Build agent's diary        │
│  Wing: agent_diary_plan   ← Plan agent's diary         │
│  Wing: agent_diary_general← General subagent's diary   │
└───────────────────────────────────────────────────────┘
```

**Rationale for same-wing-different-rooms:**
- A sub-agent's work (e.g., `@explore find the auth middleware`) should be findable when the parent agent searches for "auth middleware"
- But the sub-agent's raw exploration log shouldn't pollute the parent's session room
- Rooms provide scoping without fragmentation

### 2.5 Knowledge Graph Integration

The KG captures structured facts about the codebase that the agent discovers or confirms:

```python
# KG fact examples (subject → predicate → object)
"AuthMiddleware" → "located_in" → "src/auth/middleware.py"
"pyharness" → "uses" → "pydantic v2"
"session ABC123" → "decided" → "JWT over sessions"
"User model" → "has_field" → "email (unique, indexed)"

# Temporal facts (with validity windows)
"API v1" → "deprecated" → "2026-09-01"  (valid_from=2026-09-01)
```

**Agent writes to KG when:**
1. It reads a file and confirms where a class/function lives → `located_in`
2. It makes a design decision → `decided`
3. It discovers a dependency relationship → `uses` / `depends_on`
4. User explicitly asks to remember something → `/remember "The test DB uses in-memory SQLite"`

**Agent reads from KG:**
- On session start (wake-up)
- When the user asks "where is X?" or "what did we decide about Y?"
- Before modifying a file (impact analysis — "who depends on this?")

---

## 3. Tech Stack Implications

### 3.1 Deployment Profile

```
pip install mempalace
```

**Additional dependencies brought in by MemPalace:**

| Package | Purpose | Size |
|---------|---------|------|
| `chromadb` | Vector storage (embedded) | ~50MB |
| `sentence-transformers` or `embeddinggemma` | Embeddings model | ~100MB (first run download) |
| `sqlite3` (stdlib) | KG backend | 0 (already included) |

**Disk impact:** ~150MB for the first `mempalace` install. After that, ~50MB + storage for indexed content (roughly 10% of source size for embeddings).

**Startup time impact:** First indexing of a project takes ~5-30s (one-time). Subsequent sessions: ~50ms to load cached index. Wake-up search: ~100ms.

### 3.2 Direct Library Usage (not just MCP)

MemPalace can be used **directly as a Python library**, which is the preferred approach for pyharness:

```python
# Direct library usage — no MCP server needed
from mempalace import MemPalace

palace = MemPalace(wing="my_project")

# Search
results = palace.search("how does auth work", limit=5)

# KG operations
palace.kg_add("AuthMiddleware", "located_in", "src/auth/middleware.py")
facts = palace.kg_query("AuthMiddleware")

# Diary
palace.diary_write(agent_name="build", entry="Learned: Flask-Mail config...")

# Mine codebase
palace.mine("/path/to/project", mode="projects")
```

This avoids the overhead of running a separate MCP server process and allows pyharness to manage the MemPalace lifecycle directly (init on startup, close on exit).

**The MCP tools are still registered for the agent to call** — they become thin wrappers around the direct library calls, but this way pyharness owns the connection lifecycle.

### 3.3 Graceful Degradation

```python
# pyharness/memory/__init__.py
import importlib.util

_HAS_MEMPALACE = importlib.util.find_spec("mempalace") is not None

if _HAS_MEMPALACE:
    from pyharness.memory.store import MemPalaceStore as MemoryStore
else:
    from pyharness.memory.noop import NoopStore as MemoryStore

__all__ = ["MemoryStore"]
```

**What happens without MemPalace:**

| Feature | With MemPalace | Without |
|---------|---------------|---------|
| Session persistence | ✅ SQLite | ✅ SQLite (unchanged) |
| Cross-session search | ✅ Semantic search | ❌ SQLite full-text search only (LIKE queries) |
| Knowledge graph | ✅ Structured facts | ❌ No KG |
| Agent diary | ✅ Persistent diary | ❌ No diary |
| Session resume | ✅ Context from KG + vector search | ✅ SQLite messages only (no rich context) |
| Session resume context | Rich: prior decisions, related conversations | Basic: title, model, last few messages |
| TUI memory panel | Memory-aware: KG facts, related sessions, agent diary | Shows "MemPalace not installed — install for enhanced memory" |

---

## 4. Configuration

### 4.1 New Config Keys

```jsonc
{
  // ... existing config ...

  "memory": {
    // Enable/disable the memory system entirely
    "enabled": true,

    // Wing name for this project. Defaults to the project root directory name.
    // Set explicitly for shared config across multiple clones.
    "wing": "pyharness",

    // Rooms to create and populate
    "rooms": ["sessions", "decisions", "codebase"],

    // Auto-indexing configuration
    "auto_index": {
      // Automatically mine the project codebase on first session
      "enabled": true,

      // What to index: "projects" (code/docs), "convos" (chat transcripts)
      "mode": "projects",

      // Re-index triggers
      "on_git_push": false,     // Re-index after git push
      "on_branch_change": true, // Re-index when switching branches
      "schedule": null          // Cron expression: "0 */6 * * *" (every 6 hours)
    },

    // What the agent loop writes automatically
    "auto_write": {
      // Write KG facts when agent confirms a file location
      "kg_file_locations": true,

      // Write diary entry when session ends
      "diary_on_session_end": true,

      // Index messages into vector store on compaction
      "index_on_compaction": true,

      // Index messages into vector store on session idle (agent finishes responding)
      "index_on_idle": true,

      // Max number of exchanges to index per idle cycle
      "max_index_per_idle": 10
    },

    // Wake-up configuration
    "wake_up": {
      // Inject memory context as system message preamble
      "inject_context": true,

      // Max KG facts to load
      "max_kg_facts": 20,

      // Max past conversation results to load
      "max_relevant_memories": 5,

      // Min similarity score for relevant memories (0-2, lower = stricter)
      "max_memory_distance": 1.2,

      // Load agent diary entries
      "load_diary": true,
      "max_diary_entries": 3
    },

    // Search configuration for the agent's `mempalace_search` tool
    "agent_search": {
      // Default result limit for agent-initiated searches
      "default_limit": 5,

      // Max results the agent can request
      "max_limit": 20
    }
  }
}
```

### 4.2 Per-Project Wings

The wing name is configured per-project:

```jsonc
// .pyharness/pyharness.json (project-local)
{
  "memory": {
    "wing": "my-web-app",
    "rooms": ["sessions", "decisions", "codebase", "docs"]
  }
}
```

When the wing name is not set explicitly, it defaults to the project root directory name (e.g., `pyharness` for this repo). This means:

- **Same repo, different clones** → same wing (search finds conversations from other clones)
- **Different repo** → different wing (search is scoped to this project)
- **Configuration override** → set `memory.wing` explicitly to force a specific wing

### 4.3 Auto-Save Frequency

Auto-save is event-driven, not timer-driven:

| Event | Config key | Default | Behavior |
|-------|-----------|---------|----------|
| Agent finishes responding | `auto_write.index_on_idle` | `true` | Index last exchange |
| Context compaction | `auto_write.index_on_compaction` | `true` | Index compacted summary |
| Session ends | `auto_write.diary_on_session_end` | `true` | Write agent diary |
| File edited by agent | `auto_write.kg_file_locations` | `true` | Update KG fact |
| User `/remember` | N/A (explicit) | N/A | Always written immediately |

No timer-based auto-save is needed because the agent's natural boundaries (idle, compaction, session end) provide sufficient granularity.

---

## 5. Feature-Level Design

### 5.1 Session Resume with MemPalace Context

When the user resumes a session (`pyharness --resume abc123` or selecting from the session list):

```
1. Load SQLite session state (all messages, git refs, token counts)
2. Get first user message of the session
3. Search MemPalace: vector_search(query=first_message, wing=project, limit=5)
4. Query KG: kg_query(entity=project)
5. Read diary: diary_read(agent_name="build", last_n=3)
6. Compose context preamble
7. Inject as first system message (or append to system prompt)
8. Scroll chat to last message
```

**TUI indicator:**
```
[Memory] Loaded 12 KG facts, 3 related conversations, 2 diary entries
```

### 5.2 Cross-Session Context

When the user asks "what did we discuss yesterday about auth?":

1. The agent calls `mempalace_search(query="auth authentication password login", wing=project, limit=5)`
2. MemPalace returns verbatim snippets from previous sessions, with timestamps and session IDs
3. The agent synthesizes: "On 2026-07-13 (session def456), we implemented JWT authentication in `src/auth/jwt.py`. We decided to use HS256 signing with a 24-hour expiry."

The agent can also query the KG directly:
- `mempalace_kg_query(entity="AuthMiddleware")` → returns all facts about AuthMiddleware
- `mempalace_kg_query(entity="pyharness")` → returns all project-level decisions

### 5.3 Memory-Aware Side Panel

The existing side panel (SPEC §12.1: Sessions, File Tree, Tool Output) gains a fourth tab:

```
┌─ Memory (F4) ──────────────────┐
│                                 │
│ ▼ Knowledge Graph               │
│   AuthMiddleware               │
│   → src/auth/middleware.py     │
│   JWT decision                 │
│   → 2026-07-10, session abc   │
│   User model                   │
│   → email (unique, indexed)    │
│                                 │
│ ▼ Related Sessions (3)          │
│   • "password reset"  Jul 12   │
│   • "rate limiting"   Jul 11   │
│   • "login endpoint"  Jul 10   │
│                                 │
│ ▼ Agent Diary                   │
│   build agent, Jul 14:         │
│   "Flask-Mail needs MAIL_      │
│    SERVER in .env"             │
│                                 │
├─────────────────────────────────┤
│ [Ctrl+r refresh] [M search...]  │
└─────────────────────────────────┘
```

**Keybinds:**
- `F4` or `Ctrl+4` — Open Memory tab
- `Enter` on a fact — Show full drawer content
- `Enter` on a related session — Switch to that session
- `/m search terms` — Search memory with a query
- `/remember "fact"` — Manually add a fact to KG

### 5.4 New Slash Commands

| Command | Action |
|---------|--------|
| `/memory` | Open the Memory side panel tab |
| `/remember <fact>` | Manually add a fact to the knowledge graph |
| `/search-memory <query>` | Search past sessions for a topic |
| `/forget <fact>` | Invalidate a KG fact |
| `/diary` | Show this agent's recent diary entries |

### 5.5 New Tools for the Agent

```python
@tool(
    name="mempalace_search",
    description="Search past sessions and project knowledge for relevant information. Use when: "
                "the user asks about something discussed before, you need to recall a past decision, "
                "or you want to find related code you've worked on.",
    permission_key="memory"
)
async def mempalace_search(query: str, limit: int = 5) -> str: ...

@tool(
    name="mempalace_kg_query",
    description="Query the knowledge graph for structured facts about the codebase — "
                "file locations, architecture decisions, dependencies.",
    permission_key="memory"
)
async def mempalace_kg_query(entity: str) -> str: ...

@tool(
    name="mempalace_remember",
    description="Save a fact to the knowledge graph. Use when the user explicitly asks you "
                "to remember something, or when you confirm a file location or dependency.",
    permission_key="memory"
)
async def mempalace_remember(fact: str) -> str: ...
```

---

## 6. Code Structure

```
src/pyharness/
├── memory/                       # NEW: Memory subsystem
│   ├── __init__.py               # Exports MemoryStore, checks for mempalace
│   ├── store.py                  # MemPalaceStore: real implementation
│   ├── noop.py                   # NoopStore: graceful degradation
│   ├── wake.py                   # Wake-up protocol (load context on session start)
│   ├── indexer.py                # Message-to-memory indexing (chunking, embedding)
│   ├── tools.py                  # Agent tools: mempalace_search, kg_query, remember
│   └── cli.py                    # CLI commands: pyharness memory init/status/search
├── config/
│   └── schema.py                 # ADD: memory config model to PyHarnessConfig
├── core/
│   ├── session.py                # MODIFY: integrate MemoryStore into session lifecycle
│   └── agent.py                  # MODIFY: inject memory context on wake-up
├── tui/
│   └── widgets/
│       └── memory_panel.py       # NEW: Memory side panel widget
└── commands/
    └── memory_commands.py        # NEW: /memory, /remember, /search-memory, /forget, /diary
```

---

## 7. SPEC.md Additions

### 7.1 Tech Stack table addition

```markdown
| Memory | mempalace (optional) | Cross-session semantic search, knowledge graph, agent diaries |
```

### 7.2 New section: §17 — Memory System

```markdown
## 17. Memory System (MemPalace)

pyharness integrates [MemPalace](https://github.com/mempalace/mempalace) as a first-class memory subsystem. MemPalace provides:

- **Cross-session semantic search** — "What did we discuss about auth yesterday?"
- **Knowledge graph** — Structured facts about the codebase (file locations, decisions, dependencies)
- **Agent diaries** — Each agent writes learnings across sessions
- **Verbatim recall** — Past conversations stored word-for-word, never summarized

### 17.1 Architecture

MemPalace supplements (does not replace) SQLite session storage. SQLite is the transactional system of record for messages, tool calls, and session state. MemPalace indexes selected content for cross-session retrieval.

### 17.2 Installation

`mempalace` is an optional dependency. When installed, all memory features are available. When not installed, pyharness degrades gracefully — SQLite session storage works normally, but cross-session search and knowledge graph are unavailable.

```bash
pip install mempalace     # or: uv add mempalace
```

### 17.3 Configuration

See `memory` section in pyharness.json schema (§4.2).

### 17.4 Agent Tools

- `mempalace_search` — Semantic search across past sessions
- `mempalace_kg_query` — Query the knowledge graph
- `mempalace_remember` — Save a fact to the knowledge graph

### 17.5 Wake-Up Protocol

On session start, pyharness loads relevant context from MemPalace (KG facts, related conversations, agent diary) and injects it as a system message preamble.

### 17.6 TUI

The side panel gains a "Memory" tab (F4) showing KG facts, related sessions, and agent diary entries.
```

### 7.3 Feature Matrix addition

```markdown
| **Cross-session memory** | Not available | MemPalace (optional) | Semantic search, KG, agent diaries |
```

### 7.4 Phase placement

Add to Phase 2 (Full Agent System):

```markdown
- Memory system (MemPalace integration)
  - MemPalaceStore with graceful degradation
  - Wake-up protocol (load context on session start)
  - Agent tools: mempalace_search, kg_query, remember
  - Auto-indexing on session idle/compaction/end
```

Add to Phase 3 (TUI Polish):

```markdown
- Memory side panel (KG facts, related sessions, agent diary)
- Memory slash commands (/memory, /remember, /diary)
```

---

## 8. Open Questions

1. **Chunking strategy**: How do we chunk message exchanges for vector indexing? By turn (user↔assistant pair)? By paragraph? Sliding window? Recommendation: **by turn** — each complete user↔assistant exchange is one chunk. This preserves the conversation structure and makes recall more natural ("in that exchange about auth, we decided...")

2. **Privacy**: MemPalace stores data locally (ChromaDB + SQLite). No data leaves the machine. This is the same trust model as pyharness's SQLite sessions. No new privacy concerns.

3. **Cleanup**: Should old session data be automatically removed from MemPalace when the SQLite session is deleted? Recommendation: **yes, with a confirmation prompt**. Deleting a session should delete both the SQLite file AND the MemPalace indexes for that session.

4. **Mining the codebase**: On first run in a project, should pyharness auto-run `mempalace mine` to index the codebase? Recommendation: **prompt the user on first run** — "pyharness can index your codebase for faster memory. This takes ~30s and uses ~150MB disk. Run now? [Y/n]"

5. **MemPalace vs OpenCode parity**: OpenCode has no memory system beyond SQLite sessions. MemPalace integration is a **differentiator**, not a parity requirement. This means we can be opinionated and user-friendly rather than chasing exact feature parity.

---

## 9. Summary

| Decision | Choice |
|----------|--------|
| Built-in vs Plugin | **Built-in** (optional dep, graceful fallback) |
| SQLite replacement | **No** — supplements, not replaces |
| Python library or MCP-only | **Direct library** usage; MCP tools as wrappers |
| Write timing | **Event-driven** (session boundaries), not per-message |
| Sub-agent storage | **Same wing, separate rooms** |
| Config key | `memory.*` in pyharness.json |
| Default state | **enabled: true** if mempalace installed; **noop** if not |
| Phase placement | **Phase 2** (core memory) + **Phase 3** (TUI memory panel) |
