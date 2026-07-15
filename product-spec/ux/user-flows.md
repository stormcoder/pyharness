# Memory UX — User Flows

## 1. Session Startup: Wake-Up & Context Loading

```mermaid
flowchart TD
    A[User starts pyharness in project] --> B[pyharness calls `mempalace wake-up`]
    B --> C{MemPalace reachable?}
    C -->|Yes| D[Load project-scoped context]
    C -->|No| E[Skip memory; show offline badge]
    D --> F[Retrieve: recent diary entries, KG facts, relevant drawers]
    F --> G[Render Memory Briefing banner in chat]
    G --> H[User sees: "Welcome back. 3 topics from last session, 2 open threads..."]
    H --> I{User action?}
    I -->|Continue| J[Load last session or start new]
    I -->|Explore briefing| K[Click/hover briefing items to expand]
    I -->|Dismiss| L[Briefing collapses to compact indicator]
    E --> J
```

## 2. Memory Side Panel: Browsing & Searching Memory

```mermaid
flowchart TD
    A[User opens Memory tab in side panel] --> B[Show tree view: Wings, Rooms, Drawers]
    A --> C[Show Memory header with stats]
    C --> D["12 wings · 47 rooms · 1.2k drawers · last synced 2m ago"]
    B --> E["wing: pyharness (project)"]
    E --> F["room: auth-middleware"]
    F --> G["drawer: 'On July 10, we decided to use...' "]
    G --> H{User action on drawer?}
    H -->|Expand| I[Show full content inline]
    H -->|Cite| J[Insert citation into chat input: `@memory:auth-middleware:drawer-42`]
    H -->|Copy| K[Copy content to clipboard]
    B --> L[User types filter: /search "auth bug" ]
    L --> M[Semantic search results populate tree]
    M --> N[Results ranked by relevance, grouped by room]
```

## 3. Memory-Aware Chat: Citations & Inline Context

```mermaid
flowchart TD
    A[Agent generates response referencing memory] --> B{Type of memory reference?}
    B -->|Inline mention| C["Based on our discussion on July 10th about the auth middleware..."]
    B -->|Citation block| D[Show citation badge: `📎 July 10 · auth-middleware · drawer-42`]
    B -->|Context indicator| E["🟢 Context loaded: 12 memory snippets active (Ctrl+m to view)"]
    C --> F[User hovers mention; tooltip shows source snippet]
    D --> G[User clicks citation; jumps to drawer in Memory panel]
    E --> H[User clicks indicator; Memory panel opens with loaded context highlighted]
    F --> I[User can navigate: "Go to that conversation"]
    G --> I
    H --> I
```

## 4. Knowledge Graph: Exploration Flow

```mermaid
flowchart TD
    A[User opens Knowledge Graph view] --> B{Graph mode?}
    B -->|Tree view| C[Hierarchical: Wing → Room → Drawer → linked entities]
    B -->|Entity view| D["Flat list of entities: AuthConfig, Middleware, pydantic v2"]
    B -->|Timeline view| E["Chronological: July 10 → July 12 → July 14"]
    C --> F[Click entity: "AuthConfig"]
    D --> F
    E --> F
    F --> G[Show entity detail panel]
    G --> H["Facts: AuthConfig → uses → pydantic v2"]
    G --> I["Related drawers: 3 conversations"]
    G --> J[User action: Add fact, view source, follow relation]
```

## 5. Memory Management: Mining & Health

```mermaid
flowchart TD
    A[Memory management access] --> B{Action?}
    B -->|Mine project| C[User runs `/mine` or clicks "Mine Project"]
    B -->|Clear memory| D[User runs `/memory-clear`]
    B -->|View health| E[User opens Memory header → Stats]
    C --> F[pyharness calls `mempalace mine .`]
    F --> G[Progress: "Indexing 427 files... 142 new drawers"]
    G --> H[Memory tab refreshes with new content]
    D --> I[Confirmation dialog: "Delete all memory for this project?"]
    I -->|Confirm| J[`mempalace sync --apply` + delete wing]
    I -->|Cancel| K[No change]
    J --> L[Memory tab shows empty state]
    E --> M[Show: wings, rooms, drawers, storage size, last mine/sync time]
```

## 6. Cross-Session Search

```mermaid
flowchart TD
    A[User opens Session Search] --> B[Command: `/sessions "authentication"`]
    B --> C[Semantic search across all sessions for this project]
    C --> D[Results grouped by session]
    D --> E["Session: fix-login-bug (July 10) — 3 matches"]
    E --> F["Session: refactor-auth (July 12) — 8 matches"]
    F --> G{User action?}
    G -->|Resume session| H[Load that session]
    G -->|Preview| I[Show chat excerpt with matches highlighted]
    I --> J[User can scroll through conversation around match]
```

## 7. Inline Memory Commands

```mermaid
flowchart TD
    A[User types `/memory ` in chat input] --> B{Subcommand?}
    B -->|search| C["Search memory: `/memory \"how did we fix the auth bug?\"`"]
    B -->|remember| D["Add fact: `/memory remember 'we use pydantic v2 for all config'`"]
    B -->|forget| E["Delete: `/memory forget drawer-42`"]
    B -->|mine| F["Mine: `/memory mine` (full) or `/memory mine --since HEAD~10`"]
    B -->|briefing| G["Show: `/memory briefing` — re-display startup briefing"]
    B -->|status| H["Status: `/memory status` — wing/room/drawer counts"]
    C --> I[Results render as expandable cards in chat]
    D --> J["Confirm: 'Stored: we use pydantic v2 for all config'"]
    E --> K["Confirm: 'Forgotten: drawer-42'"]
    F --> L[Progress bar shows indexing progress]
    G --> M[Briefing banner re-renders]
    H --> N[Stats card renders]
```

