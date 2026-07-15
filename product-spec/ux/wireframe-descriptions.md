# Memory UX — Wireframe Descriptions

> Text-based screen descriptions for every memory-related UI surface in the pyharness TUI.
> These describe layout, components, and behavior without visual rendering.
> Pairs with `user-flows.md` (Mermaid diagrams) and `ux-principles.md` (interaction rules).

---

## Screen 1: Side Panel — Memory Tab

### Context
The existing side panel has tabs: **Sessions**, **File Tree**, **Tools**. A fourth tab, **Memory**, is added.

### Layout

```
┌─ Side Panel (260×748) ────────────────────────────┐
│ [Sessions] [File Tree] [Tools] [Memory]  ← tabs   │
├────────────────────────────────────────────────────┤
│ ┌─ Memory Header ─────────────────────────────────┐│
│ │ 🧠 Memory · pyharness                  [Stats]  ││
│ │ 12 wings · 47 rooms · 1.2k drawers              ││
│ │ Last synced: 2 min ago                          ││
│ └─────────────────────────────────────────────────┘│
│                                                    │
│ 🔍 [ Search memory...                        ]     │
│                                                    │
│ ┌─ Wing: pyharness (current) ─────────────────────┐│
│ │  ▼ room: auth-middleware         12 drawers     ││
│ │  ▶ room: mcp-config              8 drawers      ││
│ │  ▼ room: tui-layout              5 drawers      ││
│ │    │ On July 10 — We decided to...              ││
│ │    │ On July 12 — The side panel...             ││
│ │    │ On July 14 — Refactored the...             ││
│ │    └ ... (2 more)                               ││
│ │  ▶ room: sessions              25 drawers      ││
│ └─────────────────────────────────────────────────┘│
│                                                    │
│ ┌─ Knowledge Graph ───────────────────────────────┐│
│ │  ▶ AuthConfig → uses → pydantic v2              ││
│ │  ▶ Middleware → depends_on → AuthConfig         ││
│ │  ▶ auth-module → contains → Middleware          ││
│ │  [+ New Fact]                                   ││
│ └─────────────────────────────────────────────────┘│
│                                                    │
│ ┌─ Footer ────────────────────────────────────────┐│
│ │ `/memory search <q>` · `/mine` · `/memory stat` ││
│ │ Ctrl+m toggle memory panel                      ││
│ └─────────────────────────────────────────────────┘│
├────────────────────────────────────────────────────┤
│ ┌─ Quick Actions ─────────────────────────────────┐│
│ │ [Mine Project]  [View Briefing]  [Clear Memory] ││
│ └─────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────┘
```

### Component Details

#### Memory Header
- **Title bar**: "🧠 Memory · {wing_name}" — current project name from MemPalace wing.
- **Stats row**: "12 wings · 47 rooms · 1.2k drawers" — counts with hover tooltip showing breakdown.
- **Status indicator**: Green dot "● Synced 2m ago" / Yellow "◐ Syncing..." / Red "● Offline" / Grey "○ Not connected"
- **[Stats]** button: Opens a full-screen overlay with detailed health metrics (see Screen 5).

#### Search Bar
- `🔍 [ Search memory... ]` — Type to filter by semantic search.
- Debounced (300ms). Results replace tree content below.
- No search submitted yet: show wing/room/drawer tree.
- Active search: results grouped by room, ranked by cosine similarity, relevance score shown as small bar.

#### Wing/Room/Drawer Tree
- **Top level**: Wings. Default-expanded: current project wing.
- **Second level**: Rooms within each wing. Alphabetical or by last-modified.
- **Third level**: Drawers within each room. Chronological (newest first).
- **Expand/collapse**: `▶` / `▼` indicators. Enter to toggle.
- **Drawer preview**: First line (truncated to 60 chars) + date + size hint.
- **Selected drawer**: Highlighted (blue border). Detail panel opens below or replaces tree.
- **Right-click / context menu**: Copy, Cite, Delete, Open Source File.

#### Knowledge Graph Section
- Compact section below the drawer tree, collapsible.
- Shows **entities in current scope** (filtered to current wing).
- Each entity row: `▶ EntityName → relation → OtherEntity`
- **[+ New Fact]** button: Opens inline input: "Entity → [predicate] → Entity"
- Scope filter: "Show: [All] [Current Wing] [Current Room]"
- Toggle between: **Relations** / **Timeline** / **Full Graph** (see Screen 4).

