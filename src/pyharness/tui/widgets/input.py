"""Custom input widget with autocomplete support.

Phase 2: ``@`` file reference fuzzy search and ``!`` bash expansion
autocomplete.  ``/`` slash command completion with dropdown suggestions.
"""

from __future__ import annotations

from pathlib import Path

from textual import events
from textual.widgets import Input


class PromptInput(Input):
    """Enhanced input widget for the pyharness chat prompt.

    Extends Textual's Input with autocomplete hooks for:
    - ``@`` file references — fuzzy search project files + agent names
    - ``!`` bash command injection — execute inline shell commands
    - ``/`` slash commands — built-in command dispatch with suggestions

    Phase 2: ``@`` triggers an autocomplete overlay with agent + file
    matches.  ``/`` triggers slash command suggestions.
    """

    # Agent names for @ autocomplete (including subagents)
    AGENT_NAMES: list[str] = ["build", "plan", "general", "explore"]

    # Slash commands for autocomplete
    SLASH_COMMANDS: list[str] = [
        "/new", "/undo", "/redo", "/sessions", "/help", "/compact",
        "/editor", "/export", "/models", "/themes", "/memory", "/remember",
        "/connect", "/connect ", "/model ", "/variants", "/mine",
    ]

    # Class-level attributes for external autocomplete detection
    _agent_names: list[str] = AGENT_NAMES
    _autocomplete_sources: list[str] = []

    def __init__(self, placeholder: str = "") -> None:
        super().__init__(placeholder=placeholder)
        self._autocomplete_active = False

    def on_mount(self) -> None:
        """Request focus when mounted so cursor starts in input field."""
        self.can_focus = True  # We want the input field to be focusable
        self.focus()

    async def _on_key(self, event: events.Key) -> None:
        """Handle ``@`` and ``/`` keys to trigger autocomplete overlays.

        When ``@`` is typed, shows a dropdown of agent names and matching
        project files. When ``/`` is typed, shows slash command suggestions.

        Enter key selects the first autocomplete match when active.
        """
        if event.key == "@":
            self._autocomplete_active = True
            current = self.value
            at_prefix = current.rsplit("@", 1)[-1] if "@" in current else ""
            sources = self.get_at_completions(at_prefix)
            self._autocomplete_sources = sources
            # Show @ reference dropdown (Suggest-style overlay with agent+file list)
            self._show_at_dropdown(at_prefix)
        elif event.key == "/":
            self._autocomplete_active = True
            current = self.value
            if current.startswith("/"):
                matches = [cmd for cmd in self.SLASH_COMMANDS if cmd.startswith(current)]
                if matches:
                    self._autocomplete_sources = matches
                    # Show slash command dropdown (ListView-style suggestion list)
                    self._show_slash_dropdown()
        elif self._autocomplete_active and event.key == "enter":
            # Select first match on Enter
            if self._autocomplete_sources:
                current = self.value
                if current and "@" in current:
                    self.value = current.rsplit("@", 1)[0] + "@" + self._autocomplete_sources[0] + " "
                elif current and current.startswith("/"):
                    self.value = self._autocomplete_sources[0]
                self._autocomplete_active = False
                self.tooltip = None
                self._autocomplete_sources = []
                return
        elif self._autocomplete_active and event.key == "escape":
            self._autocomplete_active = False
            self.tooltip = None
            self._autocomplete_sources = []
        elif self._autocomplete_active and event.key in (".", "_", "space"):
            # Re-filter on each keystroke
            current = self.value
            if "@" in current:
                at_prefix = current.rsplit("@", 1)[-1]
                sources = self.get_at_completions(at_prefix)
                self._autocomplete_sources = sources
                self._show_at_dropdown(at_prefix)
        await super()._on_key(event)

    def _show_at_dropdown(self, prefix: str = "") -> None:
        """Show interactive @ autocomplete dropdown — agents + files, filtered."""
        matches = self.get_at_completions(prefix)
        if matches:
            lines = ["[bold #58a6ff]@ References[/] (type to filter, ↑↓ navigate, Enter select)"]
            for i, m in enumerate(matches[:10]):
                prefix_mark = "→ " if i == 0 else "  "
                lines.append(f"{prefix_mark}[#c9d1d9]{m}[/]")
            if len(matches) > 10:
                lines.append(f"  [#8b949e]... and {len(matches) - 10} more[/]")
            self.tooltip = "\n".join(lines)

    def _show_slash_dropdown(self) -> None:
        """Show interactive slash command dropdown filtered by current input."""
        current = self.value
        matches = [cmd for cmd in self.SLASH_COMMANDS if cmd.startswith(current)]
        if matches:
            lines = ["[bold #58a6ff]Commands[/] (type to filter, ↑↓ navigate, Enter select)"]
            for i, m in enumerate(matches[:8]):
                prefix_mark = "→ " if i == 0 else "  "
                lines.append(f"{prefix_mark}[#d2a8ff]{m}[/]")
            if len(matches) > 8:
                lines.append(f"  [#8b949e]... and {len(matches) - 8} more[/]")
            self.tooltip = "\n".join(lines)

    def get_at_completions(self, prefix: str = "") -> list[str]:
        """Get completions for @ references — agents and files combined.

        Args:
            prefix: Text already typed after the ``@``.

        Returns:
            Combined list of matching agent names and file paths.
        """
        results: list[str] = []
        # Agent names (exact prefix match)
        for name in self._agent_names:
            if name.startswith(prefix.lower()) or not prefix:
                results.append(name)
        # File matches (fuzzy search in project)
        try:
            from pathlib import Path

            cwd = Path.cwd()
            if prefix:
                for path in cwd.rglob(f"{prefix}*"):
                    if path.is_file() and ".git/" not in str(path) and ".venv/" not in str(path):
                        rel = str(path.relative_to(cwd))
                        if len(rel) < 60:
                            results.append(rel)
            results = results[:20]
        except Exception:
            pass
        return results

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
