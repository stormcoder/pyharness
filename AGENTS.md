# AGENTS.md — pyharness

## Project context

pyharness is a Python-native TUI LLM harness (OpenCode equivalent in Python). Currently in **Phase 0 — Specification**. No production code exists. All design docs are in this repo.

## Key documents

- `SPEC.md` — Full specification, architecture, feature matrix, implementation phases
- `docs/mockups/` — SVG mockups of TUI layouts and system architecture
- `docs/deepagents-integration-analysis.md` — Why we rejected DeepAgents, why we chose LangGraph
- `docs/mempalace-integration-design.md` — MemPalace integration design (built-in, not plugin)
- `docs/strategic-analysis.md` — Strategic positioning and GTM analysis
- `docs/ux-review.md` — UX review of mockups with severity-ordered findings
- `docs/technology-strategy-deepagents-mempalace.md` — Technology adoption strategy
- `README.md` — Project overview and quick links

## Tech stack (confirmed)

| Layer | Choice | Notes |
|-------|--------|-------|
| TUI | Textual 2.x | CSS-like layout, reactive, async-native |
| Agent runtime | LangGraph | Durable execution, checkpointing, subgraphs, HITL |
| LLM models | LangChain chat models | 50+ providers, unified interface |
| Provider bridge | LangChain packages + OpenRouter + LiteLLM (opt) | Three-layer: first-party (18 pkgs), OpenRouter (200+ models), LiteLLM gateway (optional). Full coverage. |
| Memory | MemPalace (optional dep) | Semantic search, knowledge graph, agent diaries. 96.6% R@5. |
| Config | pydantic v2 + JSON5 | Schema-validated `pyharness.json` |
| Git | GitPython + git CLI | Undo/redo middleware. git CLI for performance-critical ops. |
| MCP | langchain-mcp-adapters + mcp SDK | MCP servers as LangChain tools |
| Session storage | SQLite (WAL mode) | System of record; LangGraph checkpoints for agent state |
| File watch | watchfiles | Auto-refresh chat context |
| Logging | structlog | Structured from day one |
| Package mgmt | uv | Fast deps, build, task running. `uv run pyharness` |
| Testing | pytest + pytest-asyncio + pytest-textual-snapshot | Mock LLM provider, temp SQLite, temp git repo fixtures |
| Minimum Python | 3.12 | PEP 695 type params |

## Design reference

This project closely models [OpenCode](https://opencode.ai/docs) — every feature in OpenCode should have a counterpart here. When in doubt about behavior, consult OpenCode docs at https://opencode.ai/docs/ or the source at https://github.com/anomalyco/opencode.

## Key technology decisions

### LangGraph (not DeepAgents)
We use **LangGraph** directly as the agent graph runtime — not DeepAgents. LangChain ships `deepagents-code` (a competing terminal coding agent), making DeepAgents a competitor's runtime. LangGraph at the lower abstraction level gives us durable execution + checkpointing without the competitive entanglement. See `docs/deepagents-integration-analysis.md` for the full analysis.

### MemPalace as built-in memory
MemPalace is a **first-class built-in component** with `mempalace` as an optional dependency. When installed: semantic memory, knowledge graph, agent diaries, cross-session recall, wake-up context. When absent: graceful SQLite-only fallback. This is pyharness's primary differentiator — no other terminal coding agent has semantic memory.

### LangChain models (not litellm)
LangGraph uses LangChain chat models natively. Covering 50+ providers through a single interface. No litellm adapter layer needed.

## Implementation order

Phases are defined in `SPEC.md` §13 (revised from original 6 → 4 phases):

1. **Foundation** (Weeks 1-6) — LangGraph agent, tools, TUI chat, MemPalace, permissions
2. **Full Agent System** (Weeks 7-10) — Plan/general/explore agents, undo/redo, side panels
3. **MCP, Skills & Memory UX** (Weeks 11-14) — MCP client, skills, memory UX, themes
4. **Advanced & Polish** (Weeks 15-18) — Plugins, LSP, images, sharing, server mode

## Rules

- All config follows `pyharness.json` schema (mirrors `opencode.json`)
- Agent definitions use markdown frontmatter (same format as OpenCode)
- Skills use `SKILL.md` files with YAML frontmatter (same format as OpenCode)
- Plugins are Python entry points: `[project.entry-points.pyharness]` and LangGraph middleware
- Sessions stored as SQLite (WAL mode) in `~/.local/share/pyharness/sessions/`
- MemPalace index stored in `~/.local/share/pyharness/mempalace/`
- Don't start coding without reading `SPEC.md` first
- Use `uv run` for all commands: `uv run pyharness`, `uv run pytest`, `uv run ruff check .`
- All package management uses `uv`: `uv add <pkg>`, `uv lock`, `uv sync`
- Provider model strings use `provider:model-id` format (e.g. `anthropic:claude-sonnet-4-5`, `openrouter:openai/gpt-5`)