#### Footer
- Context-sensitive keybind hints.
- Shows available `/memory` subcommands.

#### Quick Actions Bar
- Three buttons at bottom:
  - **[Mine Project]**: Runs `mempalace mine .` with progress indicator.
  - **[View Briefing]**: Re-displays the session startup briefing (Screen 2).
  - **[Clear Memory]**: Opens confirmation dialog. "Delete all memory for pyharness? This cannot be undone."

### States

| State | Visual |
|-------|--------|
| **Normal** | Tree with wings/rooms/drawers, stats populated |
| **Empty** | "No memory yet. Run `/mine` to index this project." + [Mine Project] button |
| **Searching** | Spinner next to search bar, tree replaced with "Searching..." skeleton |
| **Search-no-results** | "No results for '{query}'. Try different keywords." |
| **Offline** | Header shows red "● Offline". Tree greyed out. "MemPalace not reachable." |
| **Syncing** | Header shows yellow "◐ Syncing...". Quick actions disabled. |
| **Error** | Red banner: "Error loading memory: connection refused. [Retry]" |

---

## Screen 2: Session Startup — Memory Briefing

### Context
When pyharness starts in a project and MemPalace is configured, a "Memory Briefing" banner appears at the top of the chat area before the first user message.

### Layout

```
┌─ Chat Area ──────────────────────────────────────────────────────┐
│                                                                   │
│ ┌─ 🧠 Memory Briefing ──────────────────────────────────────────┐│
│ │ Welcome back. Last session: July 12, 2026 · 12:34 PM          ││
│ │                                                               ││
│ │ ┌─ From Last Session ────────────────────────────────────────┐││
│ │ │ ● "We decided to use pydantic v2 for all config models"    │││
│ │ │ ● "The auth middleware needs refactoring to DI"            │││
│ │ │ ● "Tests are passing for the token validation module"      │││
│ │ └────────────────────────────────────────────────────────────┘││
│ │                                                               ││
│ │ ┌─ Relevant Past Discussions ────────────────────────────────┐││
│ │ │ 📁 auth-middleware (3 conversations, last: July 10)        │││
│ │ │ 📁 session-management (1 conversation, last: July 8)      │││
│ │ │ 📁 tui-layout (2 conversations, last: July 5)              │││
│ │ └────────────────────────────────────────────────────────────┘││
│ │                                                               ││
│ │ ┌─ Knowledge Graph Snapshot ─────────────────────────────────┐││
│ │ │ 5 entities · 12 relations added since last session         │││
│ │ │ New: AuthConfig, TokenValidator, SessionStore              │││
│ │ └────────────────────────────────────────────────────────────┘││
│ │                                                               ││
│ │ [Dismiss]  [Open Memory Panel]  [Load Last Session]           ││
│ └───────────────────────────────────────────────────────────────┘│
│                                                                   │
│ ┌─ Chat messages below... ──────────────────────────────────────┐│
│                                                                   │
```

### Component Details

#### Greeting Row
- "Welcome back. Last session: {date} · {time}" with model and agent used.

#### From Last Session (collapsible)
- Shows key decisions, facts, and open questions from the most recent session.
- Sourced from the agent diary and knowledge graph.
- Each bullet is a **clickable snippet** — hover shows full context; click opens in Memory panel.

#### Relevant Past Discussions (collapsible)
- Rooms with past conversations semantically relevant to the current project state.
- Each row: room name, conversation count, last activity date.
- Click a room to expand and see summarized drawer content.
- Sorted by relevance (cosine similarity to current git branch + recent edits).

#### Knowledge Graph Snapshot
- Summary of entities/relations since last session.
- "N entities · M relations added since last session"
- Lists newly added entity names.

#### Actions
- **[Dismiss]**: Collapses briefing to a compact one-line indicator.
- **[Open Memory Panel]**: Opens the Memory tab in the side panel.
- **[Load Last Session]**: Resumes the most recent session with full context.

### States

