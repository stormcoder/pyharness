# Memory UX — Design Tokens

> Color, typography, spacing, and component tokens for the MemPalace integration in pyharness TUI.
> Extends the existing Tokyo Night theme palette with memory-specific semantic tokens.

---

## 1. Color Tokens

### 1.1 New Semantic Tokens (Memory-Specific)

| Token | Value | Usage |
|-------|-------|-------|
| `--memory-link` | `#a5d6ff` | Citation underline, memory reference links |
| `--memory-link-hover` | `#c9e4ff` | Memory link on hover/focus |
| `--memory-badge-bg` | `#1a2332` | Background for memory count badges |
| `--memory-badge-text` | `#a5d6ff` | Text for memory count badges |
| `--memory-highlight` | `#58a6ff33` | Match highlight in memory search results |
| `--memory-card-bg` | `#1a2332` | Citation card and briefing card background |
| `--memory-card-border` | `#2d3a4a` | Citation card border |
| `--memory-drawer-preview` | `#8b949e` | Drawer preview text in tree |
| `--memory-drawer-date` | `#484f58` | Date text for drawers |
| `--memory-header-bg` | `#161b22` | Memory header background |
| `--memory-empty-text` | `#484f58` | Empty state text in memory views |
| `--memory-relevance-bar` | `#3fb950` | Relevance score bar in search results |
| `--memory-relevance-bar-bg` | `#21262d` | Relevance score bar track |
| `--memory-wing-active` | `#388bfd` | Active/current wing indicator |
| `--memory-progress-fill` | `#388bfd` | Mining progress bar fill |
| `--memory-progress-track` | `#21262d` | Mining progress bar track |

### 1.2 Knowledge Graph Entity Colors

| Token | Value | Entity Type |
|-------|-------|-------------|
| `--kg-class` | `#d2a8ff` | Classes, modules, packages |
| `--kg-tech` | `#7ee787` | Technologies, libraries, frameworks |
| `--kg-concept` | `#d29922` | Concepts, decisions, patterns |
| `--kg-file` | `#58a6ff` | Files, directories |
| `--kg-function` | `#ffa657` | Functions, methods |
| `--kg-edge` | `#484f58` | Relationship edges (graph view) |
| `--kg-edge-active` | `#8b949e` | Relationship edge on hover/focus |
| `--kg-node-focus` | `#388bfd` | Node focus ring |

### 1.3 Memory Status Indicators

| Token | Value | Status |
|-------|-------|--------|
| `--memory-online` | `#3fb950` | Connected & synced |
| `--memory-syncing` | `#d29922` | Currently syncing |
| `--memory-offline` | `#f85149` | Not reachable |
| `--memory-disabled` | `#484f58` | Not configured |

---

## 2. Typography Tokens

### 2.1 Memory-Specific Text Styles

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `--memory-header-title` | 13px | bold | Memory tab / panel titles |
| `--memory-header-stats` | 9px | normal | Stats row in header |
| `--memory-wing-label` | 12px | bold | Wing name in tree |
| `--memory-room-label` | 11px | semibold | Room name in tree |
| `--memory-drawer-preview` | 10px | normal | Drawer content preview |
| `--memory-drawer-meta` | 9px | normal | Drawer date/size metadata |
| `--memory-badge` | 9px | bold | Count badges |
| `--memory-citation-header` | 11px | semibold | Citation card title |
| `--memory-citation-body` | 10px | normal | Citation card content |
| `--memory-citation-link` | 10px | normal | Citation action links |
| `--memory-briefing-title` | 14px | bold | Briefing greeting |
| `--memory-briefing-body` | 11px | normal | Briefing content |
| `--memory-briefing-section` | 10px | bold | Briefing section headers |
| `--memory-kg-entity` | 11px | semibold | Entity names in graph |
| `--memory-kg-relation` | 9px | normal | Relationship labels in graph |
| `--memory-search-result-title` | 12px | semibold | Search result title |
| `--memory-search-score` | 9px | normal | Relevance score |
| `--memory-progress-label` | 10px | normal | Mining progress status text |
| `--memory-empty-title` | 12px | semibold | Empty state title |
| `--memory-empty-body` | 11px | normal | Empty state description |
| `--memory-footer-hint` | 9px | normal | Keybind hints |

### 2.2 Font Family

All memory UI elements use the same monospace font stack as the rest of pyharness:
```
'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace
```

---

## 3. Spacing Tokens

### 3.1 Memory Panel Layout

