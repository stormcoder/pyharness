# Scenarios for TUI Agent Switching, Status Bar, Command Palette, and Slash Commands

These scenarios are associated with **Story: Phase 2 TUI Enhancements** (Bugfixes for agent switching, status bar, command palette, slash command dispatch).

---

## Scenario: Tab key switches agents

```gherkin
Feature: Agent Switching
  As a pyharness user
  I want to press Tab to cycle between available agents
  So that I can quickly switch context between build and plan agents

  Background:
    Given the app is running with AGENTS = ["build", "plan"]

  Scenario: Default agent is build
    When the app launches
    Then the current agent index is 0
    And the active agent is "build"

  Scenario: Tab switches to next agent
    Given the current agent is "build"
    When I press Tab
    Then the current agent index changes to 1
    And the active agent is "plan"

  Scenario: Tab wraps around to first agent
    Given the current agent is "plan" (index 1)
    When I press Tab
    Then the current agent index changes to 0
    And the active agent is "build"

  Scenario: Tab key is bound to switch_agent
    When I inspect the app BINDINGS
    Then there is a binding ("tab", "switch_agent")
```

---

## Scenario: Status bar displays current agent

```gherkin
Feature: Status Bar Display
  As a pyharness user
  I want to see the current agent in the status bar
  So that I know which agent is active at all times

  Background:
    Given the app is running with ChatScreen active

  Scenario: Status bar is present on screen
    When the ChatScreen composes
    Then a StatusBar widget is yielded

  Scenario: Status bar shows default agent
    Given the app just launched
    When I look at the status bar
    Then the text contains "build"

  Scenario: Status bar updates on agent switch
    Given the current agent is "build"
    When I press Tab to switch to "plan"
    Then the status bar displays "plan"

  Scenario: Status bar is queryable by ID
    Given the ChatScreen is mounted
    When I query for "#status-bar"
    Then a StatusBar widget is returned
```

---

## Scenario: Ctrl+p opens command palette

```gherkin
Feature: Command Palette
  As a pyharness user
  I want to press Ctrl+p to see available commands
  So that I can discover and use slash commands without memorizing them

  Background:
    Given the app is running

  Scenario: Ctrl+p is bound to command_palette
    When I inspect the app BINDINGS
    Then there is a binding ("ctrl+p", "command_palette")

  Scenario: Command palette lists at least 10 commands
    When I open the command palette
    Then at least 10 commands are displayed
    And "/help" is listed
    And "/undo" is listed
    And "/new" is listed

  Scenario: Command palette is a modal overlay
    When I open the command palette
    Then a ModalScreen is pushed onto the screen stack
    And the palette is centered on screen

  Scenario: Escape closes command palette
    Given the command palette is open
    When I press Escape
    Then the palette is dismissed
    And the chat screen is visible again
```

---

## Scenario: Slash commands dispatch to actions

```gherkin
Feature: Slash Command Dispatch
  As a pyharness user
  I want slash commands like /new and /undo to perform real actions
  So that I can control the application from the chat input

  Background:
    Given the app is running with ChatScreen active

  Scenario: /help lists all commands
    When I type "/help" and press Enter
    Then a list of all available commands is displayed
    And each command shows its description

  Scenario: /new starts a new session
    When I type "/new" and press Enter
    Then the app's action_new_session is invoked
    And a confirmation message is shown

  Scenario: /undo acknowledges nothing to undo initially
    When I type "/undo" and press Enter
    Then the message "Nothing to undo yet" is shown

  Scenario: /models lists available model providers
    When I type "/models" and press Enter
    Then available models are displayed
    And "anthropic:claude-sonnet-4-5" is listed

  Scenario: Unknown command shows error
    When I type "/nonexistent" and press Enter
    Then an error message "Unknown command" is displayed
    And the message suggests trying "/help"

  Scenario: App and Screen COMMANDS are synchronized
    When I compare PyHarnessApp.COMMANDS and ChatScreen.COMMANDS
    Then both dictionaries contain exactly the same command keys
```

---

## Story Association

**Story:** Phase 2 TUI Enhancements — Bugfixes  
**Acceptance Criteria:**
- [x] Tab key cycles agents (build ↔ plan) with visual feedback
- [x] Current agent name is visible in the status bar at all times
- [x] Ctrl+p opens a proper command palette (modal, not toast)
- [x] All 12 slash commands dispatch to appropriate app/screen actions
- [x] Unknown commands show an error message with /help suggestion

---

## Test Coverage Mapping

| Scenario | Tests |
|----------|-------|
| Tab switches agents | `TestAgentSwitching` (6 tests) |
| Status bar displays agent | `TestStatusBar` (5 tests) |
| Ctrl+p command palette | `TestCommandPalette` (4 tests) |
| Slash command dispatch | `TestSlashCommands` (7 tests) |