| State | Visual |
|-------|--------|
| **First launch** | "Welcome to pyharness! No memory found for this project. Run `/mine` to index your codebase and enable cross-session memory." + [Mine Project] button |
| **Normal (with history)** | Full briefing as shown above |
| **Offline** | "MemPalace is not reachable. Memory features are disabled this session. [Retry]" |
| **Dismissed** | Compact bar: "🧠 3 topics from last session · [Show Briefing]" at chat top |

### Compact Indicator (when briefing dismissed)

```
┌─ 🧠 3 topics from last session · 5 entities loaded · [Show] ─────┐
```

- Always visible as a thin bar at the top of chat when briefing is collapsed.
- Updates in real-time as agent references memory.
- Click **[Show]** to re-expand the full briefing.
- Right-click for context menu: Dismiss permanently, Show briefing, Open Memory panel.

---

## Screen 3: Chat Message — Memory-Aware Citations

### Context
When the agent's response references information from MemPalace, the message styling indicates the memory source.

### Layout

```
┌─ Chat Area ───────────────────────────────────────────────────────┐
│                                                                    │
│  ┌─ User Message ────────────────────────────────────────────────┐│
│  │ You · 2:15 PM                                                 ││
│  │ Can we refactor the auth middleware now?                       ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
│  ┌─ Assistant Message (memory-aware) ────────────────────────────┐│
│  │ Assistant · 2:15 PM  🧠 2 memory refs                         ││
│  │                                                                ││
│  │ Based on our discussion on July 10th about the auth            ││
│  │ middleware, I recall we decided to use dependency injection.   ││
│  │ ^─────────────────────────────────────────────────────^       ││
│  │ ┌─ 📎 July 10 · auth-middleware ─────────────────────────────┐││
│  │ │ "We should refactor AuthMiddleware to accept an injectable  │││
│  │ │  AuthConfig object rather than hardcoding secret_key..."    │││
│  │ │ [Go to conversation]  [Copy]  [Dismiss]                    │││
│  │ └────────────────────────────────────────────────────────────┘││
│  │                                                                ││
│  │ Let me apply that refactoring now.                             ││
│  │                                                                ││
│  │ ┌─ 📎 July 12 · tui-layout ──────────────────────────────────┐││
│  │ │ "The side panel should support four tabs with keyboard      │││
│  │ │  navigation between them."                                  │││
│  │ │ [Go to conversation]  [Copy]  [Dismiss]                    │││
│  │ └────────────────────────────────────────────────────────────┘││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
│  ┌─ Status Bar ───────────────────────────────────────────────────┐│
│  │ 🧠 12 snippets active · Ctrl+m to view · /memory search "..."  ││
│  └────────────────────────────────────────────────────────────────┘│
```

### Component Details

#### Inline Memory Mention
- Agent text that references a past conversation is **underlined with a subtle dotted line** (Textual: `underline` style with dim color).
- Hovering the underlined text shows a **tooltip** with the first two lines of the source drawer.
- Pressing Enter while focused on the underlined text opens the Memory panel to that drawer.

#### Citation Card
- Below the referencing paragraph, a **collapsible card** shows the source context.
- **Header**: "📎 {date} · {room_name}" with an icon indicating the memory type:
  - 📎 = conversation / drawer
  - 🏷️ = knowledge graph fact
  - 📝 = agent diary entry
- **Body**: First ~200 characters of the source content, shown in a dimmed block.
- **Actions**: [Go to conversation] · [Copy] · [Dismiss]
  - **[Go to conversation]**: Opens the Session Browser filtered to that session.
  - **[Copy]**: Copies the source content to clipboard.
  - **[Dismiss]**: Collapses the citation card (leaves the inline underline).

#### Message Header Badge
- Next to the assistant name and timestamp: `🧠 2 memory refs`
- Indicates how many memory sources were cited in this response.
- Hover to see a list of the sources.

#### Status Bar Memory Indicator
- Persistent in the status bar when memory context is loaded:
  - `🧠 12 snippets active · Ctrl+m to view`
- Click or press Ctrl+m to open the Memory panel with loaded snippets highlighted.

### States

