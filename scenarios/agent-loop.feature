# language: en
# Story: Agent Loop — Core agent execution, tool calling, error recovery
# Associated with: SPEC §5 (Agent System), §13 (Provider Bridge)

@agent-loop @critical
Feature: Agent Loop Execution

  Background:
    Given a configured pyharness session with FakeLLMProvider
    And the build agent is active
    And the tool registry contains: bash, read, write, edit, grep, glob

  # --- Happy Path ---

  Scenario: Simple message round-trip without tool calls
    When the user sends the message "What is Python?"
    And the fake provider responds with a text-only response
    Then the response is displayed in the chat area
    And the session message count is incremented by 2

  Scenario: Single tool call — read a file
    When the user sends the message "Read setup.py"
    And the fake provider returns a tool_call for "read" with path="setup.py"
    Then the read tool is executed
    And the file contents are injected as a tool result into the next LLM request
    And the fake provider responds with analysis of the file
    And the tool call is displayed in the chat area with its output

  Scenario: Multi-step tool sequence — edit then test
    When the user sends the message "Fix the bug in main.py and run tests"
    And the fake provider returns tool_call for "edit" on main.py
    Then the edit tool is executed and the file is modified
    And the fake provider then returns tool_call for "bash" with "pytest tests/"
    Then the bash tool is executed
    And the test output is displayed
    And the fake provider responds with a summary

  Scenario: Agent switching via Tab key
    Given the build agent is active
    When the user presses Tab
    Then the agent switches to plan
    And the header displays "[Plan]"
    When the user presses Tab again
    Then the agent switches back to build
    And the header displays "[Build]"

  # --- Tool Call Error Handling ---

  Scenario: LLM returns malformed tool call JSON
    When the user sends a message
    And the fake provider returns a tool_call with malformed JSON arguments
    Then the agent loop catches the JSON parse error
    And an error message is sent back to the LLM: "Invalid tool arguments: {error}"
    And the TUI does not crash
    And the session remains in the active state

  Scenario: LLM returns tool name not in registry
    When the user sends a message
    And the fake provider returns a tool_call for "sudo_wipe_system"
    Then the agent loop rejects the unknown tool
    And responds to the LLM with "Tool 'sudo_wipe_system' not found. Available tools: bash, read, write, edit, grep, glob"
    And the tool is NOT executed

  Scenario: Tool call with missing required parameter
    When the user sends a message
    And the fake provider returns a tool_call for "read" without the required "path" parameter
    Then the tool execution layer reports "Missing required parameter: path"
    And the error is sent back to the LLM for correction

  Scenario: Tool execution exceeds output size limit
    When the user sends a message triggering a bash command
    And the bash command produces 50MB of output
    Then the output is truncated at the configured limit (default 1MB)
    And the truncated output includes the note "[Output truncated at 1MB — 49MB omitted]"
    And the full output is saved to a temp file for reference

  # --- Streaming & Interruption ---

  Scenario: Streaming response arrives in chunks
    When the user sends a message
    And the fake provider streams a response in 5 chunks over 500ms
    Then each chunk is rendered in the chat area as it arrives
    And the final rendered message is complete and correct

  Scenario: Stream ends with incomplete tool call
    When the user sends a message
    And the fake provider begins streaming a tool_call JSON
    And the stream terminates before the JSON is complete
    Then the agent loop detects the incomplete tool call
    And displays "Stream ended with incomplete tool call — retrying..."
    And the LLM is re-prompted with the partial response and a request to retry

  Scenario: User interrupts streaming response with Escape
    When the user sends a message
    And the fake provider is in the middle of streaming a long response
    And the user presses Escape
    Then the stream is cancelled
    And the partial response is preserved in the chat
    And the session enters the "interrupted" state
    And the status bar shows "[Interrupted — press Enter to resume]"

  # --- Provider Errors ---

  Scenario: Provider returns rate limit (429)
    When the user sends a message
    And the fake provider responds with HTTP 429 and Retry-After: 30
    Then the agent waits 30 seconds before retrying
    And the status bar shows "Rate limited — retrying in 30s..."
    And the chat displays a rate-limit warning
    And after the wait, the request is retried successfully

  Scenario: Provider persistently fails after retries exhausted
    When the user sends a message
    And the fake provider returns HTTP 500 for all retries
    Then after max retries (default 3) the agent stops
    And the error "Provider unavailable after 3 retries" is displayed
    And the full message history is preserved
    And a "Try again?" prompt appears

  Scenario: Provider returns empty response
    When the user sends a message
    And the fake provider returns a response with no content and no tool calls
    Then the message "Model returned no response. Try rephrasing your request." is displayed
    And the session remains active

  # --- Context Window ---

  Scenario: Auto-compaction triggers before context limit
    Given the session has 50,000 tokens of message history
    And the model's max context is 100,000 tokens
    And compaction reserved tokens is 10,000
    When the user sends a message that would push context to 95,000 tokens
    Then auto-compaction triggers
    And older messages are summarized
    And the new context size is under 80,000 tokens
    And the chat displays "[Context compacted — older messages summarized]"

  Scenario: Manual compaction via /compact
    When the user sends the command "/compact"
    Then the agent summarizes the conversation history
    And replaces older messages with a single summary message
    And displays "[Session compacted — {N} messages summarized]"
    And preserved token count is displayed in the status bar

  # --- Agent Loop Edge Cases ---

  Scenario: Maximum tool call iterations limit
    When the fake provider returns tool_calls in an infinite loop pattern
    And the agent has executed 50 tool calls in a single turn
    Then the agent stops with "Reached maximum tool call iterations (50)"
    And the user is prompted: "Agent is looping — continue or stop?"

  Scenario: Rapid consecutive user messages while agent is busy
    When the user sends message A
    And the agent begins processing message A
    And the user sends message B before A completes
    Then message B is queued
    And message B is processed after A completes
    And both responses are displayed in order
