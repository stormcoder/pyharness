"""Custom input widget with autocomplete support.

Phase 2: ``@`` file reference fuzzy search and ``!`` bash expansion
autocomplete.  ``/`` slash command completion with dropdown suggestions.

Uses ``watch_value`` (Textual reactive) for @ and / autocomplete, which
fires reliably after every value change — no ``_on_key`` timing issues.
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
    """

    # Agent names for @ autocomplete (including subagents)
    AGENT_NAMES: list[str] = ["build", "plan", "general", "explore"]

    # Slash commands for autocomplete
    SLASH_COMMANDS: list[str] = [
        "/new", "/undo", "/redo", "/sessions", "/help", "/compact",
        "/editor", "/export", "/models", "/themes", "/memory", "/remember",
        "/connect", "/connect ", "/model ", "/variants", "/mine",
    ]

    _autocomplete_sources: list[str] = []

    def __init__(self, placeholder: str = "") -> None:
        self._autocomplete_active = False  # type: ignore[assignment]
        super().__init__(placeholder=placeholder)

    def on_mount(self) -> None:
        """Request focus when mounted so cursor starts in input field."""
        self.can_focus = True
        self.focus()

    # -- Key handler: only for non-character keys (Tab, Enter, Escape) --------

    async def _on_key(self, event: events.Key) -> None:
        """Handle Tab, Enter, and Escape.  @ and / are handled by watch_value."""
        # CRITICAL: Intercept Tab BEFORE Textual Input consumes it for focus nav
        if event.key == "tab":
            if hasattr(self.app, "action_switch_agent"):
                self.app.action_switch_agent()
            return

        if event.key == "enter" and self._autocomplete_active:
            if self._autocomplete_sources:
                current = self.value
                if current and "@" in current:
                    self.value = current.rsplit("@", 1)[0] + "@" + self._autocomplete_sources[0] + " "
                elif current and current.startswith("/"):
                    self.value = self._autocomplete_sources[0]
                self._autocomplete_active = False
                self._autocomplete_sources = []
                return

        if event.key == "escape" and self._autocomplete_active:
            self._autocomplete_active = False
            self._autocomplete_sources = []

        await super()._on_key(event)

    # -- Reactive watcher: fires AFTER value changes ---------------------------

    def watch_value(self, value: str) -> None:
        """Show @ or / autocomplete whenever the value changes.

        Textual calls this reactive watcher reliably after every value
        change — no timing issues with ``_on_key``."""
        if not value:
            self._autocomplete_active = False
            self._autocomplete_sources = []
            return

        # --- @ references: agents + files ---
        if "@" in value and not value.startswith("/"):
            self._autocomplete_active = True
            at_idx = value.rfind("@")
            prefix = value[at_idx + 1:]
            sources = self.get_at_completions(prefix)
            self._autocomplete_sources = sources
            self._show_at_dropdown(prefix)
            return

        # --- / slash commands ---
        if value.startswith("/"):
            self._autocomplete_active = True
            matches = [cmd for cmd in self.SLASH_COMMANDS if cmd.startswith(value)]
            self._autocomplete_sources = matches
            if matches:
                self._show_slash_dropdown(value)
            return

        # --- Normal text: deactivate ---
        self._autocomplete_active = False
        self._autocomplete_sources = []

    # -- Display helpers -------------------------------------------------------

    def _show_at_dropdown(self, prefix: str = "") -> None:
        """Write @ autocomplete results to the chat RichLog."""
        matches = self.get_at_completions(prefix)
        if not matches:
            return
        try:
            from textual.widgets import RichLog
            chat = self.app.query_one("#chat-area", RichLog)
            chat.write(f"\n[dim #8b949e]@ References ({len(matches)} matches)[/]")
            for m in matches[:10]:
                agent_tag = " [🤖]" if m in self.AGENT_NAMES else " [📄]"
                chat.write(f"  [#7ee787]{m}{agent_tag}[/]")
            if len(matches) > 10:
                chat.write(f"  [dim]... {len(matches) - 10} more, type to filter[/]")
        except Exception:
            pass

    def _show_slash_dropdown(self, current: str = "") -> None:
        """Write slash command suggestions to the chat RichLog."""
        matches = [cmd for cmd in self.SLASH_COMMANDS if cmd.startswith(current)]
        if not matches:
            return
        try:
            from textual.widgets import RichLog
            chat = self.app.query_one("#chat-area", RichLog)
            chat.write("\n[dim #8b949e]Commands (type to filter, Enter to select)[/]")
            for m in matches[:8]:
                chat.write(f"  [#d2a8ff]{m}[/]")
            if len(matches) > 8:
                chat.write(f"  [dim]... {len(matches) - 8} more[/]")
        except Exception:
            pass

    # -- Completions -----------------------------------------------------------

    def get_at_completions(self, prefix: str = "") -> list[str]:
        """Get completions for @ references — agents and files combined."""
        results: list[str] = []
        # Agent names first
        for name in self.AGENT_NAMES:
            if not prefix or name.startswith(prefix.lower()):
                results.append(name)
        # Files via rglob
        try:
            cwd = Path.cwd()
            for path in cwd.rglob(f"{prefix}*"):
                if (
                    path.is_file()
                    and ".git/" not in str(path)
                    and ".venv/" not in str(path)
                    and "__pycache__" not in str(path)
                ):
                    rel = str(path.relative_to(cwd))
                    if len(rel) < 60:
                        results.append(rel)
                    if len(results) >= 20:
                        break
        except Exception:
            pass
        return results[:20]

    def get_at_file_refs(self) -> list[str]:
        """Extract ``@path`` references from the current input value."""
        import re
        value: str = getattr(self, "value", "")
        return re.findall(r"@([\w./-]+)", value)

    def resolve_at_files(self, project_root: Path | None = None) -> list[Path]:
        """Resolve ``@path`` references to actual files in the project."""
        root = project_root or Path.cwd()
        refs = self.get_at_file_refs()
        resolved: list[Path] = []
        for ref in refs:
            candidate = root / ref
            if candidate.exists():
                resolved.append(candidate)
        return resolved

    def fuzzy_search_files(self, partial: str, project_root: Path | None = None) -> list[str]:
        """Fuzzy search project files matching a partial path."""
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
