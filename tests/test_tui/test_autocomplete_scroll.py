"""Tests for AtAutocomplete scroll-to-highlighted fix.

When the arrow keys navigate a long dropdown list, the highlight must
stay visible.  The ``_scroll_to_highlighted()`` helper scrolls the
``VerticalScroll`` container so the highlighted item never scrolls out
of view.

IMPORTANT — ``AtAutocomplete`` starts with ``display: none`` (hidden).
Tests that verify scroll behavior MUST call ``show_dropdown()`` before
highlighting, otherwise the widget has zero size and scrolling is
meaningless.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll

from pyharness.tui.widgets.at_autocomplete import AtAutocomplete


# ---------------------------------------------------------------------------
# Minimal test app that mounts AtAutocomplete so the DOM is live
# ---------------------------------------------------------------------------


class _AutocompleteTestApp(App[None]):
    """Minimal Textual app containing a single AtAutocomplete widget."""

    def compose(self) -> ComposeResult:
        yield AtAutocomplete(
            agent_names=["build", "plan", "general", "explore"],
            id="test-ac",
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHighlightScrollsIntoView:
    """Highlight near the end of a long list must scroll the container."""

    async def test_highlight_near_end_scrolls(self) -> None:
        """Calling highlight(25) on a 30-item list must change scroll offset."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 20)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"item-{i}" for i in range(30)])
            await pilot.pause()

            widget.highlight(25)
            await pilot.pause()

            scroll = widget.query_one("#at-scroll", VerticalScroll)
            assert scroll.scroll_offset.y > 0, (
                f"Expected scroll y > 0 for item 25, got {scroll.scroll_offset.y}"
            )

    async def test_highlight_near_end_keeps_scroll_positive(self) -> None:
        """After highlighting item 20 in a 25-item list the scroll offset is
        non-zero (the item is beyond the visible area of max-height=12)."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 18)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"cmd-{i}" for i in range(25)])
            await pilot.pause()

            widget.highlight(20)
            await pilot.pause()

            scroll = widget.query_one("#at-scroll", VerticalScroll)
            assert scroll.scroll_offset.y > 0, (
                f"Scroll should be > 0 for item 20, got {scroll.scroll_offset.y}"
            )


class TestHighlightNearTop:
    """Highlight at index 0 should keep the scroll container near the top."""

    async def test_highlight_zero_scroll_near_top(self) -> None:
        """highlight(0) on a populated list keeps scroll offset close to 0."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 20)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"item-{i}" for i in range(30)])
            await pilot.pause()

            widget.highlight(0)
            await pilot.pause()

            scroll = widget.query_one("#at-scroll", VerticalScroll)
            assert scroll.scroll_offset.y <= 5, (
                f"Scroll should be near 0 for item 0, got {scroll.scroll_offset.y}"
            )

    async def test_highlight_zero_highlighted_index_is_zero(self) -> None:
        """The highlighted_index property reports 0 after highlight(0)."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 20)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"item-{i}" for i in range(30)])
            await pilot.pause()

            widget.highlight(0)
            await pilot.pause()

            assert widget.highlighted_index == 0


class TestScrollToHighlightedMethod:
    """Source-level checks: method exists and is wired into highlight()."""

    def test_method_exists(self) -> None:
        """AtAutocomplete must have a _scroll_to_highlighted method."""
        assert hasattr(AtAutocomplete, "_scroll_to_highlighted"), (
            "_scroll_to_highlighted method is missing"
        )

    def test_method_is_callable(self) -> None:
        """_scroll_to_highlighted must be callable."""
        method = getattr(AtAutocomplete, "_scroll_to_highlighted", None)
        assert callable(method), "_scroll_to_highlighted is not callable"

    def test_highlight_calls_scroll_to_highlighted(self) -> None:
        """The highlight() method must call self._scroll_to_highlighted()."""
        source = inspect.getsource(AtAutocomplete.highlight)
        assert "self._scroll_to_highlighted()" in source, (
            "highlight() must call self._scroll_to_highlighted() — "
            "the scroll call is missing from the method source"
        )

    def test_scroll_to_highlighted_uses_scroll_to_widget(self) -> None:
        """_scroll_to_highlighted must use scroll.scroll_to_widget()."""
        source = inspect.getsource(AtAutocomplete._scroll_to_highlighted)
        assert "scroll_to_widget" in source, (
            "_scroll_to_highlighted must call scroll_to_widget to scroll "
            "the container to the highlighted item"
        )

    def test_scroll_to_highlighted_queries_at_scroll(self) -> None:
        """_scroll_to_highlighted must query the #at-scroll container."""
        source = inspect.getsource(AtAutocomplete._scroll_to_highlighted)
        assert "#at-scroll" in source, (
            "_scroll_to_highlighted must query #at-scroll VerticalScroll"
        )


class TestMultipleSequentialHighlights:
    """Navigating multiple items with highlight() keeps scroll correct."""

    async def test_scroll_maintained_after_multiple_moves(self) -> None:
        """Highlight 40 then 45 in a 50-item list — scroll must be non-zero
        and the highlighted index must be 45."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 20)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"item-{i}" for i in range(50)])
            await pilot.pause()

            widget.highlight(40)
            await pilot.pause()

            widget.highlight(45)
            await pilot.pause()

            assert widget.highlighted_index == 45, (
                f"Expected highlighted_index=45 after highlight(45), "
                f"got {widget.highlighted_index}"
            )

            scroll = widget.query_one("#at-scroll", VerticalScroll)
            assert scroll.scroll_offset.y > 0, (
                f"Scroll must be > 0 for item 45, got {scroll.scroll_offset.y}"
            )

    async def test_scroll_stays_positive_after_40_to_45(self) -> None:
        """Moving from 40→45 should keep scroll non-zero (both deep items)."""
        app = _AutocompleteTestApp()
        async with app.run_test(size=(40, 18)) as pilot:
            widget = app.query_one("#test-ac", AtAutocomplete)
            widget.show_dropdown()
            widget.update_items([f"entry-{i}" for i in range(60)])
            await pilot.pause()

            widget.highlight(40)
            await pilot.pause()
            y_after_40 = widget.query_one(
                "#at-scroll", VerticalScroll
            ).scroll_offset.y

            widget.highlight(45)
            await pilot.pause()
            y_after_45 = widget.query_one(
                "#at-scroll", VerticalScroll
            ).scroll_offset.y

            # Both deep items should produce a positive scroll offset
            assert y_after_40 > 0, f"Item 40 scroll = {y_after_40}, expected > 0"
            assert y_after_45 > 0, f"Item 45 scroll = {y_after_45}, expected > 0"
