# language: en
# story: Connected Provider Model Filtering
# feature: /models dropdown only shows models from providers that have been connected
# spec-reference: SPEC §10 (Provider Bridge)

Feature: Connected Provider Model Filtering
  As a user who has connected only some providers
  I want the /models dropdown to show only models from connected providers
  So that I am not confused by models from providers I haven't set up

  Background:
    Given a pyharness configuration with multiple providers
    And only a subset of those providers have been connected
    And the app has started and populated its connected-provider tracking

  # --------------------------------------------------------------------------
  # Scenario 1: Connected providers filter restricts model list
  # --------------------------------------------------------------------------

  Scenario: Fetch models only from connected providers
    Given the config has "deepseek" and "openrouter" configured
    And "deepseek" has a real API key
    And "openrouter" has an unresolved {env:VAR} placeholder
    When fetch_models is called with providers={"deepseek"}
    Then only models prefixed with "deepseek:" are returned
    And no models prefixed with "openrouter:" appear in the result

  # --------------------------------------------------------------------------
  # Scenario 2: Empty connected set returns empty model list
  # --------------------------------------------------------------------------

  Scenario: No connected providers returns empty model list
    Given the config has multiple providers configured
    But none are connected (all have unresolved placeholders or empty keys)
    When fetch_models is called with providers=set()
    Then an empty list is returned

  # --------------------------------------------------------------------------
  # Scenario 3: Backward compatibility — no filter includes all
  # --------------------------------------------------------------------------

  Scenario: No filter includes all configured providers
    Given the config has "openrouter" configured with a real API key
    When fetch_models is called without a providers filter
    Then models from all configured providers are returned

  # --------------------------------------------------------------------------
  # Scenario 4: /models dropdown shows only connected provider models
  # --------------------------------------------------------------------------

  Scenario: /models dropdown filters to connected providers
    Given the app has deepseek, openrouter, and ollama in its config
    And only "deepseek" is connected (has a real API key)
    And the model cache contains models from all three providers
    When the user types "/models" and presses Enter
    Then the models dropdown appears
    And only deepseek-prefixed models are visible
    And no openrouter or ollama models are visible

  # --------------------------------------------------------------------------
  # Scenario 5: /models dropdown empty when no providers connected
  # --------------------------------------------------------------------------

  Scenario: /models dropdown shows empty state with no connected providers
    Given the app has providers configured with env-var placeholders
    And no environment variables are set for those placeholders
    When the user types "/models" and presses Enter
    Then the dropdown shows an empty-state or guidance message
    And the message indicates no providers are connected

  # --------------------------------------------------------------------------
  # Scenario 6: {env:VAR} placeholder resolved at startup
  # --------------------------------------------------------------------------

  Scenario: Env-var placeholder with set variable counts as connected
    Given the config has a provider with apiKey "{env:ANTHROPIC_API_KEY}"
    And the environment variable "ANTHROPIC_API_KEY" is set to a real key
    When the app populates _connected_providers on startup
    Then that provider is added to _connected_providers

  # --------------------------------------------------------------------------
  # Scenario 7: {env:VAR} placeholder NOT resolved → not connected
  # --------------------------------------------------------------------------

  Scenario: Unresolved env-var placeholder does not count as connected
    Given the config has a provider with apiKey "{env:OPENROUTER_NOT_SET}"
    And the environment variable "OPENROUTER_NOT_SET" is NOT set
    When the app populates _connected_providers on startup
    Then that provider is NOT added to _connected_providers

  # --------------------------------------------------------------------------
  # Scenario 8: Provider added to connected set after /connect
  # --------------------------------------------------------------------------

  Scenario: Provider added to connected set after successful /connect
    Given the app has an empty _connected_providers set
    And the user opens the connect dialog for "openai"
    And the connection is verified successfully
    When the connect result is handled
    Then "openai" is added to _connected_providers
    And the sidebar provider status is updated

  # --------------------------------------------------------------------------
  # Scenario 9: Multiple connects accumulate providers
  # --------------------------------------------------------------------------

  Scenario: Connecting multiple providers accumulates in the set
    Given the user has connected to "deepseek"
    When the user connects to "openai"
    Then _connected_providers contains both "deepseek" and "openai"
    And neither provider was removed from the set

  # --------------------------------------------------------------------------
  # Scenario 10: Deepseek-only connected, models dropdown works
  # --------------------------------------------------------------------------

  Scenario: Only deepseek connected shows deepseek models
    Given only "deepseek" is configured as a provider in the config
    And "deepseek" is connected
    When fetch_models is called with providers={"deepseek"}
    Then all returned models are prefixed with "deepseek:"
    And no models from other providers appear