| State | Visual |
|-------|--------|
| **No memory refs** | No badge, no citations, no status indicator |
| **Memory refs present** | Badge + underline + citation cards |
| **Citation collapsed** | Underline remains, citation card hidden, badge still shows count |
| **Citation expanded** | Full card visible |
| **Memory panel open** | Citation cards link to highlighted items in panel |

---

## Screen 4: Knowledge Graph Visualization (Full-Screen Overlay)

### Context
Opened from the Memory tab by clicking "Full Graph" or via `/memory graph`. A modal/overlay displaying the knowledge graph visually.

### Layout

```
┌─ Knowledge Graph — pyharness ─────────────────────────────────────┐
│ 🔍 [ Filter entities... ]     [Relations] [Timeline] [Tree]       │
│                                                                    │
│ ┌─ Graph Canvas ───────────────────────────┬─ Detail Panel ──────┐│
│ │                                          │                      ││
│ │    [AuthConfig] ──uses──▶ [pydantic v2]  │  Entity: AuthConfig │
│ │         │                                │                      │
│ │    depends_on                            │  Relations:          │
│ │         │                                │  → uses pydantic v2 │
│ │         ▼                                │  → defined in        │
│ │    [Middleware] ──contains──▶ [auth.py]  │    src/auth/config   │
│ │         │                                │                      │
│ │    implements                            │  Sources:            │
│ │         │                                │  📁 July 10 session  │
│ │         ▼                                │  📁 July 12 session  │
│ │    [TokenValidator]                      │                      │
│ │                                          │  [+ Add Fact]        │
│ │                                          │  [View Sources]      │
│ │                                          │                      │
│ └──────────────────────────────────────────┴──────────────────────┘│
│                                                                    │
│ ┌─ Footer ────────────────────────────────────────────────────────┐│
│ │ ← → ↑ ↓ navigate · + zoom in · - zoom out · Enter select       ││
│ │ /memory add "AuthConfig uses pydantic v2" · Esc close           ││
│ └────────────────────────────────────────────────────────────────┘│
```

### Component Details

#### Mode Tabs
- **[Relations]**: Entity-relationship graph (default). Nodes = entities, edges = relationships.
- **[Timeline]**: Chronological list of facts. "July 10 — AuthConfig created. July 12 — Middleware refactored..."
- **[Tree]**: Hierarchical wing → room → drawer → linked entities. Same as the Memory tab tree view.

#### Graph Canvas (Relations mode)
- **Nodes**: Rectangles with entity name, color-coded by type:
  - 🟣 Class/Module (purple)
  - 🟢 Technology/Library (green)
  - 🟡 Concept/Decision (yellow)
  - 🔵 File (blue)
- **Edges**: Arrows with relationship labels. Width = confidence/usage count.
- **Navigation**: Arrow keys to move focus between nodes. Enter to select.
- **Zoom**: `+` / `-` keys or mouse wheel.
- **Focus mode**: Select a node → graph re-centers showing only N hops of relations.

#### Detail Panel
- **Selected entity** name and type.
- **Relations list**: All incoming and outgoing relations with direction arrows.
- **Sources**: Drawers where this fact was extracted or discussed.
- **[+ Add Fact]**: Opens inline input to add a new relation.
- **[View Sources]**: Opens the source drawers in the Memory panel.

#### Timeline Mode
- Vertical timeline with date headers.
- Each entry: date → fact (e.g., "AuthConfig created").
- Click any entry to jump to the source conversation.

### States

| State | Visual |
|-------|--------|
| **Empty** | "No knowledge graph data. Run `/mine` to extract facts from your codebase." |
| **Loading** | Skeleton nodes with pulsing animation |
| **Large graph** | Zoomed out view with cluster labels; zoom in to see individual nodes |
| **Search active** | Non-matching nodes dimmed to 30% opacity; matching nodes highlighted |

---

## Screen 5: Memory Health Dashboard (Overlay)

### Context
Opened from the Memory tab header **[Stats]** button or `/memory status`. Shows detailed storage and health metrics.

### Layout

