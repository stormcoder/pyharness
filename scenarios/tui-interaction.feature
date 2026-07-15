# language: en
# Story: TUI Interaction — Keyboard navigation, streaming display, resize, visual regression
# Associated with: SPEC §12 (TUI Layout)

@tui @visual @critical
Feature: TUI Interaction and Rendering

  Background:
    Given pyharness is running with a FakeLLMProvider
    And the session has a mix of user messages, assistant responses, and tool calls
    And Textual's test driver (pilot) is available

  # --- Keyboard Navigation ---

  Scenario: Send message with Enter
    Given the input area has focus
    When the user types "Hello, world" and presses Enter
    Then the message appears in the chat area
    And the input area is cleared
    And the agent begins processing

  Scenario: Tab cycles through primary agents
    Given the build agent is active
    When the user presses Tab
    Then the agent switches to plan
    And the header shows "[Plan]"
    When the user presses Tab again
    Then the agent switches back to build
    And the header shows "[Build]"

  Scenario: Ctrl+p opens command palette
    When the user presses Ctrl+p
    Then the command palette opens
    And it shows available commands: /new, /sessions, /undo, /redo, /help, /export, /compact, /editor
    And the user can type to filter
    And pressing Enter executes the selected command
    And pressing Escape closes the palette

  Scenario: Ctrl+x keybind sequence
    When the user presses Ctrl+x followed by n
    Then a new session is created
    When the user presses Ctrl+x followed by u
    Then the last action is undone
    When the user presses Ctrl+x followed by q
    Then pyharness exits

  Scenario: Ctrl+o toggles side panel
    Given the side panel is hidden
    When the user presses Ctrl+o
    Then the side panel appears
    When the user presses Ctrl+o again
    Then the side panel hides

  Scenario: Shift+Tab cycles side panel tabs
    Given the side panel is visible
    When the user presses Shift+Tab
    Then the side panel cycles: Sessions → File Tree → Tool Output → Sessions

  Scenario: Arrow keys navigate sessions
    Given the side panel is showing sessions
    When the user presses Arrow Down
    Then the next session is selected
    When the user presses Enter on a session
    Then that session is loaded

  # --- Streaming Display ---

  Scenario: Text streams character by character
    When the fake provider streams text "Hello world" one character at a time
    Then each character appears in the chat area as it arrives
    And the text renders with correct word wrapping
    And after the stream ends, the full message is complete

  Scenario: Tool call appears with loading indicator
    When the fake provider returns a tool_call for "bash"
    Then the tool call widget appears with a spinner
    And shows "Running: npm test..."
    When the tool completes
    Then the spinner is replaced with the exit code and output

  Scenario: Multiple tool calls in sequence
    When the fake provider returns 3 sequential tool calls
    Then each tool call widget appears in order
    And each shows its loading state then result
    And the final message shows after all tool calls complete

  # --- Resize Behavior ---

  Scenario: Terminal resize during streaming
    Given streaming text is being rendered
    When the terminal is resized from 80×24 to 120×40
    Then the layout recalculates
    And text rewraps to the new width
    And scroll position is preserved
    And no visual glitches appear

  Scenario: Terminal resize with side panel open
    Given the side panel is visible
    When the terminal is resized to be very narrow (40 columns)
    Then the side panel auto-collapses or the chat area adapts
    And the layout does not break

  # --- Content Edge Cases ---

  Scenario: Very long single-line message
    When a message contains a 10,000 character line with no spaces
    Then the text wraps or uses horizontal scroll
    And the widget boundaries are not exceeded
    And no horizontal overflow into other widgets

  Scenario: Unicode and emoji in messages
    When a message contains emoji: 🎉🚀🐍 + CJK: こんにちは + RTL: مرحبا
    Then all characters render correctly
    And text width is calculated correctly (no overlap)
    And the message is properly aligned

  Scenario: ANSI escape codes in tool output
    When bash tool output contains ANSI color codes
    Then the output renders with correct colors in the tool result widget
    Or the codes are stripped if color rendering is disabled

  Scenario: Very large tool output
    When bash tool produces 100,000 lines of output
    Then the tool result widget shows scrollable view
    And only the visible portion is rendered (virtualized)
    And the status shows "[Output: 100000 lines]"

  # --- Copy/Paste ---

  Scenario: Paste large text block into input
    When the user pastes a 50-line text block
    Then the entire text appears in the input area
    And the input area scrolls to show the cursor
    And submitting sends the full content

  # --- Error States ---

  Scenario: Textual widget render error
    When a widget throws a render exception
    Then the error is caught by Textual's error boundary
    And an error message is displayed in that widget's area
    And the rest of the TUI continues to function
    And the error is logged

  Scenario: Theme has invalid CSS
    Given the selected theme CSS is malformed
    When the theme is loaded
    Then the default theme is used as fallback
    And the status bar shows "[Theme error — using default]"
    And the detailed error is logged

  # --- Accessibility ---

  Scenario: Screen reader announces new messages
    When a new message arrives
    Then an ARIA live region update is triggered (if terminal supports it)
    Or the message widget has proper semantic markup

  Scenario: All functions accessible via keyboard
    Given the TUI is running
    Then every feature is reachable via keyboard only
    And no feature requires mouse-only interaction
    And keyboard focus is clearly indicated

  # --- Visual Regression ---

  Scenario: Chat area visual snapshot
    Given a session with 5 mixed messages (user, assistant, tool calls)
    When a visual snapshot is taken
    Then it matches the baseline snapshot for this platform
    And differences are highlighted for manual review

  Scenario: Session list visual snapshot
    Given 10 sessions in the session history
    When the session list screen is displayed
    Then it matches the baseline snapshot