| Token | Value | Usage |
|-------|-------|-------|
| `--memory-panel-width` | 260px | Width of memory side panel (same as main sidebar) |
| `--memory-panel-padding-x` | 8px | Horizontal padding inside panel |
| `--memory-panel-padding-y` | 4px | Vertical padding inside panel |
| `--memory-tree-indent` | 16px | Indentation per tree level |
| `--memory-tree-item-height` | 24px | Height of each tree row |
| `--memory-tree-item-gap` | 2px | Gap between tree items |
| `--memory-section-gap` | 8px | Gap between sections (header, search, tree, KG) |
| `--memory-card-padding` | 8px 12px | Padding inside cards (citation, briefing, result) |
| `--memory-card-gap` | 6px | Gap between cards |
| `--memory-card-border-radius` | 6px | Border radius for cards |
| `--memory-badge-padding` | 2px 6px | Padding inside badges |

### 3.2 Chat Inline Memory

| Token | Value | Usage |
|-------|-------|-------|
| `--memory-inline-underline-offset` | 3px | Offset for citation underline |
| `--memory-inline-underline-width` | 1px | Thickness of citation underline |
| `--memory-citation-card-max-width` | 600px | Max width of inline citation card |
| `--memory-tooltip-max-width` | 400px | Max width of source tooltip |

---

## 4. Icon Tokens

Memory-specific icons used throughout the UI:

| Icon | Unicode | Usage |
|------|---------|-------|
| Brain | 🧠 | Memory feature indicator, tab icon |
| Paperclip | 📎 | Citation source |
| Label | 🏷️ | Knowledge graph fact |
| Memo | 📝 | Agent diary entry |
| Folder | 📁 | Room / topic |
| Search | 🔍 | Memory search |
| Wing (stack) | 📚 | Wing / project |
| Drawer | 📄 | Individual drawer |
| Plus | [+] | Add fact button |
| Graph | 🔗 | Knowledge graph connection |
| Status: online | 🟢 / ● | Connected indicator |
| Status: syncing | 🟡 / ◐ | Syncing in progress |
| Status: offline | 🔴 / ● | Offline indicator |
| Status: empty | ○ | No memory yet |

---

## 5. Animation Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--memory-fade-in` | 150ms ease-out | Cards and panels appearing |
| `--memory-expand` | 200ms ease-out | Tree expansion animation |
| `--memory-collapse` | 150ms ease-in | Tree collapse animation |
| `--memory-progress-pulse` | 800ms infinite | Mining progress pulse effect |
| `--memory-highlight-fade` | 2000ms ease-out | Search match highlight fade |
| `--memory-tooltip-delay` | 300ms | Hover delay before tooltip appears |
| `--memory-tooltip-fade` | 100ms ease-out | Tooltip appear/disappear |

### Reduced Motion

When `prefers-reduced-motion` or `--tui-reduced-motion: true`:
- All animations are instant (0ms).
- Progress pulse is replaced with static fill.
- Highlight fade is disabled — matches remain highlighted until dismissed.

---

## 6. Component Tokens (Computed from Primitives)

### Memory Badge
```
background: var(--memory-badge-bg)
color: var(--memory-badge-text)
padding: var(--memory-badge-padding)
border-radius: 4px
font-size: var(--memory-badge)
```

### Citation Card
```
background: var(--memory-card-bg)
border: 1px solid var(--memory-card-border)
border-radius: var(--memory-card-border-radius)
padding: var(--memory-card-padding)
max-width: var(--memory-citation-card-max-width)
```

### Drawer Tree Item
```
height: var(--memory-tree-item-height)
padding-left: calc(var(--memory-tree-indent) * depth + 8px)
font-size: var(--memory-drawer-preview)
color: var(--memory-drawer-preview)
```

### Knowledge Graph Node
```
background: transparent
border: 1px solid currentColor
border-radius: 6px
padding: 4px 10px
font-size: var(--memory-kg-entity)
```

### Entity Node — Class
```
color: var(--kg-class)
border-color: var(--kg-class)
```

### Entity Node — Technology
```
color: var(--kg-tech)
border-color: var(--kg-tech)
```

### Entity Node — Concept
```
color: var(--kg-concept)
border-color: var(--kg-concept)
```

### Entity Node — File
```
color: var(--kg-file)
border-color: var(--kg-file)
```

---

## 7. Z-Index Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--z-memory-tooltip` | 100 | Memory citation tooltips |
| `--z-memory-overlay` | 200 | Memory full-screen overlays (KG graph, health dashboard) |
| `--z-memory-modal` | 300 | Memory confirmation dialogs (clear, delete) |
| `--z-memory-briefing` | 50 | Memory briefing banner (below chat messages) |
