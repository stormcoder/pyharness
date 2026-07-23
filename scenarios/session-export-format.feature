# language: en
# Story: Session Export — OpenCode-style Markdown Format
# Associated with: SPEC §6 (Session System), session-ses_09dc.md (reference format)
# Bug: export_session_to_markdown uses old | Field | Value | table format
# Bug: _handle_export does not support /export [session_id] argument

@export @format @session
Feature: Session Export to Markdown

  Background:
    Given pyharness is configured with test fixtures
    And a FakeSessionStore is active with test sessions

  # --- Export Format: Header ---

  Scenario: Export header uses inline bold labels not table
    Given a session "sess-abc" with title "My Coding Session"
    And the session has model "deepseek:deepseek-v4-flash"
    And the session has agent "build"
    When the user runs "/export"
    Then the exported markdown file contains "**Session ID:** sess-abc"
    And the file contains "**Model:** deepseek:deepseek-v4-flash"
    And the file contains "**Agent:** build"
    And the file contains "**Created:**"
    And the file contains "**Updated:**"
    And the file contains "**Messages:**"
    And the file contains "**Total Tokens:**"
    But the file does NOT contain "| Field | Value |"
    And the file does NOT contain "|-------|-------|"

  Scenario: Export h1 heading is the session title
    Given a session with title "Refactoring Authentication"
    When the user runs "/export"
    Then the exported file h1 heading is "# Refactoring Authentication"
    And the h1 does NOT contain "Session:" prefix

  # --- Export Format: Messages ---

  Scenario: User message uses ## User heading without timestamp
    Given a session has a user message "Write a hello-world script"
    When a user message is formatted for export
    Then the message uses "## User" heading
    And the message content appears after the heading
    But the message does NOT include an ISO timestamp

  Scenario: Assistant message uses ## Assistant heading without timestamp
    Given a session has an assistant message "Here is the script:"
    When the assistant message is formatted for export
    Then the message uses "## Assistant" heading
    And the message content appears after the heading
    But the message does NOT include an ISO timestamp

  Scenario: Tool message uses **Tool: name**, **Input:**, and **Output:** blocks
    Given a session has a tool message with name "read"
    And the tool args are {"filePath": "/foo/bar.py"}
    And the tool result is "print('hello')"
    When the tool message is formatted for export
    Then the format uses "**Tool: read**"
    And the format uses "**Input:**" followed by a JSON code block
    And the format uses "**Output:**" followed by a code block
    And the format does NOT use "## Tool (read)" heading

  Scenario: Message sections are separated by horizontal rules
    Given a session with 3 messages
    When the session is exported to markdown
    Then message sections are separated by "---"

  # --- Export Format: Rich Markup ---

  Scenario: Rich Textual markup is stripped from exported messages
    Given a message contains "[bold #58a6ff]Hello![/]"
    And the message contains "[italic]styled[/] text"
    And the message contains "[#f85149 on #0d1117]Error:[/]"
    When the message is formatted for export
    Then the tags "[bold", "[italic]", "[#f85149" are absent
    But the text "Hello!", "styled", and "Error:" remain

  # --- Export Session ID Argument ---

  Scenario: Export current session when no session ID given
    Given the current active session is "sess-current"
    When the user runs "/export" with no argument
    Then the current session "sess-current" is exported

  Scenario: Export specific session by ID
    Given two sessions exist: "sess-aaa" and "sess-bbb"
    When the user runs "/export sess-bbb"
    Then session "sess-bbb" is exported
    And session "sess-aaa" is NOT affected

  Scenario: Export nonexistent session shows error
    Given no session with ID "sess-nonexistent" exists
    When the user runs "/export sess-nonexistent"
    Then an error message is displayed
    And no export file is created

  # --- Export File Naming ---

  Scenario: Export filename includes session ID by default
    Given a session with ID "sess-abc123def456"
    When the session is exported without an explicit path
    Then the output filename contains "sess-abc123def456"
    And the file extension is ".md"

  Scenario: Export to explicit file path
    Given a session and an output path "/tmp/custom_export.md"
    When the session is exported to that path
    Then the file is written to "/tmp/custom_export.md"
    And the returned path equals the requested path
