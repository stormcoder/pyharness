"""Tree view of the project directory structure.

Phase 2: Functional file tree showing project files with expand/collapse.

Provides:
- :class:`FileTreeWidget` — Tree widget showing labelled directory structure
- :class:`FileTree` — Alias for backward-compatible imports from tests
"""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Tree


class FileTreeWidget(Tree[Path]):
    """Tree view of project files.

    Shows the project directory structure starting from the current working
    directory.  Each node stores its :class:`Path` as node data.

    Args:
        label: Root node label (default ``"Project"``).
    """

    def __init__(self, label: str = "Project") -> None:
        super().__init__(label)

    def on_mount(self) -> None:
        """Populate the tree with the project directory."""
        self.show_root = True
        self.guide_depth = 2
        root_path = Path.cwd()
        root_node = self.root.add(
            str(root_path.name),
            data=root_path,
            expand=True,
        )
        self._add_directory(root_path, root_node)

    def _add_directory(self, directory: Path, parent_node: object) -> None:
        """Recursively add files and subdirectories, skipping hidden paths.

        Args:
            directory: Directory to traverse.
            parent_node: Parent tree node to attach children to.
        """
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            # Skip hidden files and common ignore patterns
            if entry.name.startswith("."):
                continue
            if entry.name in ("__pycache__", "node_modules", ".venv", "dist"):
                continue

            if entry.is_dir():
                node = parent_node.add(
                    f"\U0001f4c1 {entry.name}",
                    data=entry,
                    expand=False,
                )
            else:
                parent_node.add_leaf(
                    f"\U0001f4c4 {entry.name}",
                    data=entry,
                )


# Backward-compatible alias — tests expect ``FileTree``
FileTree = FileTreeWidget
