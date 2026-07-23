"""Tests for the CylonIndicator activity widget — TDD red phase.

All tests are expected to FAIL until the implementation exists in
``src/pyharness/tui/widgets/activity.py``.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# TEST 1: Module and imports exist
# ---------------------------------------------------------------------------


def test_cylon_indicator_exists() -> None:
    """``CylonIndicator`` can be imported from the activity module."""
    from pyharness.tui.widgets.activity import CylonIndicator  # noqa: F401


def test_cylon_indicator_is_static() -> None:
    """``CylonIndicator`` is a subclass of ``textual.widgets.Static``."""
    from pyharness.tui.widgets.activity import CylonIndicator

    from textual.widgets import Static

    assert issubclass(CylonIndicator, Static), (
        f"CylonIndicator must inherit from Static, "
        f"got {CylonIndicator.__bases__}"
    )


# ---------------------------------------------------------------------------
# TEST 2: Default LED count
# ---------------------------------------------------------------------------


def test_cylon_indicator_has_default_leds() -> None:
    """A newly-created ``CylonIndicator`` has 8 LED positions by default."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    # The default should be 8 LEDs (the spec says "8 LED positions")
    assert hasattr(widget, "_led_count") or hasattr(widget, "led_count"), (
        "CylonIndicator must expose an LED count attribute"
    )
    count = getattr(widget, "led_count", getattr(widget, "_led_count", None))
    assert count == 8, f"Expected 8 default LEDs, got {count}"


# ---------------------------------------------------------------------------
# TEST 3: LED count is configurable
# ---------------------------------------------------------------------------


def test_cylon_indicator_led_count_configurable() -> None:
    """``CylonIndicator(led_count=5)`` creates 5 LEDs."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator(led_count=5)
    count = getattr(widget, "led_count", getattr(widget, "_led_count", None))
    assert count == 5, f"Expected 5 LEDs, got {count}"


# ---------------------------------------------------------------------------
# TEST 4: Running state
# ---------------------------------------------------------------------------


def test_cylon_indicator_running_state_default() -> None:
    """A new indicator starts as NOT running."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    assert hasattr(widget, "running"), "CylonIndicator must have a 'running' property"
    assert widget.running is False, "Default state should be False (idle)"


def test_cylon_indicator_set_running_updates() -> None:
    """Calling ``set_running(True)`` changes the running state."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    assert hasattr(widget, "set_running"), (
        "CylonIndicator must have a 'set_running(running: bool)' method"
    )
    widget.set_running(True)
    assert widget.running is True


def test_cylon_indicator_set_running_false_stops() -> None:
    """Calling ``set_running(False)`` stops animation."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    widget.set_running(True)
    assert widget.running is True
    widget.set_running(False)
    assert widget.running is False


# ---------------------------------------------------------------------------
# TEST 5: Position tracking
# ---------------------------------------------------------------------------


def test_cylon_indicator_initial_position() -> None:
    """Position starts at 0 (far-left LED)."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    pos = getattr(widget, "_position", getattr(widget, "position", None))
    assert pos == 0, f"Expected position 0, got {pos}"


def test_cylon_indicator_position_advances() -> None:
    """After one ``_advance_position()``, position moves to 1."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    assert hasattr(widget, "_advance_position"), (
        "CylonIndicator must have a '_advance_position()' method"
    )
    widget._advance_position()
    pos = getattr(widget, "_position", getattr(widget, "position", None))
    assert pos == 1, f"Expected position 1 after advance, got {pos}"


