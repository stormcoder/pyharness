# language: en
@provider-status @story-13-persistence
Feature: Provider Connection Status Population
  As a pyharness user
  I want the sidebar to accurately show which providers are connected on startup
  So that I can see at a glance which providers are active

  Background:
    Given pyharness has a config file at ~/.config/pyharness/pyharness.json

  # ---------------------------------------------------------------------------
  # Bug B — Empty API key must not show as "connected"
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-001
  Scenario: Provider with empty API key is not marked as connected
    Given the config has a provider entry "bad-provider" with apiKey ""
    When I launch pyharness and _populate_connected_providers runs
    Then "bad-provider" must NOT be in _connected_providers
    And "bad-provider" must be in _provider_status with value False

  # ---------------------------------------------------------------------------
  # Bug B — Placeholder env var with unset env must be status=False
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-002
  Scenario: Provider with unresolved {env:VAR} is not connected
    Given the config has a provider entry "google-genai" with apiKey "{env:GEMINI_API_KEY}"
    And the environment variable "GEMINI_API_KEY" is NOT set
    When I launch pyharness and _populate_connected_providers runs
    Then "google-genai" must NOT be in _connected_providers
    And "google-genai" must be in _provider_status with value False

  # ---------------------------------------------------------------------------
  # Bug B — Placeholder env var with SET env must be status=True
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-003
  Scenario: Provider with resolved {env:VAR} is connected
    Given the config has a provider entry "openai" with apiKey "{env:OPENAI_API_KEY}"
    And the environment variable "OPENAI_API_KEY" is set to "sk-real-key"
    When I launch pyharness and _populate_connected_providers runs
    Then "openai" must be in _connected_providers
    And "openai" must be in _provider_status with value True

  # ---------------------------------------------------------------------------
  # Bug C — Real API key populates both structures
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-004
  Scenario: Provider with non-empty API key is fully connected
    Given the config has a provider entry "deepseek" with apiKey "sk-ds-real"
    When I launch pyharness and _populate_connected_providers runs
    Then "deepseek" must be in _connected_providers
    And "deepseek" must be in _provider_status with value True

  # ---------------------------------------------------------------------------
  # Bug C — None API key → status=False
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-005
  Scenario: Provider with apiKey=None is not connected
    Given the config has a provider entry "unconfigured" with apiKey None
    When I launch pyharness and _populate_connected_providers runs
    Then "unconfigured" must NOT be in _connected_providers
    And "unconfigured" must be in _provider_status with value False

  # ---------------------------------------------------------------------------
  # Bug C — Provider not in config does not appear
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-006
  Scenario: Undefined provider does not appear in provider_status
    Given the config defines only provider "anthropic"
    When I launch pyharness and _populate_connected_providers runs
    Then "nonexistent" must NOT appear in _provider_status
    And "nonexistent" must NOT appear in _connected_providers

  # ---------------------------------------------------------------------------
  # Bug C — Mixed providers (integration)
  # ---------------------------------------------------------------------------

  @bug @BUG-PROVIDER-STATUS-007
  Scenario: Multiple providers with mixed connection states
    Given the config has these providers:
      | name       | apiKey                         |
      | real       | sk-real                        |
      | empty      | ""                             |
      | none       | None                           |
      | env-set    | "{env:SET_VAR}" (env is set)   |
      | env-unset  | "{env:UNSET_VAR}" (env unset)  |
    When I launch pyharness and _populate_connected_providers runs
    Then _connected_providers must contain only "real" and "env-set"
    And _provider_status["real"] must be True
    And _provider_status["empty"] must be False
    And _provider_status["none"] must be False
    And _provider_status["env-set"] must be True
    And _provider_status["env-unset"] must be False
