"""Custom input widget with autocomplete support.

Phase 2: ``@`` file reference fuzzy search and ``!`` bash expansion
autocomplete.  ``/`` slash command completion lands in a future phase.
"""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Input


class PromptInput(Input):
    """Enhanced input widget for the pyharness chat prompt.

    Extends Textual's Input with autocomplete hooks for:
    - ``@`` file references — fuzzy search project files
    - ``!`` bash command injection — execute inline shell commands
    - ``/`` slash commands — built-in command dispatch

    Phase 2: ``@`` trigger opens a file search dropdown (functional stub).
    Full autocomplete with dropdown menu lands in Phase 3.
    """

    def __init__(self, placeholder: str = "") -> None:
        super().__init__(placeholder=placeholder)
        self._autocomplete_active = False

    def _on_key(self, event: object) -> None:
        """Handle ``@`` key to trigger file autocomplete.

        When the user types ``@``, we record the trigger for the parent
        ChatScreen to handle — actual dropdown rendering is Phase 3.
        """
        # Check if this is a Key event with "@" key
        key_value: str | None = getattr(event, "key", None)
        if key_value == "@":
            self._autocomplete_active = True

    def get_at_file_refs(self) -> list[str]:
        """Extract ``@path`` references from the current input value.

        Returns:
            List of file paths referenced after ``@`` markers.
        """
        import re

        value: str = getattr(self, "value", "")
        return re.findall(r"@([\w./-]+)", value)

    def resolve_at_files(self, project_root: Path | None = None) -> list[Path]:
        """Resolve ``@path`` references to actual files in the project.

        Args:
            project_root: Project root directory (defaults to ``Path.cwd()``).

        Returns:
            List of resolved existing file paths.
        """
        root = project_root or Path.cwd()
        refs = self.get_at_file_refs()
        resolved: list[Path] = []
        for ref in refs:
            candidate = root / ref
            if candidate.exists():
                resolved.append(candidate)
        return resolved

    def fuzzy_search_files(self, partial: str, project_root: Path | None = None) -> list[str]:
        """Fuzzy search project files matching a partial path.

        Args:
            partial: Partial file name or path to search for.
            project_root: Project root directory (defaults to ``Path.cwd()``).

        Returns:
            List of relative file paths matching the search term.
        """
        root = project_root or Path.cwd()
        results: list[str] = []

        for file_path in root.rglob(f"*{partial}*"):
            if file_path.is_file():
                if any(
                    part.startswith(".")
                    or part in ("__pycache__", "node_modules", ".venv", "dist", ".git")
                    for part in file_path.parts
                ):
                    continue
                results.append(str(file_path.relative_to(root)))

        return sorted(results)[:20]
