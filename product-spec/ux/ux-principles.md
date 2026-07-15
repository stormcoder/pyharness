# Memory UX — UX Principles & Interaction Rules

> Rules and heuristics governing every memory-aware interaction in the pyharness TUI.
> These principles guide implementation and review. Any deviation must be justified.

---

## Principle 1: Memory Is Ambient, Not Interruptive

**The memory system should inform without demanding attention.**

### Rules
1. **Default to collapsed.** The session startup briefing collapses to a one-line indicator after the user dismisses it or sends their first message. Never block the user from starting work.
2. **Show, don't tell.** Inline citations appear automatically — the user doesn't need to "ask" for memory context. If the agent is drawing from memory, the citation flows naturally into the conversation.
3. **Progressive disclosure.** Memory panel shows tree view by default. Graph and health are one click away. Don't overwhelm with all features at once.
4. **Badges, not banners.** Use compact badges (`🧠 2 refs`) in message headers rather than full blocks until the user engages.
5. **Context indicator is persistent but minimal.** The status bar shows `🧠 12 snippets active` — always visible, never distracting.

### Anti-Patterns
- ❌ Full-screen memory modal on every startup
- ❌ Popups or notifications about memory updates
- ❌ Requiring the user to "load" memory before chatting

---

## Principle 2: Citations Are Traceable and Actionable

**Every memory reference must link back to its source and support user action.**

### Rules
1. **Inline mentions are underlined** with a distinct dotted style. The underline signals "this is from memory" without breaking reading flow.
2. **Hover reveals the source.** A 300ms delay tooltip shows the first two lines of the source drawer.
3. **Citations are navigable.** Every citation card has a [Go to conversation] button that opens the session browser with the source highlighted.
4. **Citations are copyable.** Every citation supports one-click copy of the source content.
5. **Citations are collapsible.** Users can dismiss individual citation cards without losing the inline underline. The badge count in the header updates accordingly.
6. **Facts link to evidence.** Knowledge graph facts show which drawer(s) they were extracted from. Clicking a fact source opens the source.

### Anti-Patterns
- ❌ Citations that say "based on previous discussion" without linking to *which* discussion
- ❌ Memory references that can't be traced back to source
- ❌ Citations that take up half the chat viewport without collapse support

---

## Principle 3: The User Controls Memory Scope

**Users choose what's remembered, what's loaded, and what's forgotten.**

### Rules
1. **Per-project isolation.** Memory is scoped to the current project wing by default. Cross-project references are possible but require explicit action.
2. **Configurable startup scope.** `pyharness.json` can configure: `memory.loadRecentDays` (default: 14), `memory.loadMaxDrawers` (default: 50), `memory.autoBriefing` (default: true).
3. **Explicit add.** Users can add facts manually with `/memory remember "fact"` — these are never inferred without user intent.
4. **Explicit delete.** Users can forget individual drawers (`/memory forget drawer-42`) or clear all project memory (`/memory clear`). Both require confirmation.
5. **Mining is opt-in.** Project mining (`/mine`) is not automatic on first launch. The user must explicitly start it.
6. **Auto-mining is configurable.** `memory.autoMine` in config controls whether file changes trigger automatic re-indexing. Default: off.

### Anti-Patterns
- ❌ Auto-mining without asking first
- ❌ Silently remembering everything the user says
- ❌ No way to delete or reset memory

---

## Principle 4: Memory Search Is Fast and Semantic

**Finding past conversations should feel instant and intuitive.**

### Rules
1. **Debounced search.** The search bar debounces at 300ms. Results update as the user types.
2. **Semantic, not keyword.** Search uses MemPalace's embedding-based semantic search. "How did we fix the auth bug?" matches conversations about "authentication middleware refactoring."
3. **Results show relevance.** Each result displays a relevance score (cosine similarity, normalized to 0-1). A small bar visual helps users trust the ranking.
4. **Results are grouped.** Search results group by room (topic) so related conversations cluster together.
5. **Fallback to text search.** If MemPalace is offline or embeddings are unavailable, fall back to SQLite full-text search on session messages.
6. **Search from anywhere.** `/memory search "query"` works in chat input. The Memory panel search bar searches within the panel. Ctrl+m opens the panel with search focused.

