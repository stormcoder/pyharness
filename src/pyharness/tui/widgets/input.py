"""Custom input widget with autocomplete support.

Phase 2: ``@`` file reference fuzzy search and ``!`` bash expansion
autocomplete.  ``/`` slash command completion with dropdown suggestions.

Uses ``watch_value`` (Textual reactive) for @ and / autocomplete, which
fires reliably after every value change — no ``_on_key`` timing issues.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import events
from textual.widgets import Input

if TYPE_CHECKING:
    from pyharness.tui.widgets.at_autocomplete import AtAutocomplete


class PromptInput(Input):
    """Chat input with @ autocomplete, slash commands, and bash-like history.

    Extends Textual's Input with autocomplete hooks for:
    - ``@`` file references — fuzzy search project files + agent names
    - ``!`` bash command injection — execute inline shell commands
    - ``/`` slash commands — built-in command dispatch with suggestions

    **History** (bash-like):
    - Up/Down arrow keys navigate submitted message history when no
      autocomplete dropdown is active.
    - Ctrl+R opens reverse-search mode.
    - Submitted messages are pushed to history by the owning screen.
    """

    # Agent names for @ autocomplete (including subagents)
    AGENT_NAMES: list[str] = ["build", "plan", "general", "explore"]

    # Slash commands for autocomplete
    SLASH_COMMANDS: list[str] = [
        "/new", "/undo", "/redo", "/sessions", "/help", "/compact",
        "/editor", "/export", "/models", "/themes", "/memory", "/remember",
        "/connect", "/model ", "/variants", "/mine",
    ]

    _autocomplete_sources: list[str] = []

    # -- History ---------------------------------------------------------------
    _history: list[str] = []
    _history_index: int = -1       # -1 = not navigating history
    _saved_input: str = ""         # original input before history nav
    _search_mode: bool = False
    _search_query: str = ""
    _search_matches: list[tuple[int, str]] = []  # (index, text)
    _search_match_idx: int = -1

    def __init__(self, placeholder: str = "") -> None:
        self._autocomplete_active = False  # type: ignore[assignment]
        self._history = []
        self._history_index = -1
        self._saved_input = ""
        self._search_mode = False
        self._search_query = ""
        self._search_matches = []
        self._search_match_idx = -1
        super().__init__(placeholder=placeholder)

    def push_history(self, text: str) -> None:
        """Record a submitted message in history. Deduplicates consecutive duplicates."""
        if not text or not text.strip():
            return
        if self._history and self._history[-1] == text:
            return  # deduplicate consecutive identical entries
        self._history.append(text)
        self._history_index = -1

    def _show_history(self, index: int) -> None:
        """Replace input value with history entry at given index."""
        if 0 <= index < len(self._history):
            self.value = self._history[index]
            self._history_index = index

    def _restore_saved_input(self) -> None:
        """Restore to the pre-history-navigation input."""
        self.value = self._saved_input
        self._history_index = -1
        self._saved_input = ""

    def _activate_search(self) -> None:
        """Enter Ctrl+R reverse-search mode."""
        self._search_mode = True
        self._search_query = ""
        self._search_matches = []
        self._search_match_idx = -1
        if self._history_index < 0:
            self._saved_input = self.value
        self.value = "(reverse-i-search)`: "
        self.cursor_position = len(self.value)

    def on_mount(self) -> None:
        """Request focus when mounted so cursor starts in input field."""
        self.can_focus = True
        self.focus()

    # -- Key handler: only for non-character keys (Tab, Enter, Escape) --------

    async def _on_key(self, event: events.Key) -> None:
        """Handle Tab, Enter, Escape, and arrow keys for autocomplete."""
        # CRITICAL: Intercept Tab BEFORE Textual Input consumes it for focus nav
        if event.key == "tab":
            if hasattr(self.app, "action_switch_agent"):
                self.app.action_switch_agent()
            event.stop()
            event.prevent_default()
            return

        # --- Arrow keys for dropdown navigation ---
        if self._autocomplete_active and event.key in ("up", "down"):
            dropdown = self._get_dropdown()
            if dropdown is not None:
                delta = -1 if event.key == "up" else 1
                dropdown.highlight(dropdown.highlighted_index + delta)
            return

        # --- Ctrl+R: reverse search mode ---
        if event.key == "ctrl+r":
            if not self._search_mode:
                self._activate_search()
            else:
                # Already in search mode — cycle to next match
                if self._search_matches:
                    self._search_match_idx = (
                        self._search_match_idx + 1
                    ) % len(self._search_matches)
                    self._show_history(
                        self._search_matches[self._search_match_idx][0]
                    )
            event.stop()
            event.prevent_default()
            return

        # --- Search mode key handling ---
        if self._search_mode:
            if event.key == "escape" or event.key == "ctrl+g":
                self._search_mode = False
                self._restore_saved_input()
                self._search_matches = []
                self._search_query = ""
                event.stop()
                event.prevent_default()
                return
            if event.key == "enter":
                self._search_mode = False
                self._search_matches = []
                self._search_query = ""
                # DO NOT stop/prevent_default — let Enter propagate so
                # ChatScreen.on_input_submitted fires and submits the
                # matched history entry.  This matches bash behavior
                # where Enter in reverse-search executes the match.
                return
            # Any other key in search mode — handled in watch_value
            return

        # --- Arrow keys for history (when no autocomplete) ---
        if event.key in ("up", "down") and self._history and not self._autocomplete_active:
            if event.key == "up":
                if self._history_index < 0:
                    self._saved_input = self.value
                    self._show_history(len(self._history) - 1)
                elif self._history_index > 0:
                    self._show_history(self._history_index - 1)
            elif event.key == "down":
                if self._history_index >= 0 and self._history_index < len(self._history) - 1:
                    self._show_history(self._history_index + 1)
                elif self._history_index == len(self._history) - 1:
                    self._restore_saved_input()
            return

        # --- Enter: select from autocomplete ---
        if event.key == "enter" and self._autocomplete_active:
            dropdown = self._get_dropdown()
            if dropdown is not None and dropdown.selected_item is not None:
                current = self.value
                if current and "@" in current:
                    self.value = (
                        current.rsplit("@", 1)[0] + "@" + dropdown.selected_item + " "
                    )
                elif current and current.startswith("/"):
                    self.value = dropdown.selected_item
            self._autocomplete_active = False
            self._autocomplete_sources = []
            self._remove_dropdown()
            # Fall through to super()._on_key(event) so that ChatScreen's
            # on_input_submitted fires and dispatches slash commands.  We
            # don't return — Enter must propagate.

        # --- Escape: dismiss ---
        if event.key == "escape" and self._autocomplete_active:
            self._autocomplete_active = False
            self._autocomplete_sources = []
            self._remove_dropdown()
            return

        await super()._on_key(event)

    # -- Reactive watcher: fires AFTER value changes ---------------------------

    def watch_value(self, value: str) -> None:
        """Show @ or / autocomplete whenever the value changes.

        Textual calls this reactive watcher reliably after every value
        change — no timing issues with ``_on_key``."""

        # --- Search mode: filter history ---
        if self._search_mode:
            PREFIX = "(reverse-i-search)`"
            if value.startswith(PREFIX):
                query = value[len(PREFIX):].strip()
                if query != self._search_query:
                    self._search_query = query
                    if query:
                        self._search_matches = [
                            (i, h) for i, h in enumerate(self._history)
                            if query.lower() in h.lower()
                        ]
                        self._search_match_idx = (
                            len(self._search_matches) - 1
                            if self._search_matches else -1
                        )
                        if self._search_matches:
                            self._show_history(
                                self._search_matches[self._search_match_idx][0]
                            )
                    else:
                        self._search_matches = []
            return

        if not value:
            self._autocomplete_active = False
            self._autocomplete_sources = []
            self._remove_dropdown()
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
        self._remove_dropdown()

    # -- Display helpers -------------------------------------------------------

    def _show_at_dropdown(self, prefix: str = "") -> None:
        """Mount and populate the @ autocomplete dropdown widget."""
        matches = self.get_at_completions(prefix)
        if not matches:
            self._remove_dropdown()
            return
        dropdown = self._get_or_create_dropdown()
        dropdown.update_items(matches)
        dropdown.show_dropdown()

    def _show_slash_dropdown(self, current: str = "") -> None:
        """Mount and populate the / slash command dropdown widget."""
        matches = [cmd for cmd in self.SLASH_COMMANDS if cmd.startswith(current)]
        if not matches:
            self._remove_dropdown()
            return
        dropdown = self._get_or_create_dropdown()
        dropdown.update_items(matches)
        dropdown.show_dropdown()

    # -- Dropdown widget management --------------------------------------------

    def _get_or_create_dropdown(self) -> AtAutocomplete:
        """Return the existing dropdown or create+ mount a new one.

        The dropdown is mounted inside the input-area Container, *before*
        the PromptInput so it renders above the input field.
        """
        dropdown = self._get_dropdown()
        if dropdown is not None:
            return dropdown

        from pyharness.tui.widgets.at_autocomplete import AtAutocomplete

        dropdown = AtAutocomplete(
            agent_names=self.AGENT_NAMES,
            classes="autocomplete-dropdown",
        )
        # Mount inside the parent container (#input-area), before PromptInput
        self.parent.mount(dropdown, before=self)
        return dropdown

    def _get_dropdown(self) -> AtAutocomplete | None:
        """Return the autocomplete dropdown if it exists on the screen."""
        from pyharness.tui.widgets.at_autocomplete import AtAutocomplete

        try:
            return self.screen.query_one(
                ".autocomplete-dropdown", expect_type=AtAutocomplete
            )
        except Exception:
            return None

    def _remove_dropdown(self) -> None:
        """Remove the autocomplete dropdown widget from the screen."""
        dropdown = self._get_dropdown()
        if dropdown is not None:
            dropdown.remove()

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
        except Exception as exc:
            self.log(f"[autocomplete] {exc}")
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

    def fuzzy_search_files(
        self, partial: str, project_root: Path | None = None
    ) -> list[str]:
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
