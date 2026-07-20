# language: en
@config-persistence @story-11-persistence
Feature: Config Persistence Across App Restarts
  As a pyharness user
  I want my provider connections, model selection, and settings to survive app restarts
  So that I don't have to re-configure everything every time I launch

  Background:
    Given pyharness is installed and has never been launched

  # ---------------------------------------------------------------------------
  # Model persistence
  # ---------------------------------------------------------------------------

  @bug @BUG-PERSIST-001
  Scenario: Model choice survives restart
    When I launch pyharness
    And I switch the active model to "openai:gpt-4o-mini" via `/model`
    And I quit the application gracefully
    And I launch pyharness again
    Then the active model must still be "openai:gpt-4o-mini"
    And the status bar must show "openai:gpt-4o-mini" as the current model

  # ---------------------------------------------------------------------------
  # Provider key persistence
  # ---------------------------------------------------------------------------

  @bug @BUG-PERSIST-001
  Scenario: Provider API keys survive restart
    When I launch pyharness
    And I connect to "openai" with API key "sk-test-provider-key" via `/connect`
    And the connection is verified successfully
    And I quit the application gracefully
    And I launch pyharness again
    Then the "openai" provider must be listed as connected
    And its API key must be "sk-test-provider-key"

  # ---------------------------------------------------------------------------
  # Model list persistence
  # ---------------------------------------------------------------------------

  @bug @BUG-PERSIST-001
  Scenario: Model list is available from persisted provider after restart
    When I launch pyharness
    And I connect to "openai" with a valid API key via `/connect`
    And the connection is verified and models are fetched
    And I quit the application gracefully
    And I launch pyharness again
    Then the provider "openai" must be recognized as connected
    And running `/models` must show models from the OpenAI API
    And the model list must not be empty

  # ---------------------------------------------------------------------------
  # Multi-provider persistence
  # ---------------------------------------------------------------------------

  @bug @BUG-PERSIST-001
  Scenario: Multiple providers survive restart
    When I launch pyharness
    And I connect to "openai" with API key "sk-openai"
    And I connect to "anthropic" with API key "sk-anthropic"
    And I quit the application gracefully
    And I launch pyharness again
    Then both "openai" and "anthropic" must be listed as connected
    And both API keys must be preserved

  # ---------------------------------------------------------------------------
  # Agent and settings persistence
  # ---------------------------------------------------------------------------

  @bug @BUG-PERSIST-001
  Scenario: Settings round-trip through save/load
    When I set a custom model, provider, log level, and agent definition in the config
    And I save the config to disk
    And I load the config from disk
    Then all four settings must match what was saved:
      | model         | provider key | log_level | agent description     |
      | openai:gpt-5  | sk-roundtrip | ERROR     | A custom test agent   |
