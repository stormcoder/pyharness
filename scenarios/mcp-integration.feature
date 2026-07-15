# language: en
# Story: MCP Integration — Server lifecycle, tool discovery, crash recovery
# Associated with: SPEC §8 (MCP Server Support)

@mcp @integration
Feature: MCP Server Integration

  Background:
    Given pyharness is configured with an MCP server config:
      | name    | type   | command/url                          |
      | test-srv| local  | ["python", "-m", "test_mcp_server"]  |
      | remote  | remote | https://mcp.example.com/mcp          |
    And FakeLLMProvider is active

  # --- Server Lifecycle ---

  Scenario: Local MCP server starts on session open
    When a new session is started
    Then the test-srv MCP server process is started
    And the status bar shows "[MCP: test-srv ✓]"
    And available tools from the server are registered as "test-srv_<toolname>"

  Scenario: Local MCP server fails to start
    Given the MCP server command is invalid
    When a new session is started
    Then the MCP server fails to start after timeout (default 60s)
    And the status shows "[MCP: test-srv ✗ — failed to start]"
    And pyharness continues without that server's tools
    And a detailed error is logged

  Scenario: Remote MCP server is unreachable
    Given the remote MCP server URL is unreachable
    When a new session is started
    Then connection fails after configured retries
    And the status shows "[MCP: remote ✗ — unreachable]"
    And pyharness starts without remote tools

  Scenario: Disable an MCP server in config
    Given test-srv has "enabled: false" in config
    When a new session is started
    Then test-srv is NOT started
    And no tools from test-srv are registered

  # --- Tool Discovery and Namespacing ---

  Scenario: Tools are namespaced by server name
    Given test-srv exposes tools: ["search", "list_items"]
    When the session starts
    Then tools are registered as "test-srv_search" and "test-srv_list_items"
    And they appear in the tool list with their server prefix

  Scenario: Server declares zero tools
    Given test-srv starts but declares no tools
    Then the status shows "[MCP: test-srv ✓ — 0 tools]"
    And no tools are registered from this server
    And no error occurs

  Scenario: Duplicate tool names across servers
    Given server-A declares tool "search"
    And server-B also declares tool "search"
    When both servers start
    Then a warning is displayed: "Tool name collision: 'search' from servers A and B"
    And both are namespaced as "server-A_search" and "server-B_search"
    And no tools are silently overwritten

  # --- Tool Execution ---

  Scenario: Execute a tool from an MCP server
    Given test-srv tool "test-srv_echo" is registered
    When the agent calls "test-srv_echo" with {"message": "hello"}
    Then the MCP server processes the request
    And returns {"result": "hello"}
    And the result is displayed in the chat area

  Scenario: MCP server returns an error for a tool call
    Given test-srv tool "test-srv_failing" always returns an error
    When the agent calls "test-srv_failing"
    Then the error is captured
    And the agent receives "MCP Error (test-srv): {error message}"
    And pyharness does NOT crash

  # --- Crash and Recovery ---

  Scenario: MCP server crashes mid-tool-call
    Given test-srv is executing a tool call
    When the test-srv process is killed
    Then the tool call returns "MCP Error: server process exited unexpectedly"
    And the status shows "[MCP: test-srv ✗ — crashed]"
    And the agent can continue and use other tools

  Scenario: MCP server auto-restart on crash
    Given test-srv has crashed
    And auto-restart is configured
    When the agent calls a test-srv tool again
    Then test-srv is restarted
    And the status shows "[MCP: test-srv ✓ — restarted]"
    And the tool call succeeds

  Scenario: MCP server with long startup time
    Given test-srv takes 45 seconds to initialize
    When a new session is started
    Then the status bar shows "[MCP: test-srv — starting...]"
    And the TUI remains responsive
    After 45 seconds, the status changes to "[MCP: test-srv ✓]"

  # --- Remote MCP Authentication ---

  Scenario: Remote MCP OAuth token expires mid-session
    Given a remote MCP server with OAuth authentication
    And the access token has expired
    When the agent calls a remote server tool
    And the server returns HTTP 401
    Then the MCP client attempts token refresh
    And if refresh succeeds, the tool call is retried with the new token
    And if refresh fails, the status shows "[MCP: remote 🔒 — re-authenticate]"

  Scenario: Remote MCP server returns malformed response
    Given a remote MCP server
    When the agent calls a remote tool
    And the server returns invalid JSON
    Then the error "MCP Protocol Error: invalid JSON response" is returned to the agent
    And the full response is logged for debugging
    And pyharness does not crash

  # --- Streaming ---

  Scenario: MCP server stream is interrupted
    Given test-srv tool "test-srv_stream" streams results
    When the stream is interrupted mid-response
    Then the partial results received so far are returned
    And the error "[Stream interrupted after N items]" is appended
    And the agent is informed

  # --- Output Size ---

  Scenario: MCP tool returns very large result
    Given test-srv tool returns a 50MB JSON response
    When the agent calls the tool
    Then the response is truncated for display
    And the full response is available to the LLM context
    And truncation is noted: "[Full response: 50MB — complete data in context]"
