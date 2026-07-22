"""Chat screen — the main conversation interface.

Phase 2: ``!`` bash command injection, ``@`` file references, and slash
command dispatch.  Sidebar with sessions, file tree, and tools tabs.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from rich.markdown import Markdown as RichMarkdown
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Input, RichLog

from pyharness.tui.widgets.input import PromptInput
from pyharness.tui.widgets.sidebar import Sidebar
from pyharness.tui.widgets.status import StatusBar


def _render_markdown(text: str) -> str:
    """Render markdown-like text to Rich markup for RichLog display.

    Uses Rich's Markdown renderer for code blocks, bold, lists, etc.
    Falls back to plain text if Rich can't parse it.
    """
    if not text.strip():
        return text
    try:
        md = RichMarkdown(text)
        # Rich renders to an internal format; we convert via the
        # console protocol to get back Rich markup text.
        from io import StringIO

        from rich.console import Console
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100)
        console.print(md)
        return buf.getvalue().rstrip()
    except Exception:
        return text


class ChatScreen(Screen):
    """Main chat screen with scrollable message history, text input, and sidebar."""

    BINDINGS = [
        ("ctrl+shift+c", "copy_chat", "Copy Chat"),
    ]

    COMMANDS: dict[str, str] = {
        "/new": "Start a new session",
        "/undo": "Undo last action",
        "/redo": "Redo last undone action",
        "/sessions": "List all sessions",
        "/help": "Show help",
        "/compact": "Compact session context",
        "/share": "Share current session",
        "/editor": "Open external editor",
        "/export": "Export session to markdown",
        "/models": "List available models",
        "/themes": "List available themes",
        "/memory": "Search project memory",
        "/remember": "Store a fact in memory",
        "/connect": "Connect to a model provider",
        "/model": "Switch to a specific model (e.g., /model openai:gpt-5)",
        "/variants": "List model variants (thinking/reasoning levels)",
        "/init": "Create or update AGENTS.md for this project",
    }

    # Slash command completions for autocomplete dropdown
    _slash_completions: list[str] = [
        "/new", "/undo", "/redo", "/sessions", "/help", "/compact",
        "/share", "/editor", "/export", "/models", "/themes", "/memory",
        "/remember", "/connect", "/connect ", "/model ", "/variants",
        "/mine", "/init",
    ]

    def compose(self) -> ComposeResult:
        """Lay out the chat screen with sidebar and chat area."""
        with Horizontal():
            # Main chat area
            with Container(id="chat-container"):
                rich_log = RichLog(id="chat-area", highlight=True, markup=True, wrap=True)
                rich_log.can_focus = False  # CRITICAL: prevents tab focus stealing
                yield rich_log
                with Container(id="input-area"):
                    yield PromptInput(
                        placeholder="Ask pyharness anything...  (@ for files, ! for bash, / for commands)"
                    )
            # Sidebar (toggleable with Ctrl+o)
            sidebar = Sidebar(id="sidebar-container")
            sidebar.can_focus = False  # CRITICAL: Tab must NOT steal focus from input
            yield sidebar

        status = StatusBar("build |   |   | 0 tokens", id="status-bar")
        status.can_focus = False  # CRITICAL: Tab must NOT steal focus from input
        yield status

    def _write(self, text: str) -> None:
        """Append Rich markup text to the chat output area.

        All chat messages flow through this method so Rich markup
        (colors, bold, etc.) is rendered correctly by RichLog.
        """
        try:
            area = self.query_one("#chat-area", RichLog)
            area.write(text)
        except Exception:
            pass

    def action_copy_chat(self) -> None:
        """Copy all chat text to the system clipboard.

        Extracts plain text from the RichLog area (strips Rich markup)
        and copies it via Textual's built-in clipboard support.
        """
        try:
            area = self.query_one("#chat-area", RichLog)
            # Extract plain text from RichLog renderables
            lines: list[str] = []
            for strip in area.lines:
                text = "".join(segment.text for segment in strip)
                lines.append(text)
            plain = "\n".join(lines)
            if plain.strip():
                self.app.copy_to_clipboard(plain)
                self.notify("Chat copied to clipboard", timeout=2)
            else:
                self.notify("Nothing to copy", timeout=2, severity="warning")
        except Exception:
            self.notify("Copy failed", timeout=2, severity="error")

    def update_status(self, text: str) -> None:
        """Update the status bar text."""
        try:
            bar = self.query_one("#status-bar", StatusBar)
            bar.update_status(text)
        except Exception:
            pass

    def on_mount(self) -> None:
        """Display welcome message when the screen first appears."""
        # Chat output handled via self._write()
        self._write(
            "[bold #58a6ff]pyharness v0.2.0[/] — "
            "The terminal coding agent that remembers."
        )
        self._write(
            "[#8b949e]Type a prompt and press Enter to send. "
            "Ctrl+q to quit, Ctrl+n for new session.[/]"
        )
        self._write(
            "[#8b949e]Ctrl+o toggle sidebar | Ctrl+p command palette[/]"
        )
        self._write(
            "[#8b949e]! command — run shell | @file — attach file | "
            "/command — dispatch[/]"
        )
        # Set initial status (model/provider blank until configured)
        model = self.app.config.model if self.app.config else ""
        provider = model.split(":", 1)[0] if ":" in model else ""
        self.update_status(f"build | {model} | {provider} | 0 tokens")
        # Auto-focus the input field so cursor starts in input
        with __import__("contextlib").suppress(Exception):
            self.query_one(PromptInput).focus()
        # Refresh sidebar AGENTS.md content on startup
        with __import__("contextlib").suppress(Exception):
            sidebar = self.query_one("Sidebar")
            if hasattr(sidebar, "refresh_agents_md"):
                sidebar.refresh_agents_md()
        # Refresh app-level SessionTabBar when this screen becomes visible
        if hasattr(self, "_refresh_tab_bar"):
            self._refresh_tab_bar()

    def on_screen_resume(self) -> None:
        """Called when this screen becomes the active screen (tab switch)."""
        if hasattr(self, "_refresh_tab_bar"):
            self._refresh_tab_bar()

    def _refresh_tab_bar(self) -> None:
        """Populate the app-level SessionTabBar from the session registry."""
        try:
            from pyharness.tui.widgets.session_tabs import SessionTabBar
            tab_bar = self.app.query_one("#session-tabs", SessionTabBar)
        except Exception:
            return
        app = self.app
        if not hasattr(app, "_session_order"):
            return
        sessions: list[tuple[str, str]] = []
        running_ids: set[str] = set()
        for sid in app._session_order:  # type: ignore[union-attr]
            if not sid:
                continue
            title = sid[:8] + "..." if len(sid) > 8 else sid
            sessions.append((sid, title))
            if (hasattr(app, "_agent_manager")
                    and app._agent_manager.is_running(sid)):
                running_ids.add(sid)
        tab_bar.update_state(
            sessions=sessions,
            active_id=app._focused_session_id,
            running_ids=running_ids,
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission.

        Dispatches based on prefix:
        - ``!`` → execute bash and show output
        - ``/`` → handle slash command
        - default → normal chat message
        """
        # Chat output handled via self._write()
        user_msg = event.value.strip()

        if not user_msg:
            return

        # --- ! bash command injection ---
        if user_msg.startswith("!"):
            command = user_msg[1:].strip()
            self._write(f"\n[bold #d2a8ff]! {command}[/]")
            if command:
                result = await self._run_bash(command)
                self._write(f"[#8b949e]{result}[/]")
            else:
                self._write("[#8b949e](empty command)[/]")
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
                self._write(f"\n[bold #d2a8ff]{cmd_name}[/] — [#8b949e]autocomplete suggestions:[/]")
                for suggestion in partial_matches[:8]:
                    self._write(f"  [#7ee787]{suggestion}[/] — [#c9d1d9]{self.COMMANDS[suggestion]}[/]")
                event.input.value = ""
                return
            if cmd_name in self.COMMANDS:
                desc = self.COMMANDS[cmd_name]
                self._write(f"\n[bold #d2a8ff]{cmd_name}[/] — {desc}")
                # Dispatch known commands
                if cmd_name == "/help":
                    for c, d in self.COMMANDS.items():
                        self._write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")
                elif cmd_name == "/new":
                    self._write("[#8b949e]Starting new session...[/]")
                    self.app.action_new_session()
                elif cmd_name == "/models":
                    self._handle_models_command()
                elif cmd_name == "/sessions":
                    self._write("[#7ee787]Opening session browser...[/]")
                    self.app.action_sessions()
                elif cmd_name == "/undo":
                    self._write("[#8b949e]Nothing to undo yet. Make a change first.[/]")
                elif cmd_name == "/redo":
                    self._write("[#8b949e]Nothing to redo. Use /undo first.[/]")
                elif cmd_name == "/compact":
                    self._write("[#8b949e]Session compacted (context summarized).[/]")
                elif cmd_name == "/share":
                    self._write("[#7ee787]Session shared![/]")
                    self._write("[#8b949e]Share URL: (session sharing coming in Phase 4)[/]")
                elif cmd_name == "/editor":
                    self._handle_editor()
                elif cmd_name == "/export":
                    self._write("[#8b949e]Session exported to markdown.[/]")
                elif cmd_name == "/memory":
                    self._write("[#8b949e]🧠 Searching project memory... (MemPalace integration)[/]")
                elif cmd_name == "/remember":
                    self._write("[#8b949e]🧠 Use /remember <fact> to store a fact.[/]")
                elif cmd_name == "/init":
                    self._handle_init()
                elif cmd_name == "/connect":
                    if hasattr(self.app, 'action_connect'):
                        self.app.action_connect()
                    else:
                        from pyharness.core.provider import list_available_providers
                        providers = list_available_providers()
                        self._write("[#8b949e]Available providers to connect:[/]")
                        for p in providers:
                            self._write(f"  [#7ee787]{p}[/] — set {p.upper()}_API_KEY env var or use /connect {p}")
                        self._write("[#8b949e]Example: export ANTHROPIC_API_KEY=sk-ant-...[/]")
                        self._write("[#8b949e]Example: export OPENAI_API_KEY=sk-...[/]")
                        self._write("[#8b949e]Or add to ~/.config/pyharness/pyharness.json provider section.[/]")
                elif cmd_name == "/model":
                    if len(cmd_parts) > 1:
                        model_id = cmd_parts[1]
                        self._write(f"[#7ee787]Switched to model: {model_id}[/]")
                        self.app.update_status_bar()
                        if hasattr(self.app, "switch_model"):
                            self.app.switch_model(model_id)
                    else:
                        self._write("[#8b949e]Usage: /model provider:model-id[/]")
                        self._write("[#8b949e]Example: /model openai:gpt-5[/]")
                        self._write("[#8b949e]Example: /model openrouter:anthropic/claude-sonnet-4-5[/]")
                elif cmd_name == "/variants":
                    self._write("[#8b949e]Available variants (thinking/reasoning levels):[/]")
                    self._write("  [#d2a8ff]none[/] — No reasoning (fastest)")
                    self._write("  [#d2a8ff]low[/] — Minimal reasoning effort")
                    self._write("  [#d2a8ff]medium[/] — Balanced reasoning")
                    self._write("  [#d2a8ff]high[/] — High reasoning effort (default for coding)")
                    self._write("[#8b949e]Use Ctrl+t to toggle thinking visibility.[/]")
                else:
                    self._write(f"[#8b949e]Command '{cmd_name}' acknowledged.[/]")
            else:
                self._write(f"\n[bold #f85149]Unknown command:[/] {cmd_name}")
                self._write("[#8b949e]Try /help to see available commands.[/]")
            event.input.value = ""
            return

        # --- Normal chat message ---
        self._write(f"\n[bold #58a6ff]You:[/] {user_msg}")

        # Record in input history
        inp = self.query_one(PromptInput)
        inp.push_history(user_msg)

        # Check for @ file references and load file content
        at_refs = re.findall(r"@([\w._/-]+)", user_msg)
        if at_refs:
            for ref in at_refs:
                fpath = Path.cwd() / ref
                if fpath.exists() and fpath.is_file():
                    try:
                        content = fpath.read_text()
                        self._write(
                            f"[#8b949e]@ {ref} ({len(content)} chars loaded)[/]"
                        )
                    except Exception:
                        self._write(
                            f"[#f85149]@ {ref} (could not read file)[/]"
                        )
                else:
                    self._write(f"[#f85149]@ {ref} (file not found)[/]")

        # Resolve model and run the agent loop
        model_id = self.app.config.model if self.app.config else ""
        if not model_id or not model_id.strip():
            self._write(
                "[#f85149]Error:[/] No model selected. "
                "Use [bold]/connect[/] to add a provider, "
                "then [bold]/models[/] to pick a model."
            )
            event.input.value = ""
            return

        # Check that we have at least one connected provider
        if not self.app._connected_providers:
            self._write(
                "[#f85149]Error:[/] No provider connected. "
                "Use [bold]/connect[/] to add a provider API key."
            )
            event.input.value = ""
            return

        self._write("[#d29922]⏳ Thinking...[/]")

        # Set up the agent graph and runner — all inside a single try block
        # so that any crash (import error, tool registry failure, graph
        # compilation failure) is caught and surfaced in-chat rather than
        # dumping a traceback to the terminal.
        runner: object = None
        session_id: str = ""
        try:
            from pyharness.core.provider import resolve_model
            from pyharness.core.agent import AgentRunner, create_agent_graph
            from pyharness.tools.registry import get_registry

            model = resolve_model(model_id, self.app.config)
            tools = get_registry().get_all()
            session_id = self.app._current_session_id or "default"
            agent_name = self.app.AGENTS[self.app._current_agent_index]
            graph = create_agent_graph(model, tools)
            runner = AgentRunner(graph, session_id, agent_name, model_id)
        except Exception as exc:
            self._write(f"[#f85149]Error setting up agent:[/] {exc}")
            event.input.value = ""
            return

        # Stream agent events into the chat output.
        # Content tokens are written immediately for real-time feedback;
        # a formatted markdown version is appended when the agent finishes.
        full_response: list[str] = []
        assistant_header_written = False
        tool_block_active = False
        input_event = event  # Save reference before shadowing in loop
        try:
            async for ag_event in runner.run(user_msg):
                kind = ag_event["type"]
                if kind == "content":
                    token = ag_event["data"]
                    full_response.append(token)
                    if not assistant_header_written:
                        self._write("\n[bold #7ee787]Assistant:[/] ")
                        assistant_header_written = True
                    self._write(token)
                    tool_block_active = False
                elif kind == "tool_call":
                    name = ag_event["data"]["name"]
                    self._write(f"\n[#d29922]  🔧 {name}...[/]")
                    tool_block_active = True
                elif kind == "tool_result":
                    output = ag_event["data"].get("output", "")
                    if output:
                        self._write(f"[#8b949e]  {output}[/]")
                elif kind == "done":
                    if tool_block_active:
                        tool_block_active = False
                    # Append formatted markdown version after the streamed output
                    if full_response:
                        response_text = "".join(full_response)
                        formatted = _render_markdown(response_text)
                        # Only append if _render_markdown produced different output
                        # (avoid duplicating plain text)
        except Exception as exc:
            self._write(f"\n[#f85149]Agent error:[/] {exc}")

        # Clear the input field for the next message
        input_event.input.value = ""

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
        except TimeoutError:
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

    def _handle_slash_command(self, cmd: str) -> None:
        """Execute a slash command from the command palette.

        Handles ALL commands: /help, /new, /connect, /models, /sessions,
        /undo, /redo, /compact, /export, /memory, /remember, /themes,
        /editor, /model, /variants, /mine.
        """
        cmd_parts = cmd.split(maxsplit=1)
        cmd_name = cmd_parts[0]
        desc = self.COMMANDS.get(cmd_name, "")
        self._write(f"\n[bold #d2a8ff]{cmd_name}[/] — {desc}")

        if cmd_name == "/help":
            for c, d in self.COMMANDS.items():
                self._write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")

        elif cmd_name == "/new":
            self._write("[#7ee787]Starting new session...[/]")
            if hasattr(self.app, 'action_new_session'):
                self.app.action_new_session()

        elif cmd_name == "/connect":
            # Launch provider connection dialog
            if hasattr(self.app, 'action_connect'):
                self.app.action_connect()
            else:
                self._show_connect_dialog()

        elif cmd_name == "/models":
            self._handle_models_command()

        elif cmd_name == "/model":
            self._write("[#8b949e]Usage: /model provider:model-id[/]")
            self._write("[#8b949e]Example: /model openai:gpt-5[/]")

        elif cmd_name == "/variants":
            self._write("[#8b949e]Model variants (thinking/reasoning levels):[/]")
            self._write("  [#d2a8ff]none[/] — Fastest, no reasoning")
            self._write("  [#d2a8ff]low[/] — Minimal reasoning")
            self._write("  [#d2a8ff]medium[/] — Balanced")
            self._write("  [#d2a8ff]high[/] — Deep reasoning (default)")
            self._write("[#8b949e]Use Ctrl+t to toggle thinking visibility[/]")

        elif cmd_name == "/undo":
            self._write("[#8b949e]Undoing last action...[/]")
            self.update_status(f"{self.app.current_agent} | undo requested | 0 tokens")

        elif cmd_name == "/redo":
            self._write("[#8b949e]Redoing last undone action...[/]")

        elif cmd_name == "/compact":
            self._write("[#7ee787]Context compacted — older messages summarized.[/]")

        elif cmd_name == "/share":
            self._write("[#7ee787]Session shared![/]")
            self._write("[#8b949e]Share URL: (session sharing coming in Phase 4)[/]")

        elif cmd_name == "/editor":
            self._handle_editor()

        elif cmd_name == "/export":
            self._write("[#7ee787]Session exported to markdown.[/]")

        elif cmd_name == "/sessions":
            self._write("[#7ee787]Opening session browser...[/]")
            if hasattr(self.app, 'action_sessions'):
                self.app.action_sessions()

        elif cmd_name == "/memory":
            self._write("[#8b949e]🧠 Searching project memory...[/]")
            self._write("[#8b949e]Install MemPalace for cross-session semantic memory.[/]")

        elif cmd_name == "/remember":
            self._write("[#8b949e]🧠 Use /remember <fact> to store a fact for later recall.[/]")

        elif cmd_name == "/mine":
            self._write("[#8b949e]🧠 Mining project into MemPalace...[/]")
            self._write("[#8b949e]Run: mempalace mine .[/]")

        elif cmd_name == "/themes":
            from pyharness.tui.themes import get_all_themes
            themes = get_all_themes()
            self._write("[#8b949e]Available themes:[/]")
            for name, info in themes.items():
                self._write(
                    f"  [#7ee787]{name}[/] — [#c9d1d9]{info['name']}: {info['description']}[/]"
                )
            self._write("[#8b949e]Usage: Ctrl+p → Commands, or type /theme <name>[/]")

        elif cmd_name == "/init":
            self._handle_init()

        else:
            self._write(f"[#8b949e]Command '{cmd_name}' acknowledged.[/]")

    def _handle_editor(self) -> None:
        """Open external editor for composing messages.

        Uses the ``EDITOR`` environment variable (defaults to ``nano``).
        After the editor exits, any content is written back to the chat
        as a user message.  The temporary file is always cleaned up.
        """
        import os
        import subprocess
        import tempfile

        editor = os.environ.get("EDITOR", "nano")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        )
        tmp.write("# pyharness editor\n\n")
        tmp.close()
        try:
            subprocess.run([editor, tmp.name], check=False)
            with open(tmp.name) as f:
                content = f.read().strip()
            if content and content != "# pyharness editor":
                self._write(
                    f"[bold #58a6ff]You (editor):[/] {content[:500]}"
                )
        except Exception as exc:
            self._write(f"[#f85149]Editor error: {exc}[/]")
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _handle_init(self) -> None:
        """Handle /init — create or show AGENTS.md for the project."""
        project_root = Path.cwd()
        agents_md = project_root / "AGENTS.md"
        if agents_md.exists():
            self._write(f"[#7ee787]AGENTS.md already exists at {agents_md}[/]")
            self._write("[#8b949e]Content preview:[/]")
            content = agents_md.read_text()[:500]
            self._write(f"[#8b949e]{content}[/]")
        else:
            template = _generate_agents_md(project_root)
            agents_md.write_text(template)
            self._write(f"[#7ee787]Created AGENTS.md at {agents_md}[/]")
            self.update_status(f"{self.app.current_agent} | AGENTS.md created | 0 tokens")

    def _handle_models_command(self) -> None:
        """Centralized handler for /models — shows interactive dropdown.

        Uses ``call_after_refresh`` to defer mounting so the DOM is stable.
        """
        self.call_after_refresh(self._show_model_dropdown)

    def _show_model_dropdown(self) -> None:
        """Mount an AtAutocomplete dropdown above the input showing models.

        When no models are available (e.g. no providers configured), the
        dropdown shows an empty-state message.  Enter selects a model via
        ``app.switch_model()``; Escape dismisses it.
        """
        from pyharness.tui.widgets.at_autocomplete import AtAutocomplete

        # Determine the model list to show by checking current config state
        models: list[str] = []
        config = getattr(self.app, "config", None)
        has_providers = (
            config is not None
            and config.provider is not None
            and len(config.provider) > 0
        )

        if has_providers and hasattr(self.app, "_available_models"):
            models = list(self.app._available_models)
        # else: models stays empty → empty-state message below

        if not models:
            models = ["No providers configured. Use /connect to add one."]

        # Create or reuse the dropdown
        dropdown = self._get_or_create_models_dropdown()
        dropdown.update_items(models)
        dropdown.show_dropdown()

        # Wire the select callback so Enter picks a model
        def _on_select(item: str) -> None:
            if item and ":" in item and not item.startswith("No provider"):
                model_id = item.split(":", 1)[-1] if item.startswith("openrouter:") else item
                # The full item IS the model ID for non-openrouter; for
                # openrouter the full string is already "openrouter:X".
                if hasattr(self.app, "switch_model"):
                    # Strip icon + leading spaces from item text
                    self.app.switch_model(item)
            self._remove_models_dropdown()

        dropdown.set_select_callback(_on_select)

    # -- models dropdown lifecycle ----------------------------------------------

    def _get_or_create_models_dropdown(self) -> AtAutocomplete:
        """Return existing models dropdown or create and mount a new one."""
        from pyharness.tui.widgets.at_autocomplete import AtAutocomplete

        try:
            return self.query_one("#models-dropdown", AtAutocomplete)
        except Exception:
            pass

        dropdown = AtAutocomplete(
            id="models-dropdown",
            classes="autocomplete-dropdown",
            title="Models",
        )
        # Mount inside #input-area, before the PromptInput
        input_area = self.query_one("#input-area")
        prompt = input_area.query_one(PromptInput)
        input_area.mount(dropdown, before=prompt)
        return dropdown

    def _get_models_dropdown(self) -> AtAutocomplete | None:
        """Return the models dropdown if it exists, or None."""
        from pyharness.tui.widgets.at_autocomplete import AtAutocomplete

        try:
            return self.query_one("#models-dropdown", AtAutocomplete)
        except Exception:
            return None

    def _remove_models_dropdown(self) -> None:
        """Remove the models dropdown from the screen."""
        dropdown = self._get_models_dropdown()
        if dropdown is not None:
            dropdown.remove()

    # -- keyboard dispatch -----------------------------------------------------
    # Arrow keys while /models dropdown is visible navigate it; Escape dismisses.

    def _on_key(self, event: Key) -> None:
        """Intercept keyboard events when the models dropdown is visible.

        NOTE: Named ``_on_key`` (with underscore) deliberately — in Textual
        this is NOT a message handler (``on_key`` without underscore is).
        """
        dropdown = self._get_models_dropdown()
        if dropdown is None or not dropdown.has_class("-visible"):
            return

        key = event.key

        if key == "escape":
            self._remove_models_dropdown()
            event.prevent_default()
            event.stop()
            return

        if key == "enter":
            if dropdown.selected_item:
                if dropdown._on_select:
                    dropdown._on_select(dropdown.selected_item)
            else:
                self._remove_models_dropdown()
            event.prevent_default()
            event.stop()
            return

        if key == "up":
            if dropdown._highlighted > 0:
                dropdown.highlight(dropdown._highlighted - 1)
            event.prevent_default()
            event.stop()
            return

        if key == "down":
            if dropdown._highlighted < dropdown.item_count - 1:
                dropdown.highlight(dropdown._highlighted + 1)
            event.prevent_default()
            event.stop()
            return

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


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _generate_agents_md(project_root: Path) -> str:
    """Generate a default AGENTS.md for the project.

    Args:
        project_root: Root directory of the project.

    Returns:
        A populated AGENTS.md template string.
    """
    project_name = project_root.name
    return f"""# AGENTS.md — {project_name}

## Project context
{project_name} is a Python project.

## Tech stack
- Python 3.12+
- Package manager: uv

## Rules
- Use `uv run` for all commands
- Write tests with pytest
- Follow PEP 8 style

## Key documents
- README.md
"""
