"""Status bar — bottom-docked bar showing model, tokens, and session info.

Phase 1: Simple static display.  Phase 2 adds model selector, token count,
and memory indicator.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


class StatusBar(Static):
    """Bottom-docked status bar showing model, agent mode, and context usage.

    Usage::

        status = StatusBar("anthropic:claude-sonnet-4-5 | build | 0 tokens", id="status-bar")
    """

    def __init__(self, status_text: str = "", **kwargs: Any) -> None:
        super().__init__(status_text, **kwargs)

    def update_status(self, text: str) -> None:
        """Update the displayed status text."""
        self.update(text)
