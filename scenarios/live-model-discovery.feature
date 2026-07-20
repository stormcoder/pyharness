# language: en
@live-model-discovery @story-10-model-fetch
Feature: Live Model Discovery
  As a pyharness user
  I want model discovery to query each provider's own API
  So that I always see the actual available models, never stale hardcoded lists

  Background:
    Given pyharness is configured with provider API keys

  # ---------------------------------------------------------------------------
  # Per-provider API queries
  # ---------------------------------------------------------------------------

  Scenario: Fetch models from OpenAI API
    When the user has connected to "openai" with API key "sk-test-openai"
    And the OpenAI API at https://api.openai.com/v1/models returns:
      """
      {"data": [{"id": "gpt-5"}, {"id": "gpt-4o-mini"}]}
      """
    Then `fetch_models()` must return ["openai:gpt-5", "openai:gpt-4o-mini"]

  Scenario: Fetch models from DeepSeek API
    When the user has connected to "deepseek" with API key "sk-test-ds"
    And the DeepSeek API at https://api.deepseek.com/models returns:
      """
      {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}
      """
    Then `fetch_models()` must return ["deepseek:deepseek-chat", "deepseek:deepseek-reasoner"]

  Scenario: Fetch models from Anthropic API
    When the user has connected to "anthropic" with API key "sk-ant-test"
    And the Anthropic API at https://api.anthropic.com/v1/models returns:
      """
      {"data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-opus-4-5"}]}
      """
    Then `fetch_models()` must return ["anthropic:claude-sonnet-4-5", "anthropic:claude-opus-4-5"]

  Scenario: Fetch models from Google GenAI API
    When the user has connected to "google-genai" with API key "sk-test-google"
    And the Google API at https://generativelanguage.googleapis.com/v1beta/models returns:
      """
      {"models": [{"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"}]}
      """
    Then `fetch_models()` must return ["google-genai:models/gemini-2.5-pro"]

  # ---------------------------------------------------------------------------
  # No static fallbacks
  # ---------------------------------------------------------------------------

  Scenario: No _VERIFY_MODELS fallback dict must remain
    When importing `from pyharness.core.provider import _VERIFY_MODELS`
    Then an `ImportError` must be raised
    Because all model IDs must come from live provider API queries

  # ---------------------------------------------------------------------------
  # Custom baseUrl support
  # ---------------------------------------------------------------------------

  Scenario: Use provider baseUrl for model discovery
    Given a provider "custom-provider" is configured with:
      | apiKey      | sk-custom                            |
      | baseUrl     | https://my-llm.example.com/v1        |
    When `fetch_models()` is called with connected={"custom-provider"}
    Then the HTTP request must target https://my-llm.example.com/v1/models
    And models returned from that endpoint must be prefixed "custom-provider:"

  # ---------------------------------------------------------------------------
  # API failure handling
  # ---------------------------------------------------------------------------

  Scenario: API failure returns empty list with no fallback
    When the user has connected to "openai" with a bad API key
    And the OpenAI API returns HTTP 401
    Then `fetch_models()` must return an empty list []
    And no hardcoded models must leak from `_VERIFY_MODELS`

  # ---------------------------------------------------------------------------
  # Mixed providers
  # ---------------------------------------------------------------------------

  Scenario: All connected providers queried simultaneously
    When the user has connected to "openai", "deepseek", and "anthropic"
    And each provider's API returns its model list
    Then `fetch_models()` must return all models from all three providers
    And no duplicates must appear
    And no models from unconnected providers must appear

  # ---------------------------------------------------------------------------
  # TUI integration
  # ---------------------------------------------------------------------------

  Scenario: /models dropdown shows live API results
    When the user connects to "openai" with a valid API key
    And the OpenAI API returns {"data": [{"id": "gpt-5"}, {"id": "gpt-4o-mini"}]}
    And the user types "/models" in the TUI chat input
    Then the models dropdown must show "openai:gpt-5" and "openai:gpt-4o-mini"
    And must NOT show any model from a hardcoded static list
