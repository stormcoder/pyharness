# pyharness — Technology Strategy: DeepAgents + MemPalace

> July 14, 2026 | Strategic recommendation on two major technology adoption decisions

---

## Executive Summary

**Adopt MemPalace. Do NOT adopt DeepAgents.**

MemPalace is a clear win: it provides semantic memory, knowledge graphs, and agent diaries that no competitor offers, with manageable dependency weight and no competitive risk. DeepAgents carries a hidden fatal risk: **DeepAgents Code** (`curl -LsSf https://langch.in/dcode | bash`) is a direct competitor in the terminal coding agent space. Building pyharness on DeepAgents means building on a competitor's runtime — architectural lock-in to a framework owned by the same organization that ships a competing product. Instead, pyharness should use **LangGraph directly** (the graph runtime underneath DeepAgents) for its agent orchestration, keeping the LangChain ecosystem compatibility without ceding control of the agent harness layer.

---

## 1. Technology Deep-Dive

### 1.1 DeepAgents

| Attribute | Value |
|-----------|-------|
| GitHub Stars | 26,184 |
| License | MIT |
| Language | Python (98.9%) |
| Contributors | 140 |
| Releases | 214 |
| Latest | `deepagents-code==0.1.37` (July 13, 2026) |
| Dependencies | langchain-core, langgraph, langsmith (optional), langchain (optional) |
| Key Features | Sub-agents, virtual filesystem, context management, shell sandbox, persistent memory, human-in-the-loop, skills, MCP support, `write_todos` planning |

**Capability overlap with SPEC.md:**

| SPEC.md Feature | DeepAgents Built-In | Overlap |
|-----------------|---------------------|---------|
| Agent loop (ReAct) | ✅ `create_deep_agent` core loop | 100% |
| Sub-agents (task tool) | ✅ Built-in `task` tool for ephemeral sub-agents | 100% |
| Tool registry (bash, read, write, edit, grep, glob) | ✅ Virtual filesystem + shell sandbox | ~80% |
| Context management (compaction) | ✅ Auto-summarization + tool output offloading | 100% |
| Session persistence | ✅ LangGraph checkpointing + store backends | 100% |
| MCP client | ✅ Any MCP server as tools | 100% |
| Skills (SKILL.md) | ✅ Built-in skill loading | 100% |
| Permission system | ✅ `interrupt_on` for human-in-the-loop | ~60% |
| Git-backed undo/redo | ❌ Not built-in | 0% |
| TUI (Textual) | ❌ DeepAgents Code uses CLI, not TUI | 0% |
| Plugin system | ❌ No plugin hooks | 0% |

**DeepAgents would replace ~65% of the SPEC.md's Phase 1-4 custom code.**

### 1.2 MemPalace

| Attribute | Value |
|-----------|-------|
| GitHub Stars | 57,236 |
| License | MIT |
| Language | Python (93.5%) |
| Contributors | 110 |
| Latest | v3.5.0 (June 23, 2026) |
| Dependencies | chromadb, numpy, grpcio, sentence-transformers (or embeddinggemma-300m) |
| Backend | ChromaDB (default) |
| Disk Footprint | ~300MB (default model) or ~30MB (MiniLM) |

**MemPalace capabilities:**

| Feature | Description | pyharness Use Case |
|---------|-------------|-------------------|
| Semantic search (`search_memories`) | 96.6% R@5 retrieval accuracy | Cross-session recall of past work |
| Knowledge graph (`KnowledgeGraph`) | Temporal entity-relation graph on SQLite | Codebase understanding across sessions |
| Agent diaries (`diary_write`/`diary_read`) | Per-agent journal in AAAK format | Agent self-reflection and improvement |
| Memory stack (`MemoryStack`) | 4-layer memory (identity → essential → retrieval → deep search) | Hierarchical context loading |
| Wing/Room/Drawer model | Structured, scoped storage | Project-specific memory isolation |
| MCP protocol | Memory tools exposed via MCP | pyharness could expose `mempalace_*` tools to any agent |

