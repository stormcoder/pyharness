# language: en
@chat @output @clipboard @story-phase2-chat
Feature: Copy Chat Output to Clipboard
  As a user
  I want to copy text from the chat output
  So that I can paste agent responses into my editor, notes, or share them

  Background:
    Given the pyharness TUI is running
    And the chat screen is displayed
    And there are messages in the chat output

  # --- Copy all chat ---

  @happy-path
  Scenario: Copy all chat text to clipboard with Ctrl+Shift+C
    When I press Ctrl+Shift+C
    Then a "Chat copied to clipboard" notification appears
    And the clipboard contains all visible chat messages as plain text

  @edge-case
  Scenario: Copy when chat is empty shows warning
    Given the chat output is empty
    When I press Ctrl+Shift+C
    Then a "No chat content to copy" warning notification appears

  # --- Copy last assistant response ---

  @happy-path
  Scenario: Copy last assistant response with Ctrl+Shift+A
    Given the assistant just responded with "Hello! How can I help?"
    When I press Ctrl+Shift+A
    Then the clipboard contains "Hello! How can I help?"

  @edge-case
  Scenario: Copy last response when no assistant has responded
    Given no assistant message has been written yet
    When I press Ctrl+Shift+A
    Then a "No assistant response to copy" notification appears

  # --- Rich markup stripping ---

  @quality
  Scenario: Copied text is plain text without Rich markup
    Given the chat output contains "[bold #58a6ff]You:[/] hello world"
    When I copy the chat text
    Then the clipboard content does NOT contain "[bold"
    And the clipboard content does NOT contain "[/]"
    And the clipboard content contains "You: hello world"

  @quality
  Scenario: Copied tool output is plain text
    Given the chat output contains tool output with "[#d29922]  🔧 bash...[/]"
    When I copy the chat text
    Then the clipboard content does NOT contain Rich markup tags
    And the clipboard content contains the tool name
