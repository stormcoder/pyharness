# language: en
# Story: Session System — Lifecycle, persistence, git-backed undo/redo
# Associated with: SPEC §6 (Session System)

@session @critical
Feature: Session Lifecycle and Git Undo/Redo

  Background:
    Given pyharness is configured with test fixtures
    And a git repository exists at the project root
    And FakeLLMProvider is active

  # --- Session Lifecycle ---

  Scenario: Create a new session
    When the user starts pyharness with "pyharness"
    Then a new session is created with state "active"
    And a SQLite database is created at ~/.local/share/pyharness/sessions/<session-id>.sqlite
    And the session ID is displayed in the header
    And a git branch "pyharness-session-<id>" is created

  Scenario: Resume an existing session
    Given a previous session exists with 50 messages
    When the user runs "pyharness --resume <session-id>"
    Then the session loads with all 50 messages
    And the chat area scrolls to the last message
    And the git branch "pyharness-session-<id>" is checked out

  Scenario: Create a child session from parent
    Given an active parent session
    When the user invokes a subagent (e.g. @explore)
    Then a child session is created linked to the parent
    And the child session appears indented in the session tree
    When the child session completes
    Then the result is injected into the parent session's message history

  Scenario: Session compaction
    Given a session with 20,000 tokens of message history
    When auto-compaction triggers or /compact is invoked
    Then older messages are replaced with a compacted summary
    And the session state changes to "compacted"
    And the original messages remain in SQLite (not deleted)

  Scenario: Delete a session
    Given a session exists
    When the user deletes the session
    Then the SQLite file is moved to ~/.local/share/pyharness/sessions/.trash/
    And the session is removed from the session list
    And the git branch "pyharness-session-<id>" is deleted

  Scenario: Export session to Markdown
    Given a session with 30 messages including tool calls
    When the user runs "/export"
    Then a Markdown file is created in the project root
    And the file contains all messages with proper formatting
    And tool call inputs and outputs are included
    And API keys and secrets are redacted

  # --- Git-Backed Undo/Redo ---

  Scenario: Agent makes a file edit then user undoes it
    Given the agent has made 3 file-editing commits
    When the user presses Ctrl+x u (/undo)
    Then the most recent commit is reverted
    And the file returns to its pre-edit state
    And a message "[Undo] Reverted: Fix typo in main.py" appears in chat
    And the undo stack decrements

  Scenario: Undo then redo
    Given the user has undone the last agent edit
    When the user presses Ctrl+x r (/redo)
    Then the reverted commit is reapplied
    And the file returns to the post-edit state
    And a message "[Redo] Reapplied: Fix typo in main.py" appears

  Scenario: Undo when there is nothing to undo
    Given a fresh session with no agent edits
    When the user presses Ctrl+x u
    Then the message "Nothing to undo" is displayed
    And no error occurs

  Scenario: Undo chain (5 edits → 5 undos)
    Given the agent has made 5 sequential file edits
    When the user presses Ctrl+x u 5 times
    Then each undo reverts one commit in reverse order
    And after all 5 undos, files are in their original state

  # --- Git Edge Cases ---

  Scenario: Start session in non-git directory
    Given the current directory is NOT a git repository
    When the user starts pyharness
    Then the session starts normally
    And the status bar shows "[undo: n/a — not a git repo]"
    And the /undo command returns "Cannot undo — not a git repository"
    And all other features work normally

  Scenario: Detached HEAD at session start
    Given the git repository is in detached HEAD state
    When the user starts a new session
    Then pyharness creates branch "pyharness-session-<id>" from current HEAD
    And undo/redo work correctly on this branch

  Scenario: Dirty working directory at session start
    Given the user has uncommitted changes in the working directory
    When the user starts a new session
    Then pyharness stashes the user's uncommitted changes
    And a warning is displayed: "User changes stashed — use /unstash to recover"
    And the session proceeds normally
    And agent edits are committed on the session branch

  Scenario: Dirty working directory during undo
    Given the agent has made a committed edit
    And the user has made uncommitted manual changes after the agent edit
    When the user presses /undo
    Then the user's uncommitted changes are stashed first
    Then the agent's commit is reverted
    And a warning is displayed: "Your uncommitted changes were stashed — use /unstash to recover"

  Scenario: Merge conflict on redo
    Given an agent edit was undone
    And the user manually edits the same file differently
    When the user presses /redo
    Then a merge conflict occurs
    And the conflict is displayed with inline diff markers
    And the status bar shows "[Conflict — resolve manually or /abort-redo]"
    And the user can choose to resolve or abort

  # --- SQLite Persistence ---

  Scenario: Session survives clean exit
    Given a session with 100 messages
    When the user exits pyharness cleanly (Ctrl+x q)
    Then all 100 messages are persisted in SQLite
    And on resume, all messages are restored identically

  Scenario: Session recovery after SIGKILL
    Given a session with messages being written
    When the pyharness process receives SIGKILL
    And the user restarts pyharness with --resume
    Then SQLite WAL recovery runs automatically
    And the session recovers all committed messages
    And a warning "Session was not cleanly closed — recovery successful" is displayed

  Scenario: Corrupted SQLite file
    Given the session SQLite file has been corrupted (zeroed bytes)
    When the user attempts to resume the session
    Then the error "Session database is corrupted" is displayed
    And pyharness offers to create a recovery session
    And the corrupted file is moved to .trash/ for forensics

  Scenario: Schema migration between versions
    Given a session was created with pyharness v0.1.0 (schema version 1)
    When the user upgrades to pyharness v0.2.0 (schema version 2)
    And resumes the session
    Then schema migration runs automatically
    And all data is preserved
    And the session header shows "[Migrated: v1 → v2]"

  # --- Concurrent Access ---

  Scenario: Two pyharness instances accessing same session
    Given pyharness instance A has session X open
    When pyharness instance B attempts to open session X
    Then instance B detects the SQLite lock
    And displays "Session X is in use by PID 12345 — opening read-only"
    Or, if configured: "Session X is locked — cannot open"

  Scenario: Session list with 1000+ sessions
    Given ~/.local/share/pyharness/sessions/ contains 1000 sessions
    When the user opens the session list (Ctrl+x l)
    Then the session list loads in under 200ms
    And sessions are sorted by last activity
    And search/filter is available
