# language: en
@chat @input @dispatch @story-phase2-chat
Feature: Chat Input Message Dispatch
  As a user
  I want my chat messages to be correctly routed to the agent, slash commands,
  or bash execution based on prefix
  So that I don't accidentally run shell commands

  Background:
    Given the pyharness TUI is running
    And the chat screen is displayed
    And a provider is connected
    And a model is selected

  # --- Normal chat messages ---

  @happy-path
  Scenario: Normal message is dispatched to the agent runner
    When I type "What is Python?" in the chat input
    And I press Enter
    Then the message "You: What is Python?" appears in the chat output
    And the agent runner is invoked with the message
    And the message does NOT execute as a bash command

  @happy-path
  Scenario: Message containing ! in the middle does not trigger bash
    When I type "This is important! Please help" in the chat input
    And I press Enter
    Then the message appears in the chat output as a normal message
    And the message is dispatched to the agent runner
    And bash is NOT invoked

  @happy-path
  Scenario: Message containing / in the middle does not trigger slash command
    When I type "I need help with /tmp files" in the chat input
    And I press Enter
    Then the message appears in the chat output as a normal message
    And the message is dispatched to the agent runner
    And no slash command is dispatched

  @edge-case
  Scenario: Empty input is silently ignored
    When I type only whitespace "   " in the chat input
    And I press Enter
    Then nothing is written to the chat output
    And the input field is NOT cleared

  @edge-case
  Scenario: Input with leading/trailing whitespace is trimmed
    When I type "  hello world  " in the chat input
    And I press Enter
    Then the message "You: hello world" appears in the chat output

  # --- Bash command injection ---

  @happy-path
  Scenario: Bash command is executed when message starts with !
    When I type "! echo hello" in the chat input
    And I press Enter
    Then "! echo hello" appears in the chat output
    And the bash output "hello" appears in the chat output

  @edge-case
  Scenario: Empty bash command shows empty message
    When I type "!" in the chat input
    And I press Enter
    Then "(empty command)" appears in the chat output

  @edge-case
  Scenario: Bash command with only whitespace after ! shows empty message
    When I type "!   " in the chat input
    And I press Enter
    Then "(empty command)" appears in the chat output

  # --- Slash command dispatch ---

  @happy-path
  Scenario: Known slash command is dispatched
    When I type "/help" in the chat input
    And I press Enter
    Then the help text appears in the chat output listing all commands

  @happy-path
  Scenario: Partial slash command shows autocomplete suggestions
    When I type "/mode" in the chat input
    And I press Enter
    Then autocomplete suggestions for "/model" and "/models" appear

  @edge-case
  Scenario: Unknown slash command shows error
    When I type "/unknowncommand123" in the chat input
    And I press Enter
    Then an "Unknown command" error appears in the chat output

  # --- Search mode safety ---

  @bug @regression @BUG-001
  Scenario: Exiting search mode with Enter restores original input
    Given I previously submitted "! echo hello" as a bash command
    And I typed "What is Python?" in the chat input
    When I press Ctrl+R to enter search mode
    And I filter to the "! echo hello" history entry
    And I press Enter to exit search mode
    Then the input field shows "What is Python?" (my original message)
    And NOT "! echo hello"

  @bug @regression @BUG-001
  Scenario: Exiting search mode with Escape restores original input
    Given I previously submitted "! echo hello" as a bash command
    And I typed "What is Python?" in the chat input
    When I press Ctrl+R to enter search mode
    And I filter to the "! echo hello" history entry
    And I press Escape to exit search mode
    Then the input field shows "What is Python?" (my original message)
    And NOT "! echo hello"

  @bug @regression @BUG-001
  Scenario: Pressing Enter after accidental search-mode exit does not execute stale history
    Given search mode was entered and exited with Enter
    And the input field was contaminated with "! rm -rf /"
    When I press Enter again
    Then my ORIGINAL message is submitted
    And "! rm -rf /" is NOT executed as a bash command