### Anti-Patterns
- ❌ Results that take > 1 second to appear
- ❌ Keyword-only search that misses semantic connections
- ❌ No relevance indication — users can't tell *why* a result was shown

---

## Principle 5: The Knowledge Graph Is Visual and Interactive

**Entities and their relationships should be browsable, not just queryable.**

### Rules
1. **Three views, one data.** Relations, Timeline, and Tree views all show the same knowledge graph from different perspectives. Toggle between them freely.
2. **Focus follows selection.** Selecting a node in the graph re-centers the view and shows its immediate neighborhood (configurable hop count, default: 2).
3. **Edges show relationship type.** Every edge is labeled (e.g., "uses", "depends_on", "contains"). Labels are always visible at reasonable zoom levels.
4. **Nodes are color-coded by type.** Class/Module (purple), Technology (green), Concept (yellow), File (blue). The legend is always visible.
5. **Facts are sourced.** Every fact in the KG shows which drawer(s) it was extracted from. This builds trust.
6. **Node size = importance.** Number of edges roughly determines node visual weight. High-degree nodes are larger.

### Anti-Patterns
- ❌ A static, unlabeled graph that can't be navigated
- ❌ Nodes with no indication of what they represent
- ❌ Missing source attribution for facts

---

## Principle 6: Memory Is Safe by Default

**Memory features must never leak sensitive information or break the user's trust.**

### Rules
1. **Local-first.** All memory is stored locally via MemPalace. No cloud upload unless the user explicitly configures a remote sync target.
2. **No secrets in memory.** The mining process respects `.gitignore` and a configurable `memory.excludePatterns` list. Never index `.env`, credentials, or API key files.
3. **Memory is project-scoped.** Session content from project A is never visible when working in project B unless the user explicitly creates a cross-wing tunnel.
4. **Clear is irreversible.** The "Clear Memory" action shows a prominent warning: "This will permanently delete all memory for this project. This cannot be undone. Type the project name to confirm."
5. **Export before clear.** The health dashboard offers "Export Memory" before "Clear All Memory" to encourage backup.
6. **Agent diary is private.** Each agent's diary entries are visible to the user but not injected into other agents' context without explicit request.

### Anti-Patterns
- ❌ Silent cloud sync of conversation history
- ❌ Indexing `.env` files or secrets
- ❌ Cross-project memory leakage
- ❌ One-click delete without confirmation

---

## Principle 7: Offline Is Graceful

**Memory features degrade, not break, when MemPalace is unavailable.**

### Rules
1. **Clear offline indicator.** Red "● Offline" badge in the Memory header. Greyed-out tree. "MemPalace not reachable" message.
2. **Search fallback.** When MemPalace is offline, `/memory search` falls back to SQLite full-text search on local session data.
3. **No blocking.** Session startup skips the briefing if MemPalace is unreachable. The user can still chat.
4. **Retry button.** The offline state includes a [Retry] button to attempt reconnection.
5. **Cache last state.** The Memory panel shows the last known state (greyed out) so the user can still see what *was* there.
6. **Queue writes.** If the user adds a fact while offline, queue it and write when MemPalace reconnects.

### Anti-Patterns
- ❌ Crashing or hanging when MemPalace is down
- ❌ Silent failure — user doesn't know memory is unavailable
- ❌ Losing queued writes on reconnect failure

---

## Principle 8: Keyboard-Navigable

**Everything in memory UI must be reachable without a mouse.**

