"""AtAutocomplete — dropdown list widget for @ autocomplete above the input.

Replaces the old RichLog-based approach with a proper interactive dropdown
that appears just above the PromptInput, filters in real-time, and is
navigable with arrow keys.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class AtAutocomplete(Widget):
    """Dropdown list for @ autocomplete that appears above the input field.

    Displays a scrollable list of agent names (🤖) and file paths (📄).
    The dropdown is non-focusable — all keyboard interaction is handled
    by PromptInput._on_key() to keep typing flowing to the input field.
    """

    DEFAULT_CSS = """
    AtAutocomplete {
        display: none;
        height: auto;
        max-height: 12;
        background: $surface;
        border: tall $primary;
        margin: 0 0 1 0;
    }

    AtAutocomplete.-visible {
        display: block;
    }

    AtAutocomplete .at-item {
        padding: 0 1;
        color: $text;
        width: 100%;
    }

    AtAutocomplete .at-item.-highlighted {
        background: $accent;
        color: $text;
    }

    AtAutocomplete .at-header {
        padding: 0 1;
        color: $text-disabled;
        text-style: bold;
        background: $surface-darken-1;
    }
    """

    def __init__(
        self,
        agent_names: list[str] | None = None,
        *,
        title: str = "References",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._agent_names = agent_names or []
        self._title = title
        self._items: list[str] = []
        self._highlighted: int = 0
        self._on_select: callable | None = None

    def set_select_callback(self, callback: callable) -> None:
        """Set the callback invoked when an item is selected via Enter."""
        self._on_select = callback

    # -- public API ----------------------------------------------------------

    @property
    def selected_item(self) -> str | None:
        """The currently highlighted item, or None if the list is empty."""
        if self._items and 0 <= self._highlighted < len(self._items):
            return self._items[self._highlighted]
        return None

    @property
    def highlighted_index(self) -> int:
        """Zero-based index of the highlighted item."""
        return self._highlighted

    @property
    def item_count(self) -> int:
        """Number of items currently shown."""
        return len(self._items)

    # -- compose -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="at-scroll"):
            if self._items:
                yield Static(
                    f"{self._title} ({len(self._items)} matches)",
                    classes="at-header",
                )
                for i, item in enumerate(self._items):
                    icon = "🤖" if item in self._agent_names else "📄"
                    cls = "at-item"
                    if i == self._highlighted:
                        cls += " -highlighted"
                    yield Static(f"  {icon} {item}", classes=cls)

    # -- mutation ------------------------------------------------------------

    def update_items(self, items: list[str]) -> None:
        """Replace all items and rebuild the content area."""
        self._items = list(items)
        self._highlighted = min(self._highlighted, max(0, len(self._items) - 1))
        self._rebuild_children()

    def highlight(self, index: int) -> None:
        """Move the visual highlight to *index* (clamped to valid range)."""
        if not self._items:
            self._highlighted = 0
            return
        self._highlighted = max(0, min(index, len(self._items) - 1))
        self._refresh_highlights()
        self._scroll_to_highlighted()

    def show_dropdown(self) -> None:
        """Make the dropdown visible."""
        self.add_class("-visible")

    def hide_dropdown(self) -> None:
        """Hide the dropdown."""
        self.remove_class("-visible")

    def _scroll_to_highlighted(self) -> None:
        """Scroll the list so the highlighted item stays visible."""
        try:
            scroll = self.query_one("#at-scroll", VerticalScroll)
        except Exception:
            return
        # Items: header at index 0, then _highlighted + 1 for actual item
        item_index = self._highlighted + 1
        children = list(scroll.query("Static.at-item"))
        if 0 <= item_index - 1 < len(children):
            target = children[self._highlighted]
            scroll.scroll_to_widget(target, animate=False)

    # -- internal helpers ----------------------------------------------------

    def _rebuild_children(self) -> None:
        """Remove old child widgets and remount fresh ones."""
        try:
            scroll = self.query_one("#at-scroll", VerticalScroll)
        except Exception:
            return
        scroll.remove_children()
        scroll.mount(
            Static(
                f"{self._title} ({len(self._items)} matches)",
                classes="at-header",
            )
        )
        for i, item in enumerate(self._items):
            icon = "🤖" if item in self._agent_names else "📄"
            cls = "at-item"
            if i == self._highlighted:
                cls += " -highlighted"
            scroll.mount(Static(f"  {icon} {item}", classes=cls))

    def _refresh_highlights(self) -> None:
        """Update CSS classes to reflect the current highlight index."""
        try:
            scroll = self.query_one("#at-scroll", VerticalScroll)
        except Exception:
            return
        items = list(scroll.query("Static.at-item"))
        for i, widget in enumerate(items):
            if i == self._highlighted:
                widget.add_class("-highlighted")
            else:
                widget.remove_class("-highlighted")
