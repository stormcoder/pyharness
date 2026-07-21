# language: en
@agent-setup @story-14-agent-setup
Feature: Agent Setup Error Handling
  As a pyharness user
  I want agent setup errors to appear as in-chat messages rather than shell tracebacks
  So that I can understand what went wrong without seeing raw stack traces

  Background:
    Given pyharness is running with a ChatScreen active

  # ---------------------------------------------------------------------------
  # Bug A — Tool registry failure must not crash to shell
  # ---------------------------------------------------------------------------

  @bug @BUG-AGENT-SETUP-001
  Scenario: Tool registry failure shows in-chat error
    Given the model resolution succeeds
    But the tool registry `get_registry().get_all()` throws an exception
    When I submit a chat message
    Then the agent setup try/except must catch the exception
    And the chat must display "Error setting up agent" followed by the error message
    And the input field must be cleared (event.input.value = "")
    And no raw traceback must appear in the terminal

  # ---------------------------------------------------------------------------
  # Bug A — Graph compilation failure must not crash to shell
  # ---------------------------------------------------------------------------

  @bug @BUG-AGENT-SETUP-002
  Scenario: Graph creation failure shows in-chat error
    Given the model resolution and tool registry succeed
    But `create_agent_graph(model, tools)` throws an exception
    When I submit a chat message
    Then the agent setup try/except must catch the exception
    And the chat must display "Error setting up agent" followed by the error message
    And the input field must be cleared
    And no raw traceback must appear in the terminal

  # ---------------------------------------------------------------------------
  # Bug A — AgentRunner construction failure must not crash to shell
  # ---------------------------------------------------------------------------

  @bug @BUG-AGENT-SETUP-003
  Scenario: AgentRunner constructor failure shows in-chat error
    Given the model resolution, tool registry, and graph creation succeed
    But `AgentRunner(graph, ...)` constructor throws an exception
    When I submit a chat message
    Then the agent setup try/except must catch the exception
    And the chat must display "Error setting up agent" followed by the error message
    And the input field must be cleared
    And no raw traceback must appear in the terminal

  # ---------------------------------------------------------------------------
  # Bug A — All setup code is inside a single try block (structural)
  # ---------------------------------------------------------------------------

  @bug @BUG-AGENT-SETUP-004
  Scenario: All agent setup steps are inside the same try block
    Given the ChatScreen.on_input_submitted handler contains agent setup code
    Then `get_registry().get_all()` must be positioned after the try: and before its matching except:
    And `create_agent_graph(model, tools)` must be positioned after the try: and before its matching except:
    And `AgentRunner()` constructor call must be positioned after the try: and before its matching except:

  # ---------------------------------------------------------------------------
  # Bug A — Input field is cleared after setup failure
  # ---------------------------------------------------------------------------

  @bug @BUG-AGENT-SETUP-005
  Scenario: Input field is cleared when agent setup fails
    Given any step in agent setup throws an exception
    When the except handler runs
    Then `event.input.value` must be set to ""
    So that the user can type a new message without manually clearing the input