---

## 2. DeepAgents: The Fatal Risk

### 2.1 DeepAgents Code is a direct competitor

This is the critical finding from the GitHub research:

> **"Deep Agents Code — a pre-built coding agent in your terminal, similar to Claude Code or Cursor, powered by any LLM. Install with `curl -LsSf https://langch.in/dcode | bash`."**

DeepAgents Code (package `deepagents-code==0.1.37`) is a terminal coding agent. It exists in the same market as pyharness. It is built by the same organization (LangChain) that maintains the DeepAgents library. Currently it's CLI-based, not TUI-based — but if it adds a TUI mode (Textual or even just a richer CLI), it becomes substantially equivalent to the "Phase A" pyharness product.

**The strategic risk:** Building pyharness on DeepAgents means:
1. LangChain controls the agent runtime API — any breaking change, deprecation, or  migration forces pyharness to update
2. DeepAgents Code could absorb any pyharness innovation (MCP hosting, MemPalace integration) by adding them to the library
3. LangChain has 140 contributors on DeepAgents vs. pyharness's solo/small team — they can out-build pyharness on the same foundation
4. The messaging problem: "pyharness is a TUI on top of DeepAgents" makes pyharness sound like a thin wrapper, not an independent product

### 2.2 LangChain ecosystem lock-in

DeepAgents ties pyharness to the LangChain stack:

```
deepagents
  └── langgraph (durable execution, checkpoints, streaming)
  └── langchain-core (chat models, tools, messages)
  └── langsmith (tracing, evaluation - optional)
```

This stack is well-designed and production-proven. But it's also a walled garden. Models must implement LangChain's chat model interface. Tools must be LangChain tools. The agent loop is LangGraph's `CompiledStateGraph`. This is fine if you're building ON the ecosystem, but risky if you're building AGAINST a product (DeepAgents Code) from the same ecosystem.

### 2.3 Dependency weight for a TUI tool

| Dependency | Approximate Size | Required? |
|-----------|-----------------|-----------|
| langchain-core | ~15MB | Yes |
| langgraph | ~20MB | Yes |
| langsmith | ~5MB | Optional |
| langchain (full) | ~50MB | Optional |
| deepagents | ~5MB | Yes |
| **Total minimum** | **~40MB** | |
| **Total with extras** | **~95MB** | |

For a tool pitched as "lightweight, pip-installable", 40MB of framework dependencies before any feature code is written is substantial. Compare:
- `aider-chat`: ~25MB total
- `pip install textual`: ~8MB

### 2.4 Recommendation: Use LangGraph directly, not DeepAgents

**The middle path:**

```
pyharness agent runtime
  └── langgraph (graph execution, checkpoints, streaming)
  └── custom agent loop (thin ReAct implementation)
  └── custom tool registry (built-in + MCP)
  └── custom context management
```

This approach:
- ✅ Uses LangGraph for durable execution and checkpoints (battle-tested)
- ✅ Keeps the agent loop, tool registry, and context management custom (differentiation)
- ✅ Maintains LangChain ecosystem compatibility without lock-in
- ✅ Avoids dependency on a competing product (DeepAgents Code)
- ✅ ~20MB lighter (no deepagents package)
- ✅ SPEC.md's existing agent architecture (§5) maps cleanly to this approach
- ⚠️ Requires implementing sub-agents, skills, and context compaction from scratch
- ⚠️ Adds ~4-6 weeks to Phase 2 timeline vs. using DeepAgents

**The key tradeoff:** Give up ~4-6 weeks of development velocity to maintain architectural independence from a competitor. For a pre-product project, this is the right call. Architectural decisions made now will compound for years.

---

## 3. MemPalace: The Clear Win

### 3.1 Competitive uniqueness

**No terminal coding agent has semantic memory.** This is a genuine differentiator:

