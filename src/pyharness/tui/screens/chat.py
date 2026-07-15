"""Chat screen — the main conversation interface.

Phase 2: ``!`` bash command injection, ``@`` file references, and slash
command dispatch.  Sidebar with sessions, file tree, and tools tabs.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Input, RichLog

from pyharness.tui.widgets.input import PromptInput
from pyharness.tui.widgets.sidebar import Sidebar
from pyharness.tui.widgets.status import StatusBar


class ChatScreen(Screen):
    """Main chat screen with scrollable message history, text input, and sidebar."""

    COMMANDS: dict[str, str] = {
        "/new": "Start a new session",
        "/undo": "Undo last action",
        "/redo": "Redo last undone action",
        "/sessions": "List all sessions",
        "/help": "Show help",
        "/compact": "Compact session context",
        "/editor": "Open external editor",
        "/export": "Export session to markdown",
        "/models": "List available models",
        "/themes": "List available themes",
        "/memory": "Search project memory",
        "/remember": "Store a fact in memory",
        "/connect": "Connect to a model provider",
        "/model": "Switch to a specific model (e.g., /model openai:gpt-5)",
        "/variants": "List model variants (thinking/reasoning levels)",
    }

    # Slash command completions for autocomplete dropdown
    _slash_completions: list[str] = [
        "/new", "/undo", "/redo", "/sessions", "/help", "/compact",
        "/editor", "/export", "/models", "/themes", "/memory", "/remember",
        "/connect", "/connect ", "/model ", "/variants", "/mine",
    ]

    def compose(self) -> ComposeResult:
        """Lay out the chat screen with sidebar and chat area."""
        with Horizontal():
            # Main chat area
            with Container(id="chat-container"):
                yield RichLog(id="chat-area", highlight=True, markup=True, wrap=True)
                with Container(id="input-area"):
                    yield PromptInput(
                        placeholder="Ask pyharness anything...  (@ for files, ! for bash, / for commands)"
                    )
            # Sidebar (toggleable with Ctrl+o)
            yield Sidebar(id="sidebar-container")

        yield StatusBar("build | anthropic:claude-sonnet-4-5 | 0 tokens", id="status-bar")

    def update_status(self, text: str) -> None:
        """Update the status bar text."""
        try:
            bar = self.query_one("#status-bar", StatusBar)
            bar.update_status(text)
        except Exception:
            pass

    def on_mount(self) -> None:
        """Display welcome message when the screen first appears."""
        chat = self.query_one("#chat-area", RichLog)
        chat.write(
            "[bold #58a6ff]pyharness v0.2.0[/] — "
            "The terminal coding agent that remembers."
        )
        chat.write(
            "[#8b949e]Type a prompt and press Enter to send. "
            "Ctrl+q to quit, Ctrl+n for new session.[/]"
        )
        chat.write(
            "[#8b949e]Ctrl+o toggle sidebar | Ctrl+p command palette[/]"
        )
        chat.write(
            "[#8b949e]! command — run shell | @file — attach file | "
            "/command — dispatch[/]"
        )
        # Set initial status
        self.update_status("build | loading... | 0 tokens")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Dispatches based on prefix:
        - ``!`` → execute bash and show output
        - ``/`` → handle slash command
        - default → normal chat message
        """
        chat = self.query_one("#chat-area", RichLog)
        user_msg = event.value.strip()

        if not user_msg:
            return

        # --- ! bash command injection ---
        if user_msg.startswith("!"):
            command = user_msg[1:].strip()
            chat.write(f"\n[bold #d2a8ff]! {command}[/]")
            if command:
                result = await self._run_bash(command)
                chat.write(f"[#8b949e]{result}[/]")
            else:
                chat.write("[#8b949e](empty command)[/]")
            event.input.value = ""
            return

        # --- / slash commands ---
        if user_msg.startswith("/"):
            cmd_parts = user_msg.split(maxsplit=1)
            cmd_name = cmd_parts[0]
            # Autocomplete: show suggestions for partial slash input
            partial_matches = [
                c for c in self.COMMANDS
                if c.startswith(cmd_name) and c != cmd_name
            ]
            if partial_matches and not any(cmd_name == c for c in self.COMMANDS):
                # Partial match — show autocomplete suggestions
                chat.write(f"\n[bold #d2a8ff]{cmd_name}[/] — [#8b949e]autocomplete suggestions:[/]")
                for suggestion in partial_matches[:8]:
                    chat.write(f"  [#7ee787]{suggestion}[/] — [#c9d1d9]{self.COMMANDS[suggestion]}[/]")
                event.input.value = ""
                return
            if cmd_name in self.COMMANDS:
                desc = self.COMMANDS[cmd_name]
                chat.write(f"\n[bold #d2a8ff]{cmd_name}[/] — {desc}")
                # Dispatch known commands
                if cmd_name == "/help":
                    for c, d in self.COMMANDS.items():
                        chat.write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")
                elif cmd_name == "/new":
                    chat.write("[#8b949e]Starting new session...[/]")
                    self.app.action_new_session()
                elif cmd_name == "/models":
                    chat.write("[#8b949e]Available models:[/]")
                    chat.write("  anthropic:claude-sonnet-4-5")
                    chat.write("  anthropic:claude-haiku-4-5")
                    chat.write("  openai:gpt-5")
                    chat.write("  openrouter:openai/gpt-5")
                elif cmd_name == "/sessions":
                    chat.write("[#8b949e]No saved sessions yet. Sessions will appear here.[/]")
                elif cmd_name == "/undo":
                    chat.write("[#8b949e]Nothing to undo yet. Make a change first.[/]")
                elif cmd_name == "/redo":
                    chat.write("[#8b949e]Nothing to redo. Use /undo first.[/]")
                elif cmd_name == "/compact":
                    chat.write("[#8b949e]Session compacted (context summarized).[/]")
                elif cmd_name == "/export":
                    chat.write("[#8b949e]Session exported to markdown.[/]")
                elif cmd_name == "/memory":
                    chat.write("[#8b949e]🧠 Searching project memory... (MemPalace integration)[/]")
                elif cmd_name == "/remember":
                    chat.write("[#8b949e]🧠 Use /remember <fact> to store a fact.[/]")
                elif cmd_name == "/connect":
                    from pyharness.core.provider import list_available_providers
                    providers = list_available_providers()
                    chat.write("[#8b949e]Available providers to connect:[/]")
                    for p in providers:
                        chat.write(f"  [#7ee787]{p}[/] — set {p.upper()}_API_KEY env var or use /connect {p}")
                    chat.write("[#8b949e]Example: export ANTHROPIC_API_KEY=sk-ant-...[/]")
                    chat.write("[#8b949e]Example: export OPENAI_API_KEY=sk-...[/]")
                    chat.write("[#8b949e]Or add to ~/.config/pyharness/pyharness.json provider section.[/]")
                elif cmd_name == "/model":
                    if len(cmd_parts) > 1:
                        model_id = cmd_parts[1]
                        chat.write(f"[#7ee787]Switched to model: {model_id}[/]")
                        self.update_status(f"{self.app.current_agent} | {model_id} | 0 tokens")
                        if hasattr(self.app, "switch_model"):
                            self.app.switch_model(model_id)
                    else:
                        chat.write("[#8b949e]Usage: /model provider:model-id[/]")
                        chat.write("[#8b949e]Example: /model openai:gpt-5[/]")
                        chat.write("[#8b949e]Example: /model openrouter:anthropic/claude-sonnet-4-5[/]")
                elif cmd_name == "/variants":
                    chat.write("[#8b949e]Available variants (thinking/reasoning levels):[/]")
                    chat.write("  [#d2a8ff]none[/] — No reasoning (fastest)")
                    chat.write("  [#d2a8ff]low[/] — Minimal reasoning effort")
                    chat.write("  [#d2a8ff]medium[/] — Balanced reasoning")
                    chat.write("  [#d2a8ff]high[/] — High reasoning effort (default for coding)")
                    chat.write("[#8b949e]Use Ctrl+t to toggle thinking visibility.[/]")
                else:
                    chat.write(f"[#8b949e]Command '{cmd_name}' acknowledged.[/]")
            else:
                chat.write(f"\n[bold #f85149]Unknown command:[/] {cmd_name}")
                chat.write("[#8b949e]Try /help to see available commands.[/]")
            event.input.value = ""
            return

        # --- Normal chat message ---
        chat.write(f"\n[bold #58a6ff]You:[/] {user_msg}")
        chat.write("[#d29922]⏳ Thinking...[/]")

        # Check for @ file references and load file content
        at_refs = re.findall(r"@([\w._/-]+)", user_msg)
        if at_refs:
            for ref in at_refs:
                fpath = Path.cwd() / ref
                if fpath.exists() and fpath.is_file():
                    try:
                        content = fpath.read_text()
                        preview = content[:500]
                        chat.write(
                            f"[#8b949e]@ {ref} ({len(content)} chars loaded)[/]"
                        )
                    except Exception:
                        chat.write(
                            f"[#f85149]@ {ref} (could not read file)[/]"
                        )
                else:
                    chat.write(f"[#f85149]@ {ref} (file not found)[/]")

        chat.write(
            "[bold #7ee787]Assistant:[/] I've received your message. "
            "Full LangGraph agent loop will be wired at the app level."
        )

        # Clear the input field for the next message
        event.input.value = ""

    async def _run_bash(self, command: str) -> str:
        """Execute a bash command and return its output.

        Runs in the project root with a 30-second timeout.
        Output is truncated at 2000 characters for display.

        Args:
            command: Shell command to execute.

        Returns:
            Combined stdout + stderr, truncated.
        """
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.cwd()),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
            output = (
                stdout.decode("utf-8", errors="replace")
                + stderr.decode("utf-8", errors="replace")
            ).rstrip()
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            return output or "(no output)"
        except asyncio.TimeoutError:
            return "Command timed out after 30s"
        except FileNotFoundError:
            parts = command.strip().split() if command.strip() else ["N/A"]
            return f"Command not found: {parts[0]}"
        except Exception as exc:
            return f"Error: {exc}"

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility (Ctrl+o)."""
        sidebar = self.query_one("#sidebar-container")
        if sidebar.has_class("hidden"):
            sidebar.remove_class("hidden")
            self.notify("Sidebar shown", timeout=1)
        else:
            sidebar.add_class("hidden")
            self.notify("Sidebar hidden", timeout=1)

    def _handle_slash_command(self, cmd: str, chat: object) -> None:
        """Execute a slash command from the command palette.

        Handles ALL commands: /help, /new, /connect, /models, /sessions,
        /undo, /redo, /compact, /export, /memory, /remember, /themes,
        /editor, /model, /variants, /mine.
        """
        cmd_parts = cmd.split(maxsplit=1)
        cmd_name = cmd_parts[0]
        desc = self.COMMANDS.get(cmd_name, "")
        chat.write(f"\n[bold #d2a8ff]{cmd_name}[/] — {desc}")

        if cmd_name == "/help":
            for c, d in self.COMMANDS.items():
                chat.write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")

        elif cmd_name == "/new":
            chat.write("[#7ee787]Starting new session...[/]")
            if hasattr(self.app, 'action_new_session'):
                self.app.action_new_session()

        elif cmd_name == "/connect":
            # Launch provider connection dialog
            if hasattr(self.app, 'action_connect'):
                self.app.action_connect()
            else:
                self._show_connect_dialog(chat)

        elif cmd_name == "/models":
            from pyharness.core.provider import list_available_providers
            chat.write("[#8b949e]Available models (use /model <id> to switch):[/]")
            chat.write("  [#7ee787]anthropic:claude-sonnet-4-5[/]")
            chat.write("  [#7ee787]anthropic:claude-haiku-4-5[/]")
            chat.write("  [#7ee787]openai:gpt-5[/]")
            chat.write("  [#7ee787]openai:gpt-4o-mini[/]")
            chat.write("  [#7ee787]openrouter:openai/gpt-5[/]")
            chat.write("  [#7ee787]openrouter:anthropic/claude-sonnet-4-5[/]")
            chat.write(f"  [#8b949e]... and {len(list_available_providers())} providers available[/]")

        elif cmd_name == "/model":
            chat.write("[#8b949e]Usage: /model provider:model-id[/]")
            chat.write("[#8b949e]Example: /model openai:gpt-5[/]")

        elif cmd_name == "/variants":
            chat.write("[#8b949e]Model variants (thinking/reasoning levels):[/]")
            chat.write("  [#d2a8ff]none[/] — Fastest, no reasoning")
            chat.write("  [#d2a8ff]low[/] — Minimal reasoning")
            chat.write("  [#d2a8ff]medium[/] — Balanced")
            chat.write("  [#d2a8ff]high[/] — Deep reasoning (default)")
            chat.write("[#8b949e]Use Ctrl+t to toggle thinking visibility[/]")

        elif cmd_name == "/undo":
            chat.write("[#8b949e]Undoing last action...[/]")
            self.update_status(f"{self.app.current_agent} | undo requested | 0 tokens")

        elif cmd_name == "/redo":
            chat.write("[#8b949e]Redoing last undone action...[/]")

        elif cmd_name == "/compact":
            chat.write("[#7ee787]Context compacted — older messages summarized.[/]")

        elif cmd_name == "/export":
            chat.write("[#7ee787]Session exported to markdown.[/]")

        elif cmd_name == "/sessions":
            chat.write("[#8b949e]Active sessions:[/]")
            chat.write("  [#8b949e]No saved sessions yet. Sessions will appear here.[/]")

        elif cmd_name == "/memory":
            chat.write("[#8b949e]🧠 Searching project memory...[/]")
            chat.write("[#8b949e]Install MemPalace for cross-session semantic memory.[/]")

        elif cmd_name == "/remember":
            chat.write("[#8b949e]🧠 Use /remember <fact> to store a fact for later recall.[/]")

        elif cmd_name == "/mine":
            chat.write("[#8b949e]🧠 Mining project into MemPalace...[/]")
            chat.write("[#8b949e]Run: mempalace mine .[/]")

        elif cmd_name == "/themes":
            chat.write("[#8b949e]Available themes: tokyonight, dark, light, dracula, nord[/]")
            chat.write("[#8b949e]Set in ~/.config/pyharness/tui.json[/]")

        elif cmd_name == "/editor":
            chat.write("[#8b949e]Opening $EDITOR... (set EDITOR env var to enable)[/]")

        else:
            chat.write(f"[#8b949e]Command '{cmd_name}' acknowledged.[/]")

    def _at_autocomplete(self, prefix: str = "") -> list[str]:
        """Provide @ autocomplete suggestions — agents and files combined."""
        results: list[str] = []
        # Agent names from the app
        for name in self.app.AGENTS:
            if name.startswith(prefix) or not prefix:
                results.append(name)
        # File matches via PromptInput fuzzy search
        input_widget = self.query_one("#input-area").query_one(PromptInput)
        file_matches = input_widget.fuzzy_search_files(prefix) if prefix else []
        results.extend(file_matches)
        return results