### Rules
1. **Tab navigation.** The Memory tab is part of the side panel tab cycle: Shift+Tab cycles through Sessions → File Tree → Tools → Memory.
2. **Direct access.** `Ctrl+m` toggles the Memory panel open/closed and focuses the search bar.
3. **Tree navigation.** Arrow keys: ↑↓ to move between items, → to expand, ← to collapse, Enter to select.
4. **Graph navigation.** Arrow keys to move between nodes, +/− to zoom, Enter to select and focus.
5. **Citation navigation.** Tab to move focus into citation cards. Enter on [Go to conversation] to navigate to source.
6. **All commands keyboard-accessible.** Every action (mine, search, clear, add fact) has a `/memory` slash command equivalent.
7. **Esc closes.** Esc dismisses tooltips, collapses citation cards, and closes overlays. Esc from Memory panel returns focus to chat input.

### Anti-Patterns
- ❌ Mouse-only interactions (drag in graph, right-click context menus without keyboard equivalents)
- ❌ No way to reach the Memory panel via keyboard

---

## Principle 9: Feedback Is Immediate and Clear

**Every memory action produces visible, understandable feedback.**

### Rules
1. **Mining shows progress.** A progress bar with file count, drawers created, and entities extracted.
2. **Search shows count.** "Found 3 results" header. Empty state: "No results for 'query'. Try different keywords."
3. **Add fact confirms.** "✓ Stored: 'we use pydantic v2 for all config'" — brief, clear, includes what was stored.
4. **Delete confirms.** "✗ Forgotten: 'auth-middleware discussion from July 10'" — shows what was deleted so user can verify.
5. **Sync shows delta.** "Synced: 3 updated, 0 orphaned" — shows what changed.
6. **Errors are actionable.** "Error: MemPalace connection refused. Is `mempalace` running? [Retry] [Learn More]" — explains what happened and what to do.

### Anti-Patterns
- ❌ Silent success — user doesn't know if the action worked
- ❌ Vague errors: "Something went wrong"
- ❌ No progress indication for long-running operations

---

## Principle 10: Memory Awareness Is Not Surveillance

**The memory system should feel like a helpful assistant, not a surveillance tool.**

### Rules
1. **Transparency.** The briefing explicitly shows "what we know" so the user can see exactly what's being remembered. No hidden state.
2. **Opt-in intimacy.** The "From Last Session" section shows only the user's own session content. Cross-user memory is never loaded without explicit sharing configuration.
3. **Tone is neutral and helpful.** "Welcome back. Last session: July 12." — not "I've been watching your work."
4. **Memory is local.** The phrase "stored locally" appears in the first-time setup to reassure users their data stays on their machine.
5. **No personality inference.** The knowledge graph extracts code entities, not personality traits or behavior patterns.

### Anti-Patterns
- ❌ "I noticed you've been struggling with..." (unsolicited analysis)
- ❌ Hiding what's being remembered from the user
- ❌ Anthropomorphizing: "I remember you told me..." — prefer "Based on our July 10 discussion..."

---

## Summary: Interaction Decision Matrix

| Situation | Action | Rationale |
|-----------|--------|-----------|
| First launch, no memory | Show setup wizard, don't auto-mine | Principle 3: user controls scope |
| Startup with history | Show briefing (collapsible) | Principle 1: ambient, not interruptive |
| Agent references memory | Auto-add citation card | Principle 2: traceable and actionable |
| User dismisses briefing | Collapse to compact bar | Principle 1: don't block the user |
| MemPalace offline | Grey out panel, show retry | Principle 7: graceful degradation |
| User searches memory | Debounced semantic search | Principle 4: fast and semantic |
| User adds a fact | Show inline confirmation | Principle 9: immediate feedback |
| User clears memory | Require project name confirmation | Principle 6: safe by default |
| Mining in progress | Show progress bar, allow cancel | Principle 9: visible feedback |
| Keyboard-only navigation | Full keyboard support for all actions | Principle 8: keyboard-navigable |