| Tool | Session Persistence | Cross-Session Memory | Semantic Search | Knowledge Graph |
|------|-------------------|---------------------|-----------------|-----------------|
| OpenCode | ✅ SQLite sessions | ❌ | ❌ | ❌ |
| Claude Code | ✅ Local files | ❌ | ❌ | ❌ |
| Aider | ✅ Git history | ❌ | ❌ | ❌ |
| Codex CLI | ✅ Local files | ❌ | ❌ | ❌ |
| Crush | ✅ Sessions | ❌ | ❌ | ❌ |
| DeepAgents Code | ✅ LangGraph store | ❌ | ❌ | ❌ |
| **pyharness + MemPalace** | ✅ Sessions | ✅ **Memory across sessions** | ✅ **Semantic search** | ✅ **Entity-relation graph** |

### 3.2 What MemPalace enables that no competitor has

1. **"What did we do last time?"** — Agent recalls past sessions, decisions, and fixes via semantic search
2. **"Where was that bug?"** — Semantic search across all past sessions for code patterns, error messages, or file references
3. **Persistent codebase understanding** — Mine the codebase into the palace, build a knowledge graph of the architecture, and load it on session start
4. **Agent self-improvement** — Agent diaries enable agents to learn from past sessions (what worked, what didn't)
5. **Project wings** — Different projects get isolated memory contexts

### 3.3 Dependency analysis

| Concern | Analysis | Verdict |
|---------|----------|---------|
| ChromaDB dependency | ChromaDB is ~15MB, battle-tested, and embeddable. It runs in-process. | ✅ Acceptable |
| Embedding model size | 300MB (default) or 30MB (MiniLM). MiniLM is sufficient for code search. | ✅ Use MiniLM by default |
| Memory overhead | 100-500MB RAM for vector index depending on corpus size | ⚠️ Acceptable for a development tool |
| Install complexity | `pip install mempalace` + first-run model download | ✅ Acceptable |
| Startup time | ~2-5 seconds for embedding model warm-up on first run | ✅ Acceptable |

### 3.4 Integration strategy

```
┌────────────────────────────────────────────────────────────┐
│                    pyharness Agent Loop                      │
│                                                              │
│  On session start:                                           │
│    1. mempalace.wake_up(wing=project_name)  → L0 + L1       │
│    2. Load recent session summaries                         │
│    3. Load project knowledge graph facts                    │
│                                                              │
│  During session:                                             │
│    - Agent writes to mempalace diary on key decisions       │
│    - Files edited → update knowledge graph                  │
│    - User asks "remember when..." → semantic search          │
│                                                              │
│  On session end:                                             │
│    - Mine session into MemPalace                            │
│    - Update knowledge graph with new facts                  │
│    - Write agent diary entry                                │
└────────────────────────────────────────────────────────────┘
```

MemoPalace should be:
- **Optional but shipped by default** — `pip install pyharness` includes mempalace as an optional dependency
- **Auto-configured on first run** — `pyharness` detects MemPalace presence, offers to set up memory
- **Privacy-first** — All memory is local. No cloud. User can delete at any time.
- **Scoped by project** — Each project gets its own wing; cross-project tunneling optional

---

## 4. Revised Architecture

### 4.1 Agent Runtime — LangGraph + Custom

```python
# pyharness/core/agent.py — Custom agent loop on LangGraph

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint import MemorySaver

def create_agent(tools: list[Tool], model: LLMProvider):
    """Build a ReAct agent graph with custom tool dispatch."""

    builder = StateGraph(MessagesState)

    async def call_model(state: MessagesState):
        response = await model.chat(state["messages"], tools)
        return {"messages": [response]}

    async def route_tools(state: MessagesState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "execute_tools"
        return END

    async def execute_tools(state: MessagesState):
        # Custom tool dispatch with permissions, MCP routing, etc.
        ...

    builder.add_node("agent", call_model)
    builder.add_node("tools", execute_tools)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_tools, {...})
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=MemorySaver())
```

### 4.2 Memory — MemPalace

```python
# pyharness/memory/mempalace.py — MemPalace integration

from mempalace.layers import MemoryStack
from mempalace.searcher import search_memories

class ProjectMemory:
    def __init__(self, project_name: str):
        self.stack = MemoryStack()
        self.wing = project_name

    async def load_context(self) -> str:
        """Return ~500 tokens of project context on session start."""
        return self.stack.wake_up(wing=self.wing)

    async def search(self, query: str, room: str | None = None) -> list[dict]:
        """Semantic search across past sessions."""
        return search_memories(query, wing=self.wing, room=room)

    async def record_decision(self, decision: str):
        """Record a key decision in the knowledge graph."""
        ...

    async def mine_session(self, session_path: str):
        """Mine a completed session into the palace."""
        ...
```

### 4.3 Revised dependency tree

```
pyharness
├── textual (TUI)
├── litellm (provider bridge)
├── pydantic (config)
├── langgraph (agent orchestration — minimal)
├── GitPython (undo/redo)
├── mcp (Python SDK)
├── watchfiles (file watching)
├── [extras] mempalace (cross-session memory)
└── [extras] chromadb (if using MemPalace)
```

---

## 5. Differentiation Impact — Revised

### 5.1 New elevator pitch

> **"The terminal coding agent that remembers."**
>
> pyharness is a Python-native TUI coding agent with persistent memory, MCP-native tooling, and cross-session recall. It's the only coding agent that learns from every session — remembering past decisions, fixes, and codebase architecture so you don't repeat yourself.

### 5.2 New "aha moment"

> *"I opened pyharness in a project I hadn't touched in two weeks, and it immediately recalled the bug I'd been debugging, the approach I'd settled on, and the files that were affected — all from its memory of our last session."*

### 5.3 Competitive positioning matrix

| Feature | OpenCode | Claude Code | Aider | DeepAgents Code | **pyharness** |
|---------|----------|-------------|-------|----------------|---------------|
| TUI | ✅ Go | ✅ Node.js | ✅ Python CLI | ❌ CLI only | ✅ Textual |
| Multi-provider | ✅ 75+ | ❌ Claude only | ✅ litellm | ✅ LangChain models | ✅ litellm |
| MCP host | ✅ Client only | ✅ Client only | ❌ | ✅ Client only | ✅ **Client + host** |
| Semantic memory | ❌ | ❌ | ❌ | ❌ | ✅ **MemPalace** |
| Knowledge graph | ❌ | ❌ | ❌ | ❌ | ✅ **MemPalace** |
| Agent diaries | ❌ | ❌ | ❌ | ❌ | ✅ **MemPalace** |
| Python-native | ❌ Go | ❌ TS | ✅ | ✅ | ✅ |
| Python plugins | ❌ | ❌ | ✅ (via litellm) | ✅ (via LangChain) | ✅ pip entry points |
| Open source | ✅ MIT | ❌ | ✅ Apache 2.0 | ✅ MIT | ✅ MIT |
| Git undo/redo | ✅ | ❌ | ✅ Auto-commit | ❌ | ✅ |

### 5.4 Does this strengthen the "bet on MCP"?

**Yes, significantly.** MemPalace can be exposed as an MCP server:

```
# pyharness mcp server exposes mempalace tools:
mempalace_search    — Semantic search across project memory
mempalace_remember  — Record a fact or decision
mempalace_recall    — Recall past sessions
mempalace_kg_query  — Query the knowledge graph
```

This creates a virtuous cycle: pyharness treats MCP as first-class, MemPalace is exposed via MCP, and any MCP-compatible tool can leverage pyharness's memory features. This is a genuine ecosystem play that no competitor is making.

---

## 6. Adoption Barriers — Revised

### 6.1 LangGraph dependency weight

| Component | Size | Required |
|-----------|------|----------|
| langgraph | ~20MB | Yes |
| langchain-core | ~15MB | Yes (model + tools types) |
| **Total framework** | **~35MB** | |

This is acceptable. langgraph + langchain-core provides durable execution and model abstraction without the full LangChain framework weight.

### 6.2 MemPalace dependency weight

| Component | Size | Required |
|-----------|------|----------|
| chromadb | ~15MB | Yes (for MemPalace) |
| MiniLM model | ~30MB | Yes (for MemPalace) |
| mempalace package | ~0.5MB | Yes (for MemPalace) |
| **Total MemPalace overhead** | **~45MB** | Optional |

### 6.3 Total install size

| Configuration | Approximate Size |
|---------------|-----------------|
| pyharness (minimal) | ~60MB (Textual + litellm + langgraph) |
| pyharness + MemPalace | ~105MB |
| pyharness + MemPalace + ChromaDB | ~120MB |
| For comparison: `aider-chat` | ~25MB |
| For comparison: `claude` (Claude Code) | ~150MB (Node.js + deps) |

The minimal install of ~60MB is competitive. The full install of ~120MB is heavy but justified by the memory features. The recommendation is:

```bash
pip install pyharness              # Minimal: no memory
pip install pyharness[mempalace]   # Full: with memory
```

### 6.4 Making it optional

```toml
# pyproject.toml
[project.optional-dependencies]
mempalace = ["mempalace>=3.5.0", "chromadb>=0.5.0"]

# At runtime:
try:
    from mempalace.searcher import search_memories
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
```

---

## 7. Revised Go-to-Market

### 7.1 Updated elevator pitch

> **pyharness is the terminal coding agent that learns.** It remembers every session — every bug fixed, every architecture decision, every refactor — and uses that memory to help you code faster. MCP-native. Python-first. Open source.

### 7.2 Messaging anchors

1. **"The coding agent that remembers"** — Memory as primary differentiator
2. **"MCP-native, not MCP-compatible"** — First-class MCP server hosting + client
3. **"Python-first, not Python-only"** — pip install, Python plugins, but any language project
4. **"Aider's spiritual successor"** — Git-native workflow + MCP + memory

### 7.3 Ideal first user (revised)

**Primary: The Python polyglot who's tried everything**
- Used Aider but frustrated with maintenance mode
- Has Claude Code but wants multi-provider
- Lives in the terminal
- Has multiple projects and wishes AI remembered context across sessions
- Has built or wants to build MCP servers
- Value prop: "Pick up exactly where you left off — in any project, any time"

**Secondary: The ML/AI engineer**
- Jupyter + terminal workflow
- Needs memory across notebooks and sessions
- Wants MCP server integration for data tools
- Value prop: "Your AI pair programmer that remembers your experiments and pipelines"

---

## 8. Revised Kill Criteria

### 8.1 Previous kill criteria (from strategic analysis)

- **6 months post-Phase A:** <100 GitHub stars, 0 external contributors
- **12 months:** <500 DAU, no community MCP integrations
- **Competitive signal:** Aider exits maintenance mode + ships MCP; OpenCode ships `mcp init`

### 8.2 Updated kill criteria

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| **6 months post-MVP** | <200 GitHub stars | Higher bar because memory is a stronger differentiator |
| **12 months** | <500 DAU or 0 community MCP servers targeting pyharness | Same as before |
| **DeepAgents Code TUI** | If DeepAgents Code ships a TUI mode within 9 months | They absorb the "agent harness in terminal" lane |
| **OpenCode adds memory** | If OpenCode ships cross-session semantic memory within 12 months | They absorb the memory differentiator |
| **Aider revival** | If Aider exits maintenance mode AND ships MCP within 6 months | They reclaim the Python terminal agent niche |
| **MemPalace acquired/deprecated** | If MemPalace project ends or goes proprietary | Memory becomes custom code burden |
| **LangGraph licensing change** | If LangGraph goes non-open-source | Forces pyharness to reimplement agent orchestration |

### 8.3 Accelerated kill trigger (new)

**If DeepAgents Code ships a TUI mode within 6 months of pyharness MVP, kill the project or pivot to being a DeepAgents Code skin.** The risk of being sandwiched between DeepAgents Code (below) and OpenCode (above) is existential if they converge.

---

## 9. SPEC.md Impact — Concrete Revisions

### 9.1 Architecture changes

| SPEC.md Section | Current | Revised |
|-----------------|---------|---------|
| §1 (Tech Stack) | No agent framework listed | Add: Agent orchestration = **LangGraph** (not DeepAgents) |
| §1 (Tech Stack) | No memory layer | Add: Memory = **MemPalace** (optional with `[mempalace]` extra) |
| §2 (Architecture) | Core Engine: Agent Runtime | Rename: Agent Runtime → LangGraph-based with custom ReAct loop |
| §5 (Agent System) | Custom sub-agent implementation | Implement via LangGraph subgraphs (not DeepAgents `task` tool) |
| §6 (Session System) | SQLite for sessions | SQLite + MemPalace for cross-session memory |
| §14 (Implementation Phases) | 6-phase plan | Revised to 4-phase plan (see below) |

### 9.2 Revised implementation phases

**Phase A — Launch (weeks 1-10):**
1. Config loading (pydantic + JSON5)
2. Provider bridge (litellm: Anthropic, OpenAI, Ollama)
3. LangGraph-based agent loop (ReAct pattern)
4. Tools: read, write, edit, grep, glob, bash
5. Permission system (allow/ask/deny)
6. Simple TUI (input → response)
7. Session persistence (SQLite)
8. **MemPalace integration (optional, shipped by default)**

**Phase B — Differentiators (weeks 11-18):**
9. MCP client (local stdio + remote HTTP)
10. `pyharness mcp init` scaffolding command
11. @ file references + ! bash injection
12. Side panel (sessions + files)
13. Command palette

**Phase C — Polish (weeks 19-26):**
14. Plan agent (read-only)
15. Sub-agents via LangGraph subgraphs
16. Git-backed undo/redo
17. SKILL.md discovery + custom commands
18. Theme system (Textual CSS)

**Phase D — Growth (post-adoption):**
19. Plugin system
20. Web search via MCP
21. LSP integration
22. Image attachments

### 9.3 New SPEC.md sections needed

1. **§8b — Memory System** (after MCP Server Support)
   - MemPalace integration architecture
   - Wing/Room/Drawer model for pyharness
   - Cross-session recall workflow
   - Knowledge graph integration
   - Agent diary format
   - Privacy guarantees (local-only)

2. **§5b — Sub-agent Architecture** (after Agent System)
   - LangGraph subgraph pattern for sub-agents
   - Context isolation strategy
   - Permission inheritance model

---

## 10. Recommendation Summary

| Decision | Verdict | Rationale |
|----------|---------|-----------|
| **Adopt DeepAgents?** | **NO** | DeepAgents Code is a direct competitor. Use LangGraph directly for agent orchestration. |
| **Adopt MemPalace?** | **YES** | Clearest differentiator in the market. No competitor has semantic memory. Make it optional but shipped by default. |
| **Use LangGraph?** | **YES** | Provides durable execution, checkpoints, and streaming without depending on competing product. |
| **Build own agent loop?** | **YES** | Thin ReAct loop on LangGraph — 95% of the benefit of DeepAgents at 100% architectural independence. |
| **Revised MVP scope?** | MemPalace moves from "future" to **Phase A** | Memory is the differentiator. Ship it from day one. |
| **Revised GTM?** | Lead with **"the coding agent that remembers"** | Memory + MCP + Python is the unique stack. |

### The bet

> **pyharness bets that memory matters more than benchmarks.** No one wins a coding agent war on SWE-bench scores or feature count. The tools that win are the ones developers form a relationship with — the tools that learn their codebase, remember their decisions, and get better over time. MemPalace makes that possible. DeepAgents would make pyharness a thin wrapper on a competitor's runtime. LangGraph gives pyharness the infrastructure without the dependency.

---

*Analysis prepared July 14, 2026. Revisit after Phase A ships and DeepAgents Code ships its next major release.*
