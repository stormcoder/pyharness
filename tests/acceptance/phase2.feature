# language: en
# Story: Phase 2 — Full Agent System
# Associated with: SPEC.md §14 (Phase 2 Implementation)
# 
# Acceptance criteria for all Phase 2 features:
# 1. Plan agent (read-only primary)
# 2. General subagent (full-access via task tool)
# 3. Explore subagent (read-only codebase exploration)
# 4. @ file references & autocomplete
# 5. ! bash command injection
# 6. Git-backed undo/redo middleware
# 7. Side panels (Sessions, File Tree, Tools)
# 8. Command palette (Ctrl+p)
# 9. Slash commands (/new, /undo, /redo, /sessions, /help, etc.)
# 10. MemPalace Memory tab (4th sidebar tab)
# 11. Session briefing UX on startup

@phase2 @acceptance
Feature: Phase 2 — Full Agent System

  Background:
    Given pyharness is configured with test fixtures
    And FakeLLMProvider is active
    And a git repository exists at the project root

  # =========================================================================
  # Plan Agent (read-only primary)
  # =========================================================================

  @plan-agent @critical
  Scenario: Plan agent is read-only
    Given pyharness is started with the "plan" agent active
    When the user asks "analyze the auth module and suggest improvements"
    Then the agent should read files and provide analysis
    But the agent must NOT modify any files
    And the agent must NOT execute any bash commands
    And any attempt to use "write" or "edit" tools is denied with "Permission denied: plan agent is read-only"

  @plan-agent
  Scenario: Plan agent can be switched to via Tab key
    Given the build agent is active
    When the user presses Tab
    Then the active agent switches to "plan"
    And the header displays "[Plan]"
    And the plan agent's model is "anthropic:claude-haiku-4-5" (the small_model)

  @plan-agent
  Scenario: Plan agent permission denial is reported to user
    Given the "plan" agent is active
    And the plan agent has permission: {edit: deny, bash: deny}
    When the LLM attempts to call the "write" tool
    Then the tool execution is intercepted by PermissionMiddleware
    And a message "[Denied] Plan agent cannot modify files" is logged
    And the error is sent back to the LLM as a tool result

  # =========================================================================
  # General Subagent (full-access task tool)
  # =========================================================================

  @general-subagent
  Scenario: General subagent handles multi-step tasks
    Given pyharness is started with the "build" agent active
    When the user asks "@general search the codebase for all places where password hashing is used and verify they use bcrypt"
    Then a child session should be created for the "general" subagent
    And the subagent should use read, grep, and glob tools
    And the subagent should return findings to the parent session
    And the child session appears in the Sessions sidebar indented under the parent

  @general-subagent
  Scenario: General subagent has full tool access
    Given a "general" subagent is invoked via the task tool
    When the subagent needs to write a file
    Then the subagent has "edit: allow" permission
    And the subagent can execute bash commands
    And the subagent has access to all registered tools

  @general-subagent
  Scenario: General subagent result is injected into parent session
    Given a "general" subagent has completed its task
    When the subagent returns its findings
    Then the result is displayed in the parent chat as a tool result
    And the parent agent can reference the subagent's findings in subsequent messages
    And the subagent's session is marked as "completed" in the Sessions sidebar

  # =========================================================================
  # Explore Subagent (read-only codebase exploration)
  # =========================================================================

  @explore-subagent
  Scenario: Explore subagent searches read-only
    Given pyharness is started
    When the user asks "@explore find all API route handlers and list their auth dependencies"
    Then the "explore" subagent should search the codebase
    And the subagent must NOT modify any files
    And the subagent must NOT execute any bash commands
    And results should appear in the parent chat

  @explore-subagent
  Scenario: Explore subagent finds code patterns
    Given pyharness is started
    When the user asks "@explore find all places where we import sqlalchemy"
    Then the explore subagent uses grep and glob to find all SQLAlchemy imports
    And the results include file paths and line matches
    And the results are formatted with file:lineno: content

  @explore-subagent
  Scenario: Explore subagent cannot be tricked into writing
    Given the "explore" subagent is running
    When the user prompt contains "explore the codebase and fix any bugs you find"
    Then the subagent searches and reports bugs
    But the subagent does NOT modify any files
    And if the subagent attempts to call "edit" or "write", the permission is denied

  # =========================================================================
  # @ File References & Autocomplete
  # =========================================================================

  @file-references
  Scenario: @ file reference autocomplete inserts file content
    Given pyharness is started in a project with "src/auth/middleware.py"
    When the user types "@src/auth/" in the input
    Then a fuzzy file search dropdown should appear
    And selecting a file should insert "@src/auth/middleware.py" into the prompt
    And the file content should be added to the conversation context

  @file-references
  Scenario: @ file reference with partial filename
    Given the project contains "src/models/user.py", "src/models/order.py", and "tests/test_user.py"
    When the user types "@user" in the input
    Then the autocomplete dropdown shows "src/models/user.py" and "tests/test_user.py"
    And typing continues to narrow the results

  @file-references
  Scenario: @ file reference for non-existent file
    Given the project does NOT contain "src/nonexistent.py"
    When the user types "@src/nonexistent.py"
    Then no autocomplete match is found
    And the file is NOT injected into context

  # =========================================================================
  # ! Bash Command Injection
  # =========================================================================

  @bash-injection
  Scenario: ! bash command executes and shows output
    Given pyharness is started
    When the user types "!ls -la" and sends
    Then the command "ls -la" should execute in the project root
    And the output should appear in the chat as a tool result
    And the output is formatted as a collapsible block

  @bash-injection
  Scenario: ! bash command with arguments
    Given pyharness is started
    When the user types "!python -c 'print(42)'"
    Then the command executes and output shows "42"

  @bash-injection
  Scenario: ! bash command respects permission model
    Given the global permission for bash is "ask"
    When the user types "!rm -rf /"
    Then an inline permission prompt appears
    And the user must approve before execution

  # =========================================================================
  # Git-Backed Undo/Redo Middleware
  # =========================================================================

  @git-undo
  Scenario: Undo reverts the most recent agent file change
    Given the build agent has made a file change via the "edit" tool
    And a git commit was created on the session branch
    When the user runs /undo
    Then the file change is reverted
    And the conversation state is restored to before the change
    And the user's original prompt is displayed again

  @git-undo
  Scenario: Redo reapplies a previously undone action
    Given a previous /undo was performed
    When the user runs /redo
    Then the undone changes are reapplied
    And the file returns to the post-edit state

  @git-undo
  Scenario: Undo with no history
    Given a fresh session with no agent edits
    When the user runs /undo
    Then the message "Nothing to undo" is displayed
    And no error occurs

  @git-undo
  Scenario: Undo chain of 5 edits
    Given the agent has made 5 sequential file edits
    When the user runs /undo five times
    Then each undo reverts one commit in reverse order
    And after all 5 undos, all files are in their original state

  # =========================================================================
  # Side Panels
  # =========================================================================

  @side-panels
  Scenario: Sessions side panel shows active and archived sessions
    Given there are 3 active sessions and 2 archived sessions in this project
    When the user presses F1 (Sessions tab)
    Then the side panel shows "ACTIVE" section with 3 sessions
    And the side panel shows "ARCHIVED" section with 2 sessions
    And active sessions show their agent name and token count
    And archived sessions show their date and compacted badge

  @side-panels
  Scenario: File Tree side panel shows project structure
    When the user presses F2 (File Tree tab)
    Then a tree view of the project directory appears
    And directories are expandable/collapsible
    And files are selectable (opens in read tool)
    And hidden directories (.git, __pycache__) are excluded

  @side-panels
  Scenario: Tools side panel shows available tools
    When the user presses F3 (Tools tab)
    Then all registered tools are listed
    And each tool shows its name, description, and permission status
    And MCP server tools are grouped by server name
    And tool status (available/unavailable/degraded) is indicated

  @side-panels
  Scenario: Cycling side panel tabs via Shift+Tab
    When the user presses Shift+Tab repeatedly
    Then the side panel cycles through: Sessions → File Tree → Tools → Memory → None
    And the active tab is visually highlighted

  # =========================================================================
  # Command Palette
  # =========================================================================

  @command-palette
  Scenario: Command palette shows all available commands
    When the user presses Ctrl+p
    Then a searchable command list overlay appears
    And all slash commands are listed (/new, /undo, /redo, /sessions, /help, etc.)
    And each command shows its keyboard shortcut and description

  @command-palette
  Scenario: Command palette filters by typing
    When the user presses Ctrl+p and types "undo"
    Then only commands matching "undo" are shown (/undo, /redo)
    And the first match is pre-selected

  @command-palette
  Scenario: Command palette executes selected command
    When the user presses Ctrl+p, types "undo", and presses Enter
    Then the /undo command is executed
    And the command palette closes

  # =========================================================================
  # Slash Commands
  # =========================================================================

  @slash-commands
  Scenario: /new creates a fresh session
    Given an active session with message history
    When the user runs /new
    Then the current session is archived
    And a new session is created with state "active"
    And the new session ID is displayed in the header

  @slash-commands
  Scenario: /sessions opens session browser
    When the user runs /sessions
    Then the session browser screen opens
    And all sessions for the current project are listed
    And sessions are sorted by last activity

  @slash-commands
  Scenario: /help displays available commands
    When the user runs /help
    Then a help message appears in chat
    And the message lists all slash commands with descriptions
    And each command shows its keyboard shortcut

  # =========================================================================
  # MemPalace Memory Tab
  # =========================================================================

  @memory-tab
  Scenario: Memory tab shows knowledge graph and related sessions
    Given MemPalace is installed and has data for this project
    When the user presses F4 (Memory tab)
    Then the sidebar shows knowledge graph facts as an expandable tree
    And related past sessions are listed and clickable
    And agent diary entries are visible with timestamps
    And the memory indicator in the header shows "[🧠 N facts]"

  @memory-tab
  Scenario: Memory tab with MemPalace not installed
    Given MemPalace is NOT installed
    When the user presses F4 (Memory tab)
    Then the sidebar shows "MemPalace not installed"
    And an installation prompt is displayed: "pip install mempalace"
    And all other features continue to work normally

  @memory-tab
  Scenario: Clicking a related session in Memory tab
    Given the Memory tab shows "Session #3: refactored auth module"
    When the user clicks on that session entry
    Then pyharness shows a resume confirmation dialog
    And confirming opens the session

  # =========================================================================
  # Session Briefing UX
  # =========================================================================

  @session-briefing
  Scenario: Session briefing on startup with MemPalace data
    Given MemPalace has prior data for this project
    When pyharness starts a new session
    Then a briefing appears at the top of the chat area showing:
      | Section               | Content                       |
      | Related past sessions | 2-3 recent sessions           |
      | Knowledge graph facts | Key facts about the project   |
      | Agent diary entries   | Last entry from each agent    |
    And the briefing is collapsible via click or keypress

  @session-briefing
  Scenario: Session briefing with no MemPalace data
    Given MemPalace has NO prior data for this project
    When pyharness starts a new session
    Then a minimal briefing shows "No prior project memory"
    And the chat begins with an empty context

  @session-briefing
  Scenario: Session briefing respects max_results config
    Given memory.wake_up.max_results is set to 3
    And MemPalace has 10 matching past sessions
    When pyharness starts a new session
    Then the briefing shows at most 3 related past sessions
