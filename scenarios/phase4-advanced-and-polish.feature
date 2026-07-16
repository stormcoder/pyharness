# language: en
# Story: Phase 4 — Advanced & Polish (pyharness/phase4)
# Corresponds to SPEC.md §14 Phase 4 (lines 840-854)

@phase4 @plugin-system
Feature: LangGraph Middleware Plugin System
  As a pyharness developer
  I want to extend pyharness with plugins
  So that I can add custom middleware, tools, and behaviors without modifying core

  Background:
    Given pyharness is installed and configured

  Scenario: Plugin field exists in configuration schema
    When I create a PyHarnessConfig with plugin list
    Then the config should have a "plugin" field
    And the plugin field should be a list of strings

  Scenario: Register custom tool from a plugin
    Given the ToolRegistry is available
    When I register a new BaseTool
    Then the tool should appear in the registry
    And the tool should be retrievable by name

  Scenario: Batch register multiple plugin tools
    Given the ToolRegistry is available
    When I call register_all with multiple tools
    Then all tools should be in the registry

  Scenario: Plugin permissions filter tools
    Given the ToolRegistry has registered tools
    When I call get_for_agent with deny-all permissions
    Then only explicitly allowed tools should be returned

  Scenario Outline: Plugin discovery from local paths
    Given the PluginLoader is initialized
    When I call discover()
    Then the result should be a list

    Examples:
      | source        | type   |
      | local dir     | local  |
      | pip entry pt  | pip    |

---
@phase4 @session-sharing
Feature: Session Sharing (/share command)
  As a pyharness user
  I want to share my session with others
  So that I can collaborate or show my work

  Background:
    Given I am in a pyharness chat session

  Scenario: /share command is registered
    When I check the available commands
    Then "/share" should be in ChatScreen.COMMANDS
    And "/share" should be in PyHarnessApp.COMMANDS

  Scenario: /share command dispatches correctly
    When I type "/share" in the chat input
    Then the command should be dispatched
    And the session should be exported or linked

  Scenario: /share exports session to markdown
    When I invoke /share
    Then a markdown file should be generated
    And the file should contain the conversation history

---
@phase4 @editor-mode
Feature: Editor Mode (/editor command)
  As a pyharness user
  I want to open an external editor from within pyharness
  So that I can edit files without leaving the TUI workflow

  Background:
    Given I am in a pyharness chat session

  Scenario: /editor command is registered
    When I check the available commands
    Then "/editor" should be in ChatScreen.COMMANDS
    And "/editor" should be in PyHarnessApp.COMMANDS

  Scenario: /editor references EDITOR env var
    When I type "/editor" in the chat input
    Then the handler should reference the EDITOR environment variable
    And guidance text should explain how to set EDITOR

  Scenario: /editor can open files externally
    When EDITOR is set to "vim"
    And I type "/editor path/to/file.py"
    Then the file should open in vim

---
@phase4 @server-mode
Feature: Server Mode (pyharness serve)
  As a pyharness operator
  I want to run pyharness in headless server mode
  So that I can expose pyharness as a remote API or agent service

  Background:
    Given pyharness is installed

  Scenario: pyharness serve is planned
    When I inspect the main module
    Then the entry point should support a serve/server mode
    And the configuration schema should allow server settings

  Scenario: Server config is extensible
    Given a PyHarnessConfig instance
    When I add server configuration as extra fields
    Then the config should validate without errors

---
@phase4 @remote-config
Feature: Remote Configuration (.well-known/pyharness)
  As a pyharness administrator
  I want to serve configuration from a .well-known endpoint
  So that teams can share pyharness config centrally

  Background:
    Given pyharness is installed

  Scenario: Config loader is callable
    When I call load_config with a project path
    Then it should return a validated PyHarnessConfig

  Scenario: Config merge respects overrides
    When I merge two config dicts
    Then override values should replace base values

  Scenario: Well-known path is supported
    When a remote_config URL is provided
    Then the config schema should accept it

---
@phase4 @lsp
Feature: LSP Integration (python-lsp-server)
  As a pyharness user
  I want LSP-powered diagnostics, completions, and go-to-definition
  So that I get IDE-like intelligence in the TUI

  Background:
    Given pyharness is installed

  Scenario: LSP module path exists
    When I check for LSP modules
    Then at least one of src/pyharness/tools/lsp.py or src/pyharness/lsp/__init__.py should exist

  Scenario: LSP is configurable in schema
    Given the PyHarnessConfig model
    When I check model_config
    Then "extra" should be "allow" for LSP config extensibility

---
@phase4 @github-integration
Feature: GitHub / GitLab Integration
  As a pyharness developer
  I want CI/CD workflows and git integration
  So that pyharness is continuously tested and can manage git operations

  Background:
    Given the pyharness repository

  Scenario: CI workflow runs tests
    When I check .github/workflows/ci.yml
    Then it should contain a pytest step
    And it should use uv for dependency management

  Scenario: Git undo middleware exists
    When I import pyharness.middleware.git_undo
    Then GitUndoMiddleware should be importable

---
@phase4 @performance
Feature: Performance Optimization (Virtualized Scrolling & Lazy Loading)
  As a pyharness user with long chat histories
  I want the TUI to remain responsive
  So that I can chat without lag or memory issues

  Background:
    Given I have a pyharness chat session

  Scenario: Chat area uses RichLog for virtualized scrolling
    When I inspect ChatScreen.compose
    Then it should use RichLog for the chat area

  Scenario: Focus management prevents tab-stealing
    When I inspect ChatScreen.compose
    Then RichLog should have can_focus=False
    And StatusBar should have can_focus=False

  Scenario: Prompt uses lazy-loading autocomplete
    When I inspect ChatScreen.compose
    Then it should use PromptInput for input