```
┌─ Memory Health — pyharness ───────────────────────────────────────┐
│                                                                    │
│ ┌─ Overview ──────────────────────────────────────────────────────┐│
│ │ 🧠 MemPalace v2.1.0  ·  Connected  ·  Local storage            ││
│ │ Storage: 14.2 MB across 1,247 drawers                          ││
│ │ Last mine: July 14, 2026 · 2:15 PM  (427 files, 142 new)      ││
│ │ Last sync: July 14, 2026 · 2:16 PM  (0 orphaned, 3 updated)   ││
│ └────────────────────────────────────────────────────────────────┘││
│                                                                    ││
│ ┌─ Wings ─────────────────────────────────────────────────────────┐││
│ │  pyharness           847 drawers · 32 rooms · 14.2 MB   [→]   ││
│ │  webapp              234 drawers · 12 rooms · 3.1 MB    [→]   ││
│ │  api-server          166 drawers ·  8 rooms · 2.4 MB    [→]   ││
│ └────────────────────────────────────────────────────────────────┘││
│                                                                    ││
│ ┌─ Rooms (pyharness) ─────────────────────────────────────────────┐││
│ │  auth-middleware     142 drawers · last: July 14        [→]    ││
│ │  sessions             89 drawers · last: July 12        [→]    ││
│ │  tui-layout           76 drawers · last: July 14        [→]    ││
│ │  mcp-config           54 drawers · last: July 10        [→]    ││
│ │  ... (28 more)                                                ││
│ └────────────────────────────────────────────────────────────────┘││
│                                                                    ││
│ ┌─ Knowledge Graph ───────────────────────────────────────────────┐│
│ │  47 entities · 128 relationships · 23 facts valid now          ││
│ │  Top entities: AuthConfig (12 edges), Middleware (9 edges)     ││
│ │  [View Full Graph]                                             ││
│ └────────────────────────────────────────────────────────────────┘││
│                                                                    ││
│ ┌─ Actions ───────────────────────────────────────────────────────┐│
│ │ [Mine Project Now]  [Sync Orphans]  [Clear All Memory]         ││
│ │ [Export Memory]  [Compact Storage]                             ││
│ └────────────────────────────────────────────────────────────────┘││
│                                                                    │
│ [Close]                                                           │
└────────────────────────────────────────────────────────────────────┘
```

### Component Details

#### Overview Section
- MemPalace version and connection status.
- Total storage size across all drawers.
- Last mine: timestamp, files processed, new drawers created.
- Last sync: timestamp, orphans cleaned, updated count.

#### Wings List
- Each wing as a row: name, drawer count, room count, storage size.
- **[→]** button: drills into that wing's rooms.

#### Rooms List
- Only shows when a wing is selected (or defaults to current project).
- Room name, drawer count, last activity date.
- **[→]** button: opens that room in the Memory tab tree.

#### Knowledge Graph Stats
- Entity and relationship counts.
- Top entities by edge count.
- **[View Full Graph]** button: opens Screen 4.

#### Actions Section
- **[Mine Project Now]**: Re-runs `mempalace mine .`
- **[Sync Orphans]**: Runs `mempalace sync` to clean up stale references.
- **[Clear All Memory]**: Destructive — confirmation required.
- **[Export Memory]**: Exports as JSON for backup or migration.
- **[Compact Storage]**: VACUUM-equivalent for MemPalace.

---

## Screen 6: Memory Search — Inline Results (Chat)

### Context
When the user types `/memory search "query"` in the chat input, results render as expandable cards in the chat area.

### Layout

```
┌─ Chat Area ───────────────────────────────────────────────────────┐
│                                                                    │
│  ┌─ Command ─────────────────────────────────────────────────────┐│
│  │ > /memory search "auth middleware dependency injection"       ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
│  ┌─ Memory Search Results (3 found) ─────────────────────────────┐│
│  │                                                                ││
│  │  ┌─ Result 1 (0.94) — auth-middleware ──────────────────────┐ ││
│  │  │ July 10, 2026 · Session: refactor-auth-module            │ ││
│  │  │ "We should refactor AuthMiddleware to accept an          │ ││
│  │  │  injectable AuthConfig object rather than hardcoding..." │ ││
│  │  │ [Resume Session]  [Show in Memory]  [Copy]              │ ││
│  │  └──────────────────────────────────────────────────────────┘ ││
│  │                                                                ││
│  │  ┌─ Result 2 (0.87) — auth-middleware ──────────────────────┐ ││
│  │  │ July 8, 2026 · Session: fix-login-bug                    │ ││
│  │  │ "The middleware is tightly coupled. We need to extract..."│ ││
│  │  │ [Resume Session]  [Show in Memory]  [Copy]              │ ││
│  │  └──────────────────────────────────────────────────────────┘ ││
│  │                                                                ││
│  │  ┌─ Result 3 (0.81) — tui-layout ───────────────────────────┐ ││
│  │  │ July 5, 2026 · Session: tui-redesign                     │ ││
│  │  │ "Side panel should show four tabs including a Memory..." │ ││
│  │  │ [Resume Session]  [Show in Memory]  [Copy]              │ ││
│  │  └──────────────────────────────────────────────────────────┘ ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
```