def test_cylon_indicator_position_wraps() -> None:
    """Advancing past the last position reverses direction."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    # Move to position 6 (one before the last of 8 LEDs, index 7)
    for _ in range(6):
        widget._advance_position()
    pos = getattr(widget, "_position", getattr(widget, "position", None))
    assert pos == 6, f"Expected position 6, got {pos}"

    # Advance to position 7 (last LED, index 7)
    widget._advance_position()
    assert (
        getattr(widget, "_position", getattr(widget, "position", None)) == 7
    ), "Expected position 7"

    # Advance again — direction should reverse, moving back to 6
    widget._advance_position()
    assert (
        getattr(widget, "_position", getattr(widget, "position", None)) == 6
    ), "Expected position 6 after wrap (direction reversal)"

    # Now keep going back to 0
    for _ in range(6):
        widget._advance_position()
    pos = getattr(widget, "_position", getattr(widget, "position", None))
    assert pos == 0, f"Expected position 0 after full back-scan, got {pos}"

    # Advancing past 0 should reverse again
    widget._advance_position()
    assert (
        getattr(widget, "_position", getattr(widget, "position", None)) == 1
    ), "Expected position 1 after left-edge wrap"


# ---------------------------------------------------------------------------
# TEST 6: Rendered output
# ---------------------------------------------------------------------------


def test_cylon_indicator_idle_renders_dim() -> None:
    """When not running, rendered text does NOT contain bright color markup."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    widget.running = False
    rendered = widget.render()
    # The idle state should not include bright accent colors
    assert "#7ee787" not in str(rendered), (
        f"Idle indicator should not contain bright accent color. Got: {rendered!r}"
    )


def test_cylon_indicator_running_renders_lit() -> None:
    """When running, the rendered text contains at least one lit LED (bright color)."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    widget.running = True
    # Force a render after setting position
    rendered = widget.render()
    text = str(rendered)
    # Should contain a lit LED character (Unicode filled circle)
    assert "◉" in text or "⬤" in text or "■" in text, (
        f"Running indicator must contain a lit LED character. Got: {text!r}"
    )
    # Should use Rich markup for color
    assert "[" in text and "]" in text, (
        f"Running indicator must use Rich markup. Got: {text!r}"
    )


def test_cylon_indicator_rendered_markup() -> None:
    """The rendered output uses Rich markup for colors (contains brackets)."""
    from pyharness.tui.widgets.activity import CylonIndicator

    widget = CylonIndicator()
    widget.running = True
    rendered = widget.render()
    text = str(rendered)
    assert "[" in text and "]" in text, (
        f"Output must use Rich markup brackets. Got: {text!r}"
    )
    assert "/" in text, (
        f"Rich markup must have closing tags [/]. Got: {text!r}"
    )


# ---------------------------------------------------------------------------
# TEST 7: ChatScreen integration
# ---------------------------------------------------------------------------


def test_chat_screen_composes_cylon_indicator() -> None:
    """ChatScreen compose includes ``CylonIndicator`` before ``StatusBar``."""
    from pyharness.tui.widgets.activity import CylonIndicator

    from pyharness.tui.screens.chat import ChatScreen

    screen = ChatScreen()
    # Get the compose output
    children = list(screen.compose())
    found_cylon = False
    found_status = False
    for child in children:
        if isinstance(child, CylonIndicator):
            found_cylon = True
        if found_cylon and not isinstance(child, CylonIndicator):
            # CylonIndicator must come before StatusBar
            from pyharness.tui.widgets.status import StatusBar

            if isinstance(child, StatusBar):
                found_status = True
    assert found_cylon, (
        "ChatScreen compose() must yield a CylonIndicator"
    )
    assert found_status, (
        "CylonIndicator must be followed by StatusBar in compose order"
    )


def test_chat_screen_has_set_activity_running() -> None:
    """ChatScreen has a ``set_activity_running(running: bool)`` method."""
    from pyharness.tui.screens.chat import ChatScreen

    screen = ChatScreen()
    assert hasattr(screen, "set_activity_running"), (
        "ChatScreen must have a 'set_activity_running(running: bool)' method"
    )
    assert callable(screen.set_activity_running), (
        "'set_activity_running' must be callable"
    )


def test_chat_screen_activity_updates_indicator() -> None:
    """``set_activity_running(True)`` updates the ``CylonIndicator`` widget."""
    from pyharness.tui.screens.chat import ChatScreen

    from pyharness.tui.widgets.activity import CylonIndicator

    screen = ChatScreen()
    assert hasattr(screen, "set_activity_running"), (
        "ChatScreen must expose set_activity_running"
    )
    # The method should accept a boolean
    screen.set_activity_running(True)
    screen.set_activity_running(False)
