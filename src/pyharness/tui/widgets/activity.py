"""Cylon/KITT LED activity indicator for agent running state."""

from __future__ import annotations

from typing import Any

from textual.timer import Timer
from textual.widgets import Static


class CylonIndicator(Static):
    """A row of LED dots that pulse back and forth (Cylon/KITT effect).

    When ``running`` is True, the lit LED scans left-to-right and back.
    When idle, all LEDs are dim.

    Usage::

        indicator = CylonIndicator()
        indicator.set_running(True)   # start animation
        indicator.set_running(False)  # stop animation
    """

    LIT_CHAR = "\u25c9"  # ◉
    DIM_CHAR = "\u25cb"  # ○
    LIT_COLOR = "#7ee787"   # green accent
    DIM_COLOR = "#30363d"   # dim gray
    INTERVAL_MS = 150
    DEFAULT_LED_COUNT = 8

    def __init__(
        self,
        led_count: int = DEFAULT_LED_COUNT,
        **kwargs: Any,
    ) -> None:
        super().__init__("", **kwargs)
        self.led_count = led_count
        self._position: int = 0
        self._direction: int = 1  # 1 = right, -1 = left
        self._running: bool = False
        self._timer: Timer | None = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """Whether the Cylon animation is currently active."""
        return self._running

    @running.setter
    def running(self, value: bool) -> None:
        """Set running state via property assignment."""
        self.set_running(value)

    def set_running(self, running: bool) -> None:
        """Start or stop the Cylon animation.

        Args:
            running: ``True`` to start the scanning animation,
                     ``False`` to stop and return to idle display.
        """
        if running == self._running:
            return
        self._running = running
        if running:
            self._position = 0
            self._direction = 1
            if self._timer is not None:
                self._timer.stop()
            try:
                self._timer = self.set_interval(
                    self.INTERVAL_MS / 1000.0, self._advance_position
                )
            except RuntimeError:
                # No running event loop (e.g. unit test outside Textual app).
                # State is set correctly; timer will be created on mount.
                self._timer = None
        else:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
        self.refresh()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _advance_position(self) -> None:
        """Advance position by one in the current direction, bouncing at edges.

        Direction ``1`` means moving right (position increases).
        Direction ``-1`` means moving left (position decreases).
        At the leftmost or rightmost edge, direction reverses.
        """
        self._position += self._direction

        # Bounce at right edge
        if self._position >= self.led_count - 1:
            self._position = self.led_count - 1
            self._direction = -1
        # Bounce at left edge
        elif self._position <= 0:
            self._position = 0
            self._direction = 1

        self.refresh()

    def render(self) -> str:
        """Render the LED row as Rich markup.

        When running, one LED at the current position is rendered in the
        bright accent colour; all others are dim.  When idle every LED is dim.
        """
        leds: list[str] = []
        for i in range(self.led_count):
            if self._running and i == self._position:
                leds.append(f"[{self.LIT_COLOR}]{self.LIT_CHAR}[/]")
            else:
                leds.append(f"[{self.DIM_COLOR}]{self.DIM_CHAR}[/]")
        return " ".join(leds)