### Component Details

#### Search Command
- Rendered as a distinct command message (like a user message but with a command badge).
- Shows the full `/memory search "query"` text.

#### Results Container
- Header: "Memory Search Results (N found)"
- Each result card:
  - **Relevance score** (cosine similarity, 0-1) as a small bar or number.
  - **Room name** — click to open that room in the Memory panel.
  - **Date and session name** — timestamp and session label.
  - **Content preview** — first ~200 characters of the drawer.
  - **Actions**: [Resume Session] [Show in Memory] [Copy]
- Results sorted by relevance (highest first).
- Only shows results above a minimum similarity threshold (configurable, default 0.5).

---

## Screen 7: Session Browser — Memory-Enhanced

### Context
The `/sessions` overlay (already designed in mockups) gains a semantic search bar and memory-aware groupings.

### Changes to Existing `/sessions` Screen

```
┌─ Session Browser ─────────────────────────────────────────────────┐
│ 🔍 [ Search sessions by topic...  ]  🔍 semantic search           │
│                                                                    │
│ ┌─ ACTIVE SESSIONS ───────────────────────────────────────────────┐│
│ │ ▶ refactor-auth-module · Build · 24 msgs · 2 min ago           ││
│ │   🧠 3 memory refs · auth-middleware                            ││
│ │                                                                 ││
│ │ ● fix-login-bug · Build · 8 msgs · 1 hr ago                    ││
│ │   🧠 1 memory ref · auth-middleware                             ││
│ │                                                                 ││
│ │ ● plan-database-schema · Plan · 42 msgs · 3 hr ago             ││
│ │   (no memory refs)                                              ││
│ └─────────────────────────────────────────────────────────────────┘│
│                                                                    │
│ ┌─ ARCHIVED ──────────────────────────────────────────────────────┐│
│ │ ● add-ci-pipeline · Build · 18 msgs · 5 days ago               ││
│ │ ● initial-setup · Build · 56 msgs · 2 weeks ago                ││
│ └─────────────────────────────────────────────────────────────────┘│
│                                                                    │
│ ┌─ MEMORY TOPICS (pyharness) ─────────────────────────────────────┐│
│ │ ▶ auth-middleware — 4 conversations (most active)              ││
│ │ ▶ tui-layout — 3 conversations                                 ││
│ │ ▶ session-management — 2 conversations                         ││
│ └─────────────────────────────────────────────────────────────────┘│
│                                                                    │
│ Enter resume · d delete · /search filter · Esc close              │
└────────────────────────────────────────────────────────────────────┘
```

### New Elements

#### Semantic Search Bar
- Replaces or augments the existing text filter.
- Matches against session titles, message content (via MemPalace), and topics.
- When user types, results filter in real-time (debounced).

#### Memory Ref Badges
- Each session row shows `🧠 N memory refs` if the session has drawers in MemPalace.
- Shows the primary room(s) the session belongs to.
- Hover to see: "3 drawers in auth-middleware, 1 in tui-layout"

#### Memory Topics Section (new)
- Below the archived list, a "MEMORY TOPICS" section groups sessions by room.
- Each row: room name, conversation count, activity indicator.
- Click to filter sessions to that topic.
- Sorted by activity (most conversations first).

---

## Screen 8: Startup Flow — First-Time Memory Setup

### Context
When pyharness launches for the first time in a project with MemPalace installed but no project memory exists.

### Layout

