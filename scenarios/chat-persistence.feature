# language: en
# Story: Chat Message Persistence — Messages stored during conversation
# Associated with: SPEC §4.2 (Chat Interface), SPEC §6 (Session System)
# Bug: ChatScreen._run_agent() never persists messages to SessionStore
# Bug: /export always returns empty transcript (0 messages)

@persistence @chat @export
Feature: Chat Message Persistence

  Background:
    Given pyharness is configured with test fixtures
    And a FakeSessionStore is active with in-memory storage
    And a session "sess-test" has been created

  # --- User Message Persistence ---

  Scenario: User message is stored in SessionStore after sending
    Given session "sess-test" has 0 messages
    When the user types "Write a Python script" and presses Enter
    Then the session has at least 1 message
    And the most recent message has role "user"
    And the most recent message content is "Write a Python script"

  Scenario: User message is stored immediately before agent runs
    Given session "sess-test" is active
    When the user sends a message
    Then the user message is stored BEFORE the agent begins processing
    And the session message count increments by 1 immediately

  # --- Assistant Response Persistence ---

  Scenario: Assistant response is stored after agent completes
    Given session "sess-test" has 1 user message
    When the agent responds with "I'll create that script for you"
    Then the session has at least 2 messages
    And the most recent message has role "assistant"
    And the most recent message content is "I'll create that script for you"

  # --- Tool Call Persistence ---

  Scenario: Tool call is stored with name, args, and result
    Given session "sess-test" is active
    When the agent invokes a "read" tool with args {"filePath": "src/main.py"}
    And the tool returns result "print('hello')"
    Then the session has a message with role "tool"
    And the tool message has tool_name "read"
    And the tool message has tool_args {"filePath": "src/main.py"}
    And the tool message has tool_result "print('hello')"

  Scenario: Multiple tool calls in one agent turn are all stored
    Given session "sess-test" is active
    When the agent invokes "read" then "write" tools
    Then the session has 2 tool messages
    And the tool messages appear in invocation order

  # --- Export Has Full Transcript ---

  Scenario: Export contains all user, assistant, and tool messages
    Given session "sess-test" has:
      | role      | content                        |
      | user      | Create a Python script         |
      | tool      | write -> File written          |
      | assistant | I've created hello.py for you  |
    When the user runs "/export"
    Then the exported file contains "Create a Python script"
    And the exported file contains "File written"
    And the exported file contains "I've created hello.py for you"

  Scenario: Export preserves chronological message order
    Given session "sess-test" has messages sent in order: msg1, msg2, msg3, msg4, msg5
    When the session is exported
    Then msg1 appears before msg2 in the export
    And msg2 appears before msg3
    And msg3 appears before msg4
    And msg4 appears before msg5

  Scenario: Export contains correct message count in header
    Given session "sess-test" has 5 messages
    When the session is exported
    Then the header shows "**Messages:** 5"

  Scenario: Export contains updated total token count
    Given session "sess-test" has accumulated 2500 tokens
    When the session is exported
    Then the header shows "**Total Tokens:** 2500"

  # --- Multi-Turn Conversations ---

  Scenario: Three user-assistant turn pairs are all preserved
    Given session "sess-test" is active
    When the user and assistant exchange 3 turns each
    Then the session has 6 messages
    And all 6 messages appear in the export in correct order

  Scenario: Session metadata is updated after each message
    Given session "sess-test" has updated_at showing 12:00
    When a new message is added
    Then the session updated_at is more recent than 12:00
    And the session total_tokens increases

  # --- Rich Markup in Export ---

  Scenario: Rich markup is stripped in export but not in session store
    Given the assistant responds with "[bold #58a6ff]Hello![/] plain text"
    When the message is stored in SessionStore
    Then the stored content retains the rich markup
    When the session is exported to markdown
    Then the exported content is "Hello! plain text"
    And "[bold #58a6ff]" is NOT in the export
