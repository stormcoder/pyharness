"""Side panel with tabbed panes for Sessions, File Tree, and Tools.

Phase 2: Functional tabbed sidebar with toggle support (Ctrl+o).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import TabbedContent, TabPane, Static

from pyharness.tui.widgets.file_tree import FileTreeWidget
from pyharness.tui.widgets.memory import MemoryTab


class SessionList(Static):
    """Placeholder listing of recent sessions."""

    def on_mount(self) -> None:
        self.update("[#8b949e]Sessions will be listed here (Phase 2).[/]")


class ToolList(Static):
    """Placeholder listing of available tools."""

    def on_mount(self) -> None:
        self.update("[#8b949e]Available tools will be listed here (Phase 2).[/]")


class Sidebar(Static):
    """Side panel with Sessions, File Tree, and Tools tabs.

    Toggle with ``Ctrl+o`` from :class:`~pyharness.tui.app.PyHarnessApp`.
    """

    def compose(self) -> ComposeResult:
        with Container(id="sidebar-container"):
            with TabbedContent():
                with TabPane("Sessions", id="tab-sessions"):
                    yield SessionList(id="session-list")
                with TabPane("File Tree", id="tab-files"):
                    yield FileTreeWidget()
                with TabPane("Tools", id="tab-tools"):
                    yield ToolList(id="tool-list")
