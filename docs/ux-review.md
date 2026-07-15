# pyharness TUI — UX Review & Critique

> **Date**: 2026-07-14
> **Reviewer**: Senior UX/Product Designer
> **Sources**: SPEC.md §12, all 4 SVG mockups in `docs/mockups/`, OpenCode v1.2.20 actual TUI (via TUICommander analysis)

---

## Severity Scale

| Label | Meaning |
|-------|---------|
| 🔴 **P0** | Blocks usability — fix before MVP |
| 🟠 **P1** | Major UX friction — fix before beta |
| 🟡 **P2** | Noticeable issue — fix before launch |
| 🟢 **P3** | Polish — nice to have |

---

## 1. Layout & Space Efficiency

### 🔴 P0 — Sidebar width is a fixed 260px with no responsive fallback

**Evidence**: `tui-main-layout.svg` sets sidebar at 260px + chat at 1060px = 1320px total. On an 80-column terminal (~640px equivalent in the SVG's mono font), the sidebar alone would consume >40% of visible space, leaving the chat area unreadable.

**Impact**: This is the single biggest UX risk. Terminal users don't all have 200+ column windows. The mockup assumes a ~165-column terminal which is unrealistic for most configurations (especially with a code editor open alongside).

**Recommendation**:
- The sidebar must be **collapsible to 0 width** (Ctrl+o is documented in SPEC but not shown in the mockup).
- At <100 columns, the sidebar should **auto-hide** and become a pop-out drawer triggered by keyboard shortcut.
- At <80 columns, consider switching to a **vertical stack layout** (no side-by-side).
- Show these states in additional mockup panels.

### 🟠 P1 — Chat area at narrow widths doesn't exist

**Evidence**: No mockup variation for 80-column, 100-column, or 120-column terminal widths.

**Recommendation**: Create responsive variants showing:
- **80 cols**: No sidebar, full-width chat, header condenses to single line.
- **100 cols**: Sidebar collapsed, chat gets full width.
- **120+ cols**: Sidebar visible at reduced width (~30 chars for session names).
- **160+ cols**: Full layout as shown in mockup.

### 🟡 P2 — The sidebar footer wastes 44px (~2 lines) on keybind hints

**Evidence**: `tui-main-layout.svg` lines 91-93: the sidebar footer shows keybind hints that duplicate the status bar information.

**Recommendation**: Remove the sidebar footer or use it for context-sensitive info (e.g., "3 files changed", "2 subagents running").

---

## 2. Information Hierarchy

### 🟡 P2 — Status bar is sparse

**Evidence**: `tui-main-layout.svg` status bar (lines 188-201) shows only agent name, git status, and keybind reminders.

The following high-value information is only visible in the **header** (which scrolls off when reading long conversations):
- Current model and provider
- Token usage (12.4k / 200k)
- Session title

**Recommendation**: Move token usage and model to the status bar (always visible). OpenCode does this well — the status bar shows path, branch, and version. Add:
```
[Build] git:main ✓ | claude-sonnet-4-5 | 12.4k/200k tokens | ctrl+p commands
```

### 🟢 P3 — Tool call expansions are always visible

**Evidence**: All tool calls in the mockup (bash, read, edit) are shown expanded with full output. For long tool outputs, this pollutes the conversation.

**Recommendation**: Default to **collapsed** tool calls (showing just the tool name and first line). Allow expanding with `Enter` and collapsing with `Esc`. Show a summary line like:
```
▶ bash: grep -rn "class AuthMiddleware" src/  [3 results, 0.2s]  ▶ expand
```

### 🟢 P3 — No thinking/reasoning toggle shown

**Evidence**: SPEC §12 documents `Ctrl+t` to toggle thinking visibility, but no mockup shows what thinking looks like.

**Recommendation**: Add a mockup screen showing expanded thinking content (chain-of-thought, in a distinct muted color block, collapsed by default).

---

## 3. Keyboard Navigation

### 🟠 P1 — Sidebar tab switching has no documented keyboard shortcut

**Evidence**: `tui-agent-sessions.svg` line 115-119 documents Up/Down/Right/Left for session navigation, but no sidebar tab switcher (Sessions → File Tree → Tools) is documented. SPEC §12 says `Shift+Tab` cycles side panel, but this conflicts with standard terminal behavior (insert literal tab).

**Recommendation**:
- Use `Ctrl+1` / `Ctrl+2` / `Ctrl+3` for sidebar tabs (muscle memory from browsers).
- Or use `F1`/`F2`/`F3` for tab selection.
- Update mockup to show tab switching hints.

### 🟠 P1 — Permission dialog has no keyboard shortcut indicators

**Evidence**: `tui-main-layout.svg` lines 162-170: The "Allow", "Allow Always", "Deny" buttons have no keyboard shortcut labels. A terminal user cannot reach for a mouse.

**Recommendation**:
- `Enter` → Allow
- `Alt+a` → Allow Always
- `Esc` → Deny
- Add these as labels beneath each button in the mockup.

### 🔴 P0 — No vim-style navigation

**Evidence**: Nowhere in SPEC or mockups are j/k navigation keys mentioned. The SPEC only documents arrow keys.

**Impact**: The target audience (terminal developers) overwhelmingly uses vim keybindings. Without j/k for scroll, `gg`/`G` for top/bottom, and `/` for search, the UX will feel hostile.

**Recommendation**:
- `j`/`k` — scroll chat down/up (when input is not focused)
- `gg` — scroll to top of chat
- `G` — scroll to bottom of chat
- `Ctrl+d`/`Ctrl+u` — half-page scroll
- `/` — enter search mode for conversation
- `Esc` — return to input focus
- Document a vim-mode toggle in `tui.json`.

### 🟡 P2 — Arrow keys for session navigation conflict with chat scrolling

**Evidence**: `tui-agent-sessions.svg` shows Up/Down/Right/Left mapped to session navigation. But when a long chat response is visible, Up/Down should scroll the chat.

**Recommendation**: Session navigation only works when the sidebar is focused. Add a dedicated `Ctrl+j`/`Ctrl+k` for session switching without focus context ambiguity.

---

## 4. Conversation UX

### 🟠 P1 — No streaming response mockup

**Evidence**: All assistant text in the mockup appears fully formed. There's no visual representation of streaming — a blinking cursor, animated typing indicator, or progressive text reveal.

**Recommendation**: Add a mockup panel showing a mid-stream response:
- Cursor at end of streaming text (blinking block or pipe)
- Different visual treatment for partially-streamed vs. completed text
- Pulsing activity indicator (spinner or dot animation) in the header while streaming

### 🟡 P2 — Tool call completion lacks visual distinction from running tools

**Evidence**: All tool calls in the mockup use the same `▶ bash` / `▶ read` / `▶ edit` prefix. There's no way to distinguish running tools from completed ones.

**Recommendation**: Adopt OpenCode's conventions:
- `→` for read operations (file reads)
- `←` for write operations (file writes/edits)
- `▣` for completed tool calls
- `◉` (or spinner) for currently running tool calls
- Show elapsed time on completion: `▣ bash: npm test  [exit 0, 2.3s]`

### 🟡 P2 — Child session messages not visually distinguished in chat

**Evidence**: `tui-main-layout.svg` sidebar shows child sessions but the chat area has no visual indicator when viewing a child session's results.

**Recommendation**: When viewing a child session, add a banner or colored bar at the top of the chat:
```
┌─────────────────────────────────────────────────────┐
│ ↳ @general: update tests  (active since 12:35 PM)   │
│ Press Up to return to parent session                │
└─────────────────────────────────────────────────────┘
```

### 🟢 P3 — No conversation timestamp grouping

**Evidence**: Each message pair (user + assistant) shows the same timestamp. For long conversations spanning hours or days, temporal context is lost.

**Recommendation**: Show date/time headers when the gap exceeds a threshold:
```
── Today 12:34 PM ───────────────────
```

### 🟢 P3 — No copy/paste affordances

**Evidence**: Terminal users frequently want to copy code snippets or command output. No copy hint is documented.

**Recommendation**: Add a subtle copy indicator on code blocks and tool outputs. Consider `Ctrl+c` to copy the selected block (when Textual supports clipboard access via the terminal).

---

## 5. Side Panel Design

### 🟠 P1 — Missing critical tabs: Context/Memory, Diffs, Skills

**Evidence**: `tui-main-layout.svg` shows only three tabs: Sessions, File Tree, Tools. The following information has no dedicated view:

| Missing Tab | Why It Matters |
|-------------|---------------|
| **Context** | Users need to see what files/symbols are in the LLM's context window. OpenCode shows this in its right panel. |
| **Diffs** | When the agent modifies files, users need to see pending changes before they commit. |
| **Skills** | With 100+ loaded skills (AGENTS.md shows available skills), discoverability requires a visible list. |
| **MCP** | MCP server status, connected tools, error states need monitoring. |

**Recommendation**: 
- Add **Context** as a primary tab (or merge with a "Status" tab showing context usage, tokens, loaded files).
- Add **Diffs** as a dedicated view for git-tracked changes.
- Add **Skills** as a tab showing loaded and available skills with status (enabled/disabled).
- Add **MCP** as a tab showing server connection status, tool counts, and error states.

### 🟡 P2 — File tree at 260px is unusably narrow for real project structures

**Evidence**: The sidebar is only 260px (~32 chars at the mockup's font size). Real project trees often have deeply nested paths that need 40-60 chars.

**Recommendation**:
- Horizontal scrolling within the file tree widget.
- Option to expand the sidebar to 40% width with a double-tap of the toggle key.
- Show full path on hover/focus (or as a tooltip overlay at the bottom of the sidebar).

### 🟡 P2 — "Tools" tab purpose is unclear

**Evidence**: The mockup labels a tab "Tools" but the SPEC diagram shows "Tool Output" in the side panel. It's ambiguous whether this is an inventory of available tools or a running output log.

**Recommendation**: Rename to **"Tool Log"** or split into two views:
- **Tool List** — inventory of registered tools (built-in, MCP, custom) with permission status
- **Tool Output** — live output from currently running tool, replacing inline output blocks

---

## 6. Permission UX

### 🔴 P0 — Modal overlay blocks the conversation

**Evidence**: `tui-main-layout.svg` lines 148-170: The permission dialog is a centered modal overlay with a semi-transparent black backdrop. This is **anti-pattern for a TUI**. When the user needs to decide whether to allow a bash command, they need to see what the tool call is and what's happening in the conversation.

**OpenCode's approach (superior)**: Permissions appear **inline within the prompt frame**. The prompt box expands to show:
```
┃  △ Permission required
┃    ← Access external directory /tmp
┃  Patterns: /tmp/*
┃
┃   Allow once  Allow always  Reject
```
This lets the user see the original message, the tool call description, AND the permission prompt simultaneously.

**Recommendation**: **Remove the modal overlay entirely.** Handle permissions inline:
1. Tool call appears in chat with a highlighted permission banner.
2. User presses Enter to accept, or types `a` for "allow always", or Esc for "deny".
3. The response continues inline after approval.

### 🟠 P1 — No bulk approval workflow

**Evidence**: The mockup shows individual "Allow Always" but doesn't address multi-step tool chains. A common workflow is: agent runs 5 bash commands. Without bulk approval, the user must approve each one individually, breaking flow.

**Recommendation**: 
- When the agent queues multiple tool calls of the same type, prompt: "Allow all 5 bash commands for this session?"
- Add a "Session Policy" view accessible from the sidebar that lets users pre-approve patterns: `npm * → allow`, `pip install * → ask`, `rm -rf * → deny`.

### 🟡 P2 — Permission buttons look clickable but terminal users can't click

**Evidence**: `tui-main-layout.svg` lines 163-170: Three styled buttons (Allow, Allow Always, Deny) imply mouse interaction. In a keyboard-first TUI, these need keyboard affordances.

**Recommendation**: Show keyboard shortcuts as part of the button design:
```
[ Enter Allow ]  [ Alt+A Allow Always ]  [ Esc Deny ]
```

### 🟢 P3 — No "Show diff" option for edit permissions

**Evidence**: When the agent requests edit permission, the user sees the tool call but not what will change.

**Recommendation**: Add a "Preview" option to the edit permission prompt that shows a unified diff inline before the user approves.

---

## 7. Visual Design Quality

### ✅ Strengths

- **Cohesive dark theme**: The GitHub-dark palette (#0d1117 base, #161b22 surfaces, #1f2937 selected) is recognizable and comfortable for long coding sessions.
- **Consistent semantic color usage**: Blue for system/commands, green for assistant, purple for tool calls, orange for warnings — these are well-chosen and internally consistent.
- **Professional header and status bars**: Clean, information-dense without feeling cluttered.
- **Diff styling**: The `+` (green #3fb950) / `-` (red #f85149) diff preview is immediately readable.
- **Session list cards**: Good use of color (blue border for active, dimmed for archived) and metadata density.

### 🟠 P1 — WCAG contrast failures on secondary text

**Evidence**: Secondary text uses #484f58 on #0d1117 background. The contrast ratio is approximately **2.8:1**, which fails WCAG AA (minimum 4.5:1 for text). This includes:
- Timestamps ("12:34 PM")
- "2m ago" / "1h ago" labels
- Session subtitle text
- Keybinding hints in the status bar
- Sidebar footer text

**Impact**: Users with visual impairments (and tired developers at 2 AM) will struggle with secondary information.

**Recommendation**: Raise secondary text to at least #6e7681 (contrast ratio ~4.5:1 on #0d1117) or #8b949e (already used for some labels but inconsistently).

### 🟡 P2 — Red/green diff is the only diff of color blindness

**Evidence**: Diff preview uses red (#f85149) for deletions and green (#3fb950) for additions. This is the most common form of color blindness (deuteranopia, affecting ~6% of males).

**Recommendation**: Add `-` / `+` prefixes (already present in the mockup — good) AND consider a secondary indicator like background shading:
- Removed lines: slight red-tinted background
- Added lines: slight green-tinted background
- Optionally support a colorblind-friendly theme with blue/orange diffs.

### 🟢 P3 — Sidebar gradient may not render on all terminals

**Evidence**: The sidebar uses `linearGradient` from #161b22 to #0d1117. Truecolor terminals (most modern terminals) render this fine, but some terminals may fall back to a solid color, losing the visual distinction.

**Recommendation**: Ensure the sidebar still has visual contrast without the gradient (e.g., a border or different background solid color). Test on rxvt, st, and Linux console.

### 🟢 P3 — No light theme mockup shown in detail

**Evidence**: `tui-screens-overlays.svg` shows a small "Light" theme swatch (line 106-107) but no full conversation view in light mode.

**Recommendation**: Add at least one full-conversation mockup in light theme to validate the palette is usable for daylight coding.

### 🟢 P3 — Theme picker swatches are generic blocks, not previews

**Evidence**: Theme swatches show header/body blocks but don't give a sense of what actual code or conversation would look like.

**Recommendation**: Show a miniature chat preview inside each theme swatch card — a few lines of user/assistant exchange in the theme's colors.

---

## 8. OpenCode Comparison

### What OpenCode Does Better (that pyharness should adopt)

| OpenCode Feature | pyharness Status | Recommendation |
|-----------------|------------------|----------------|
| **Inline permission prompts** (no modal) | Modal overlay (🔴 P0) | Adopt inline permissions |
| **Right sidebar** (less dominant for LTR reading) | Left sidebar takes focus | Consider right-aligning sidebar or making side configurable |
| **Progress bar in footer** (`■■⬝⬝⬝⬝⬝⬝`) during tool execution | Not shown | Add footer progress bar |
| **Completion marker** (`▣` with timing info) | No completion indicator | Adopt completion markers |
| **Context token display in sidebar** (always visible) | Only in scrollable header | Move tokens to always-visible area |
| **Cost tracking** ($0.00 spent) in sidebar | Not shown | Add cost tracking |
| **Welcome screen** with ASCII art and quick-start | Not shown | Add welcome/onboarding screen |
| **Tips** (● Tip: contextual hints) | Not shown | Add contextual tips |
| **LSP status in sidebar** | Not shown | Add LSP connection status |
| **Error display inline** in conversation frame | Not shown | Errors should appear inline, not modals |
| **Mouse tracking** (enabled by default) | Not documented | Document mouse support |
| **Two-panel layout** (conversation + context sidebar) | Three-region layout (header, chat+sidebar, status) | Simpler = better for terminals |

### What pyharness Does Better (that OpenCode should adopt)

| pyharness Feature | Rationale |
|-------------------|-----------|
| **Tabbed sidebar** (Sessions, File Tree, Tools) | More organizing power than OpenCode's single-panel sidebar |
| **Theme picker with live swatches** | Visual theme selection is faster than cycling through names |
| **Command palette** (Ctrl+p) | Excellent discoverability pattern |
| **Session browser with search** | OpenCode has no session search; this is a real advantage |
| **Agent hierarchy visualization** | The agent/session tree diagram helps users understand the system |
| **Diff preview inline** in chat | OpenCode shows diffs but pyharness's inline diff block is clearer |
| **Model selector with pricing info** | Including $/MTok in the picker helps users make cost-conscious choices |

### Areas Where OpenCode Is Simply Different

| Aspect | OpenCode | pyharness |
|--------|----------|-----------|
| Framework | Bubble Tea (Go) | Textual (Python) |
| Panel layout | 2-panel (chat + context sidebar) | 3-region (header, chat+sidebar, status) |
| Tool call display | Inline (`→ Read`, `← Write`) | Inline card with header |
| Permission style | Inline in prompt frame | Modal overlay (needs change) |
| Cursor | Block cursor, always visible | Cursor shown in input field only |
| Foundation | Terminal ANSI control codes | Higher-level Textual widget API |

---

## 9. Missing Screens & States

### Screens/States That MUST Be Documented (P0–P1)

| Missing State | Severity | Description |
|---------------|----------|-------------|
| **Streaming response** | 🔴 P0 | How does text appear as the LLM streams tokens? Cursor? Animation? Typing indicator? |
| **Thinking/reasoning display** | 🟠 P1 | What does `Ctrl+t` toggle look like? (chain-of-thought, reasoning tokens) |
| **Welcome/empty state** | 🟠 P1 | First launch experience. No sessions exist. What do users see? |
| **Tool execution in progress** | 🟠 P1 | How are long-running tools (bash, web search) shown? Progress bar? Spinner? |
| **Error state** | 🟠 P1 | API error, connection failure, rate limit, tool failure — how are these displayed? |
| **Compaction notification** | 🟠 P1 | When context is auto-compacted, how is the user informed? Can they review what was removed? |
| **Narrow terminal (80 cols)** | 🟠 P1 | Full layout at 80 columns — what changes? |
| **Empty conversation** | 🟡 P2 | Before the first message — what instructions/hints are shown? |
| **Empty sidebar tabs** | 🟡 P2 | "No sessions yet", "Empty directory", "No tools loaded" |
| **Session resume** | 🟡 P2 | Resuming a long session — how much history is loaded? Loading indicator? |
| **Child session collapsed view** | 🟡 P2 | How do multiple running child sessions appear simultaneously? |
| **Confirmation dialogs** | 🟡 P2 | Delete session confirmation, overwrite file confirmation |
| **Connection lost / reconnected** | 🟡 P2 | Network interruption during streaming — what happens? |
| **Token limit warning** | 🟡 P2 | Approaching context limit — visual warning before auto-compaction? |
| **Multi-file diff view** | 🟢 P3 | When the agent edits 5+ files, how does the diff browser work? |
| **Search results in conversation** | 🟢 P3 | When searching chat history, how are results highlighted? |
| **Notification toast** | 🟢 P3 | Child session completes, file watcher detects change — how is the user notified? |

### Specific Missing Screens to Mock Up

1. **Welcome Screen** (P1) — OpenCode shows ASCII art + "Ask anything..." prompt. pyharness should show:
   - pyharness ASCII logo
   - Quick-start: "Describe what you want to build..."
   - Model/agent selector at bottom
   - Recent sessions list (if any exist)
   - Version info

2. **Streaming State** (P0) — Most critical missing mockup:
   - Assistant text appearing character-by-character
   - Blinking cursor at end of streaming text
   - "Streaming..." indicator in header
   - Tool calls appearing inline as they're invoked
   - Interrupt hint: "Esc to interrupt"

3. **Tool Execution Progress** (P1):
   - bash command with scrolling output
   - Progress bar/spinner for long-running commands
   - "Running for 45s..." elapsed time indicator
   - "Ctrl+c to cancel" hint

4. **Error States** (P1):
   - API error banner in chat: "Error: Rate limit exceeded. Retrying in 30s..."
   - Connection failure: "Cannot reach api.anthropic.com. Check your connection."
   - Tool failure: "bash: command not found: npmm" — shown inline with red styling

5. **Narrow Viewport** (P1):
   - 80-column mockup with collapsed sidebar
   - 100-column mockup with compact sidebar (icon-only tabs)
   - Mobile/responsive breakpoint diagram

6. **Compaction Event** (P1):
   - Pre-compaction warning: "Context at 95%. Compacting..."
   - Post-compaction summary: "Compacted 142 messages → summary (saved 180k tokens)"
   - Option to review removed context

---

## Summary of Top Issues

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | 🔴 P0 | No responsive layout for narrow terminals | Add 80/100/120-col variants; auto-hide sidebar |
| 2 | 🔴 P0 | Modal permission overlay in a TUI | Inline permissions (like OpenCode) |
| 3 | 🔴 P0 | No vim keybindings (j/k) | Add vim-mode navigation option |
| 4 | 🔴 P0 | No streaming response mockup | Mock up mid-stream state with cursor |
| 5 | 🟠 P1 | No welcome/empty state | Mock welcome screen |
| 6 | 🟠 P1 | Missing sidebar tabs (Context, Diffs, Skills, MCP) | Add 4 new tabs to sidebar design |
| 7 | 🟠 P1 | WCAG contrast failures on secondary text | Raise #484f58 → #6e7681 minimum |
| 8 | 🟠 P1 | No error state mockups | Mock API errors, tool failures, connection loss |
| 9 | 🟠 P1 | Permission dialog lacks keyboard shortcuts | Add Enter/Alt+key/Esc labels |
| 10 | 🟡 P2 | Tool calls always expanded (no collapse) | Default collapsed, expand on Enter |

---

## Appendix: SVG Mockup Element Annotations

### tui-main-layout.svg

| Element (line) | Issue |
|----------------|-------|
| Line 148-170 — Permission modal overlay | 🔴 Replace with inline permission in input frame |
| Line 39-47 — Sidebar at 260px fixed width | 🔴 Needs collapsible/responsive behavior |
| Line 163-170 — Permission buttons | 🟠 Add keyboard shortcut labels |
| Line 112-130 — Tool call always expanded | 🟡 Default to collapsed with expand affordance |
| Line 184 — Input hints bar | 🟢 Add `j/k scroll` hint for vim users |
| Line 91-93 — Sidebar footer keybinds | 🟡 Replace with context-sensitive info |
| Line 114 — `▶ bash` prefix (all same) | 🟡 Distinguish running vs. completed tools |
| Line 173-183 — Input area | ✅ Good design — clear, well-placed |
| Line 18-37 — Header bar | ✅ Good information density |

### tui-agent-sessions.svg

| Element (line) | Issue |
|----------------|-------|
| Line 112-119 — Navigation key doc | ✅ Excellent documentation, clear mapping |
| Line 57-70 — Subagent definitions | ✅ Good visual hierarchy |
| Line 73-78 — Custom subagent (dashed) | ✅ Good distinction between built-in and custom |
| Line 83-113 — Session hierarchy | ✅ Clear parent-child visualization |

### tui-screens-overlays.svg

| Element (line) | Issue |
|----------------|-------|
| Line 96-118 — Theme swatches | 🟢 Add miniature chat previews, not just header/body |
| Line 68-87 — Model selector | ✅ Excellent — shows pricing, context window, selection state |
| Line 129-143 — Command palette | ✅ Good — shows keybindings, filterable search |
| Line 18-67 — Session browser | ✅ Good — metadata-rich, searchable, archive section |

### system-architecture.svg

| Element (line) | Issue |
|----------------|-------|
| Line 15-47 — TUI Layer | ✅ Clear system boundary, well-organized |
| Line 49-83 — Core Engine | ✅ Good component separation |
| Line 85-113 — Storage & Discovery | ✅ Shows all discovery paths |
| Line 115-139 — External Integrations | ✅ Good separation of external dependencies |

