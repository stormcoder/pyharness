# pyharness

A Python-native terminal UI LLM harness — multi-provider AI coding agent for the terminal.

Built with [Textual](https://textual.textualize.io/) for the TUI, [LangChain](https://github.com/langchain-ai/langchain) + [OpenRouter](https://openrouter.ai/) for universal LLM provider access, [LangGraph](https://github.com/langchain-ai/langgraph) for the agent runtime, and [MemPalace](https://github.com/MemPalace/mempalace) for persistent semantic memory.

## Features (planned)

- **TUI** — Multi-panel terminal interface with chat, side panels, and command palette
- **Agents** — Build/Plan/General/Explore agents with permission controls
- **Sessions** — Git-backed undo/redo, persistent chat history, session resume
- **Multi-provider** — 200+ LLM models via LangChain (18 first-party packages) + OpenRouter
- **MCP** — Local (stdio) and remote (HTTP/SSE) MCP server support
- **Skills** — Reusable SKILL.md instruction files (progressive disclosure)
- **Plugins** — Python hook system for tool interception, notifications, custom behavior
- **Custom commands** — `/slash` command templates with argument substitution

## Quick Links

- [Specification](SPEC.md) — Full feature spec, architecture, and implementation plan
- [Mockups](docs/mockups/) — SVG TUI layout and system architecture diagrams

## Status

**Phase 0 — Specification.** No code yet.

See [SPEC.md](SPEC.md) for the detailed implementation plan.
