# language: en
# Story: Permission System — Allow/ask/deny, agent permissions, glob patterns
# Associated with: SPEC §5.1, §5.2, §7

@permission @security
Feature: Permission System

  Background:
    Given pyharness is configured with default permissions:
      | tool    | default |
      | edit    | ask     |
      | bash    | ask     |
      | read    | allow   |
      | grep    | allow   |
      | glob    | allow   |
    And the build agent is active

  # --- Global Permission Rules ---

  Scenario: Ask permission for bash execution
    Given the permission for "bash" is "ask"
    When the agent attempts to execute a bash command
    Then the user is prompted: "Allow bash: npm test?"
    And the agent pauses until the user responds
    When the user selects "Allow"
    Then the command executes
    And the tool result is displayed

  Scenario: Deny permission for bash execution
    Given the permission for "bash" is "ask"
    When the agent attempts to execute a bash command
    And the user selects "Deny"
    Then the command is NOT executed
    And the agent receives "Permission denied by user" as the tool result
    And the agent can suggest an alternative approach

  Scenario: Auto-deny after timeout
    Given the permission for "bash" is "ask"
    And the permission timeout is set to 60 seconds
    When the agent requests bash execution
    And the user does not respond within 60 seconds
    Then the permission is auto-denied
    And the agent receives "Permission timed out (auto-denied)"

  Scenario: Allow-all mode for specific tool
    Given the permission for "bash" is configured as "allow"
    When the agent executes a bash command
    Then the command runs without prompting the user
    And no permission dialog appears

  # --- Agent-Level Permissions ---

  Scenario: Plan agent cannot execute bash even if global is allow
    Given global permission for "bash" is "allow"
    And plan agent has "bash: deny" in its agent config
    When the plan agent attempts to execute a bash command
    Then the command is denied
    And the agent receives "Permission denied: plan agent cannot execute bash"
    And the global "allow" is ignored

  Scenario: Subagent inherits parent permission ceiling
    Given the build agent has "bash: deny"
    When the build agent spawns a general subagent with "bash: allow"
    Then the general subagent inherits "bash: deny" from its parent
    And the subagent's more permissive config is ignored

  Scenario: Subagent can have stricter permissions than parent
    Given the build agent has "bash: allow"
    When the build agent spawns a general subagent with "bash: deny"
    Then the general subagent has "bash: deny"
    And least privilege is enforced

  # --- File Path Permissions ---

  Scenario: Read file within workspace
    Given the workspace is /home/user/project/
    When the agent reads "/home/user/project/src/main.py"
    Then the read is allowed (path is within workspace)

  Scenario: Read file outside workspace
    Given the workspace is /home/user/project/
    When the agent attempts to read "/etc/passwd"
    Then the read is denied: "Path outside workspace: /etc/passwd"
    And the permission "external_directory" is checked

  Scenario: Path traversal attempt
    Given the workspace is /home/user/project/
    When the agent attempts to read "/home/user/project/../../../etc/passwd"
    Then the realpath resolves to "/etc/passwd"
    And the read is denied: "Path outside workspace"

  Scenario: Symlink escape attempt
    Given the workspace is /home/user/project/
    And a symlink "safe_link" exists pointing to "/etc/passwd"
    When the agent attempts to read "safe_link"
    Then the realpath is resolved before validation
    And the read is denied: "Symlink target outside workspace"

  # --- Bash Permission Patterns ---

  Scenario: Glob pattern matches allowed command
    Given the bash permission glob is "npm *, pytest *, git *"
    When the agent executes "npm test"
    Then the command is allowed (matches "npm *")

  Scenario: Glob pattern does NOT match
    Given the bash permission glob is "npm *, pytest *"
    When the agent executes "rm -rf node_modules"
    Then the permission falls back to "ask"
    And the user is prompted

  Scenario: Empty or wildcard-only glob
    Given the bash permission glob is "*"
    When the config is loaded
    Then a warning is displayed: "Bash permission glob is '*' — ALL commands allowed"
    Or (if safety mode): the config is rejected with "Wildcard bash glob not permitted in safe mode"

  Scenario: Multiple glob patterns
    Given the bash permission glob is "npm *, pytest *, git status, git diff, git log"
    When the agent executes "git log --oneline"
    Then the command is allowed (matches "git log")
    When the agent executes "git push --force"
    Then the command requires user approval (does not match any pattern)

  # --- Config Validation ---

  Scenario: Circular permission references rejected
    Given agent A references agent B's permissions
    And agent B references agent A's permissions
    When the config is loaded
    Then the error "Circular permission reference: A → B → A" is displayed
    And the config load fails

  Scenario: Unknown permission key
    Given the config contains "permission: { "sudo": "allow" }"
    When the config is loaded
    Then the warning "Unknown permission key: 'sudo'" is logged
    And "sudo" is not added to the permission registry

  # --- Headless/CLI Mode ---

  Scenario: Ask permission in headless mode defaults to deny
    Given pyharness is running in CLI mode ("pyharness run")
    And --yes flag is NOT set
    And the permission for "bash" is "ask"
    When the agent attempts to execute a bash command
    Then the permission auto-denies
    And a message is logged: "[CLI] Auto-denied bash: no user to ask"

  Scenario: Ask permission in headless mode with --yes flag
    Given pyharness is running in CLI mode
    And --yes flag IS set
    And the permission for "bash" is "ask"
    When the agent attempts to execute a bash command
    Then the permission auto-allows
    And a message is logged: "[CLI] Auto-allowed bash: --yes flag"
