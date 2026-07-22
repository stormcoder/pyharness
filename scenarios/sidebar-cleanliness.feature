# language: en
@sidebar @config @bug-SIDEBAR-LEAK-001
Feature: Sidebar Provider Cleanliness
  As a pyharness user
  I want the sidebar to only display providers I have actually configured
  So that stale or removed providers do not appear as options

  Background:
    Given pyharness loads configuration from ~/.config/pyharness/pyharness.json
    And config files can contain entries from previously configured providers

  # ---------------------------------------------------------------------------
  # Story: Config loading excludes removed providers
  # ---------------------------------------------------------------------------

  @story-1 @load_config
  Scenario: Custom config file has only the expected providers
    Given a temp config file "/tmp/test/pyharness.json" with only provider "deepseek"
    And the environment variable "PYHARNESS_CONFIG" points to that file
    When I call load_config()
    Then config.provider must contain ONLY {"deepseek"}
    And config.provider must NOT contain "bad"
    And config.provider must NOT contain "bad-provider"

  @story-1 @load_config @regression
  Scenario: Global config bad entries do not leak through custom config
    Given "~/.config/pyharness/pyharness.json" has providers {"bad-provider", "bad", "deepseek"}
    And "PYHARNESS_CONFIG" points to a file with only provider "deepseek"
    When I call load_config()
    Then config.provider must contain ONLY {"deepseek"}
    And config.provider must NOT contain "bad" or "bad-provider"
    # NOTE: This is xfail — _merge_configs deep-merges provider dicts,
    # allowing global entries to leak through.

  @story-1 @inline-config
  Scenario: Inline config via PYHARNESS_CONFIG_CONTENT excludes bad providers
    Given the environment variable "PYHARNESS_CONFIG_CONTENT" contains a JSON blob with only "deepseek"
    When I call load_config()
    Then config.provider must contain ONLY {"deepseek"}
    And config.provider must NOT contain "bad" or "bad-provider"

  # ---------------------------------------------------------------------------
  # Story: Provider status population is clean
  # ---------------------------------------------------------------------------

  @story-2 @populate
  Scenario: _populate_connected_providers only processes config providers
    Given self.config has provider entries only for "deepseek"
    When _populate_connected_providers() runs
    Then _provider_status must NOT contain "bad"
    And _provider_status must NOT contain "bad-provider"
    And any keys in _provider_status must be from config.provider

  @story-2 @populate @stale
  Scenario: Re-populating clears stale injected entries
    Given _provider_status has stale entries {"bad": True, "bad-provider": False}
    And self.config has only "deepseek"
    When _provider_status is reset and _populate_connected_providers() runs again
    Then _provider_status must NOT contain "bad"
    And _provider_status must NOT contain "bad-provider"

  # ---------------------------------------------------------------------------
  # Story: save_config removes stale disk entries
  # ---------------------------------------------------------------------------

  @story-3 @save
  Scenario: Saving a clean config writes only configured providers
    Given a PyHarnessConfig with only provider "deepseek"
    When I call save_config(config) to disk
    Then the written file's provider section must contain only "deepseek"
    And the written file's provider section must NOT contain "bad"

  @story-3 @save @replace
  Scenario: save_config replaces the full provider section
    Given a file on disk has providers {"bad-provider", "bad", "deepseek"}
    When I save_config with a config containing only "deepseek"
    Then the re-read file must contain only "deepseek" in the provider section
    And "bad-provider" must be gone from the file
    And "bad" must be gone from the file

  # ---------------------------------------------------------------------------
  # Story: Sidebar widget displays clean provider text
  # ---------------------------------------------------------------------------

  @story-4 @sidebar
  Scenario: Sidebar renders only the providers passed to it
    Given a mounted Sidebar widget
    When I call update_provider_status({"deepseek": True})
    Then the #providers-status text must contain "deepseek"
    And the #providers-status text must NOT contain "bad"

  @story-4 @sidebar @app-chain
  Scenario: Full app chain renders clean sidebar text
    Given a running PyHarnessApp with only deepseek in provider config
    And _provider_status is {"deepseek": True}
    When _update_sidebar_providers() runs
    Then the Sidebar #providers-status text must contain "deepseek"
    And the Sidebar #providers-status text must NOT contain "bad"
    And the Sidebar #providers-status text must NOT contain "bad-provider"

  # ---------------------------------------------------------------------------
  # Story: Full integration chain
  # ---------------------------------------------------------------------------

  @story-5 @integration
  Scenario: Full chain — config → load → populate → sidebar — is clean
    Given a config with only "deepseek"
    When I trace the full chain:
      | Step | Component               | Action                              |
      | 1    | config.loader.load_config | Load from clean temp file           |
      | 2    | PyHarnessConfig          | Validate clean config               |
      | 3    | _populate_connected_providers | Build _provider_status          |
      | 4    | Sidebar.update_provider_status | Render to sidebar text         |
    Then at no point does "bad" or "bad-provider" appear in any structure
    And the final sidebar text contains only "deepseek"

  @story-5 @integration @roundtrip
  Scenario: Full persistence round-trip is clean
    Given a clean config on disk with only "deepseek"
    When I load_config() → save_config() → re-read disk
    Then the re-read file contains only "deepseek" in providers
    And "bad" and "bad-provider" are absent