```
┌─ Chat Area ───────────────────────────────────────────────────────┐
│                                                                    │
│ ┌─ 🧠 Welcome to MemPalace ─────────────────────────────────────┐ │
│ │                                                                │ │
│ │  MemPalace gives pyharness cross-session memory:              │ │
│ │  • Remember what was discussed across restarts                │ │
│ │  • Build a knowledge graph of your codebase                   │ │
│ │  • Search past conversations by topic                         │ │
│ │  • Each agent writes a diary of learnings                     │ │
│ │                                                                │ │
│ │  To get started, index your project:                          │ │
│ │                                                                │ │
│ │  ┌─ ⚡ Quick Setup ──────────────────────────────────────────┐│ │
│ │  │                                                           ││ │
│ │  │  [✓] MemPalace detected (v2.1.0)                         ││ │
│ │  │  [ ] Mine this project (est. 15s for 427 files)          ││ │
│ │  │  [ ] Enable auto-mine on file changes                     ││ │
│ │  │  [ ] Load existing codebase knowledge graph               ││ │
│ │  │                                                           ││ │
│ │  │  [Start Mining]                                          ││ │
│ │  └──────────────────────────────────────────────────────────┘│ │
│ │                                                                │ │
│ │  [Skip for now]  (memory features will be limited)            │ │
│ └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
```

### Component Details

#### Welcome Message
- Explains what MemPalace does in 3-4 bullet points.
- Friendly, not overwhelming.

#### Quick Setup Checklist
- **[✓] MemPalace detected**: Auto-checked if MemPalace is installed and reachable.
- **[ ] Mine this project**: Estimated time based on file count.
- **[ ] Enable auto-mine**: Watch files and auto-index changes (toggle, optional).
- **[ ] Load knowledge graph**: Extract entities/relations from existing codebase (runs `mempalace mine .` with KG extraction).

#### Actions
- **[Start Mining]**: Begins the mining process with a progress bar.
- **[Skip for now]**: Dismisses; memory features show "not configured" state.

---

## Screen 9: Mining Progress (Chat Overlay)

### Layout

```
┌─ Chat Area ───────────────────────────────────────────────────────┐
│                                                                    │
│  ┌─ 🧠 Mining Project ──────────────────────────────────────────┐│
│  │                                                                ││
│  │  ████████████████░░░░░░  78%                                  ││
│  │  334 / 427 files indexed                                       ││
│  │  89 new drawers created                                        ││
│  │  12 entities extracted                                         ││
│  │                                                                ││
│  │  Current: src/pyharness/tui/widgets/sidebar.py                ││
│  │                                                                ││
│  │  [Cancel]                                                     ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
```

### Component Details

- **Progress bar**: Textual `ProgressBar` widget.
- **Stats**: Files indexed, new drawers, entities extracted — updates in real-time.
- **Current file**: Shows the file currently being processed, rotating for visual feedback.
- **[Cancel]**: Stops mining. Partial results are saved.
- When complete: auto-dismisses and refreshes Memory panel.

---

## Design Token Integration

All memory UI elements reuse the existing pyharness color palette (Tokyo Night theme):

| Element | Token | Value |
|---------|-------|-------|
| Memory header bg | `--surface-header` | `#161b22` |
| Memory tab active | `--accent-primary` | `#388bfd` |
| Citation card bg | `--surface-raised` | `#1f2937` |
| Citation underline | `--memory-link` | `#a5d6ff` (new token) |
| Entity node (class) | `--kg-class` | `#d2a8ff` |
| Entity node (tech) | `--kg-tech` | `#7ee787` |
| Entity node (concept) | `--kg-concept` | `#d29922` |
| Entity node (file) | `--kg-file` | `#58a6ff` |
| Relevance bar | `--accent-success` | `#3fb950` |
| Briefing banner bg | `--surface-elevated` | `#0d1117` |
| Offline indicator | `--status-error` | `#f85149` |
| Syncing indicator | `--status-warning` | `#d29922` |
| Online indicator | `--status-success` | `#3fb950` |

New semantic tokens:
- `--memory-link`: `#a5d6ff` — Citation inline underlines and memory reference links
- `--memory-badge-bg`: `#1a2332` — Background for memory count badges
- `--memory-highlight`: `#58a6ff33` — Highlight color for memory search matches
