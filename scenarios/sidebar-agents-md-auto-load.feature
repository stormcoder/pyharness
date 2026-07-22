# language: en
@sidebar @agents-md @bug-SIDEBAR-AGENTS-001
Feature: Sidebar Auto-Loads AGENTS.md on Mount
  As a pyharness user
  I want the sidebar to automatically display AGENTS.md content when the app starts
  So that I can see project instructions without running /init first

  Background:
    Given pyharness has a sidebar with an AGENTS.md section
    And the project root may or may not contain AGENTS.md

  # ---------------------------------------------------------------------------
  # Story: refresh_agents_md method reads project AGENTS.md
  # ---------------------------------------------------------------------------

  @story-1 @source-inspection
  Scenario: refresh_agents_md method exists and is callable
    When I inspect the Sidebar class
    Then it must have a method named "refresh_agents_md"
    And that method must be callable

  @story-1 @source-inspection
  Scenario: refresh_agents_md reads from correct file path
    When I inspect the source of Sidebar.refresh_agents_md
    Then it must use "Path.cwd()" and "AGENTS.md"

  @story-1 @source-inspection
  Scenario: refresh_agents_md checks file existence before reading
    When I inspect the source of Sidebar.refresh_agents_md
    Then it must call ".exists()" before reading the file

  @story-1 @source-inspection
  Scenario: refresh_agents_md targets correct widget
    When I inspect the source of Sidebar.refresh_agents_md
    Then it must query the widget with id "agents-content"

  # ---------------------------------------------------------------------------
  # Story: Sidebar mounts and auto-refreshes AGENTS.md
  # ---------------------------------------------------------------------------

  @story-2 @source-inspection
  Scenario: Sidebar defines on_mount lifecycle hook
    When I inspect the Sidebar class
    Then it must define an "on_mount" method

  @story-2 @source-inspection
  Scenario: Sidebar on_mount triggers refresh_agents_md
    When I inspect the source of Sidebar.on_mount
    Then it must call "self.refresh_agents_md()"

  # ---------------------------------------------------------------------------
  # Story: ChatScreen also refreshes sidebar as safety net
  # ---------------------------------------------------------------------------

  @story-3 @source-inspection
  Scenario: ChatScreen on_mount calls sidebar refresh
    When I inspect the source of ChatScreen.on_mount
    Then it must call "refresh_agents_md" on the sidebar widget

  # ---------------------------------------------------------------------------
  # Story: AGENTS.md found → sidebar shows "found:"
  # ---------------------------------------------------------------------------

  @story-4 @runtime
  Scenario: Sidebar shows "found:" when AGENTS.md exists in project root
    Given a temporary directory with a valid AGENTS.md file
    And the working directory is set to that directory
    When I mount the Sidebar widget and call refresh_agents_md()
    Then the "#agents-content" Static widget text must contain "found:"
    And the text must NOT contain "Run /init"

  @story-4 @runtime
  Scenario: Sidebar on_mount auto-loads AGENTS.md content
    Given a temporary directory with a valid AGENTS.md file
    And the working directory is set to that directory
    When I mount the Sidebar widget
    Then the "#agents-content" Static widget text must contain "found:"
    And the text must NOT contain "Run /init"

  # ---------------------------------------------------------------------------
  # Story: AGENTS.md missing → sidebar shows init message
  # ---------------------------------------------------------------------------

  @story-5 @runtime
  Scenario: Sidebar shows "Run /init" when no AGENTS.md in project root
    Given a temporary directory without an AGENTS.md file
    And the working directory is set to that directory
    When I mount the Sidebar widget and call refresh_agents_md()
    Then the "#agents-content" Static widget text must contain "Run /init"
    And the text must NOT contain "found:"

  @story-5 @runtime
  Scenario: Sidebar on_mount shows init message when no AGENTS.md
    Given a temporary directory without an AGENTS.md file
    And the working directory is set to that directory
    When I mount the Sidebar widget
    Then the "#agents-content" Static widget text must contain "Run /init"
