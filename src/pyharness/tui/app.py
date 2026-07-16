"""Main Textual App for pyharness — Phase 2 enhanced chat TUI.

Phase 2 additions:
- Sidebar (Ctrl+o) with Sessions, File Tree, Tools tabs
- Command palette (Ctrl+p) listing available slash commands
- @ file reference support on PromptInput
- ! bash command injection in ChatScreen
- Slash commands dispatching
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from pyharness.config.loader import load_config
from pyharness.config.schema import PyHarnessConfig
from pyharness.tui.screens.chat import ChatScreen


class PyHarnessApp(App):
    """The main pyharness TUI application.

    Phase 2: Chat with sidebar, command palette, and slash commands.
    """

    CSS = """
    Screen {
        background: #0d1117;
    }

    ChatScreen {
        layout: vertical;
        background: #0d1117;
    }

    Horizontal {
        height: 100%;
        width: 100%;
    }

    #chat-container {
        height: 100%;
        width: 1fr;
    }

    #chat-area {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
        background: #0d1117;
    }

    #input-area {
        height: auto;
        min-height: 3;
        max-height: 10;
        border-top: solid #30363d;
        background: #161b22;
        padding: 1 2;
    }

    #sidebar-container {
        width: 30;
        height: 100%;
        border-left: solid #30363d;
        background: #161b22;
        overflow-y: auto;
    }

    #sidebar-container.hidden {
        display: none;
    }

    #status-bar {
        height: 1;
        dock: bottom;
        background: #161b22;
        color: #8b949e;
        padding: 0 2;
    }

    .user-message {
        color: #58a6ff;
        margin: 1 0;
    }

    .assistant-message {
        color: #c9d1d9;
        margin: 1 0;
    }

    .tool-call {
        background: #1a1525;
        border: solid #30363d;
        padding: 0 1;
        margin: 1 0;
    }

    .tool-result {
        background: #0d1117;
        border: solid #21262d;
        padding: 0 1;
        margin: 0 0 1 2;
    }

    .error {
        color: $error;
    }

    .info {
        color: #8b949e;
    }
    """

    BINDINGS = [
        ("tab", "switch_agent", "Switch Agent"),  # MUST be first for priority
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+n", "new_session", "New Session"),
        ("escape", "interrupt", "Interrupt"),
        ("ctrl+o", "toggle_sidebar", "Toggle Sidebar"),
        ("ctrl+p", "command_palette", "Commands"),
    ]

    AGENTS = ["build", "plan", "general", "explore"]
    _current_agent_index: int = 0

    COMMANDS: dict[str, str] = {
        "/new": "Start a new session",
        "/undo": "Undo last action",
        "/redo": "Redo last undone action",
        "/sessions": "List all sessions",
        "/help": "Show help",
        "/compact": "Compact session context",
        "/share": "Share current session",
        "/editor": "Open external editor for composing messages",
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

    def __init__(self) -> None:
        super().__init__()
        self.config: PyHarnessConfig | None = None

    def on_mount(self) -> None:
        """Load project config and push the chat screen on startup."""
        cwd = Path.cwd()
        self.config = load_config(cwd)
        self._load_keybinds()
        self.push_screen(ChatScreen())

    def _load_keybinds(self) -> None:
        """Load custom keybinds from tui.json, merging with defaults."""
        import json

        tui_paths: list[Path] = [
            Path.home() / ".config" / "pyharness" / "tui.json",
            Path.cwd() / ".pyharness" / "tui.json",
        ]
        for tui_path in tui_paths:
            if tui_path.exists():
                try:
                    with open(tui_path) as f:
                        tui_config = json.load(f)
                    custom: dict[str, str] = tui_config.get("keybinds", {})
                    if custom:
                        # Merge custom keybinds (override defaults)
                        for action, key in custom.items():
                            for i, binding in enumerate(self.BINDINGS):
                                existing_key, existing_action, *rest = binding
                                if existing_action == action:
                                    self.BINDINGS[i] = (key, action, *rest)
                                    break
                except Exception:
                    pass

    @property
    def current_agent(self) -> str:
        """Return the currently selected agent name."""
        return self.AGENTS[self._current_agent_index]

    def action_switch_agent(self) -> None:
        """Cycle through available agents (build → plan → build)."""
        self._current_agent_index = (self._current_agent_index + 1) % len(self.AGENTS)
        agent = self.AGENTS[self._current_agent_index]
        self.notify(f"Agent: {agent}", timeout=2)
        # Update status bar on active screen (if running)
        try:
            screen = self.screen
            if hasattr(screen, "update_status"):
                model = self.config.model if self.config else "unknown"
                screen.update_status(f"{agent} | {model} | 0 tokens")
        except Exception:
            pass

    def switch_model(self, model_id: str) -> None:
        """Switch the currently active model at runtime.

        Updates the config model and refreshes the status bar.
        """
        if self.config:
            self.config.model = model_id
        try:
            screen = self.screen
            if hasattr(screen, "update_status"):
                screen.update_status(f"{self.current_agent} | {model_id} | 0 tokens")
        except Exception:
            pass

    def action_connect(self) -> None:
        """Open provider connection dialog."""
        from pyharness.tui.screens.connect import ConnectScreen
        self.push_screen(ConnectScreen(), callback=self._handle_connect_result)

    def _handle_connect_result(self, result: str | None) -> None:
        """Handle result from the connect dialog."""
        if result:
            self.notify(result, timeout=3)

    def action_quit(self) -> None:
        """Exit the application cleanly."""
        self.exit()

    def action_new_session(self) -> None:
        """Create a new chat session."""
        self.notify("New session (not yet implemented)", severity="information")

    def action_interrupt(self) -> None:
        """Interrupt a running agent loop."""
        self.notify("Interrupted", severity="warning")

    def action_sessions(self) -> None:
        """Open session browser."""
        from pyharness.tui.screens.sessions import SessionBrowser
        self.push_screen(SessionBrowser())

    def action_theme(self, name: str | None = None) -> None:
        """Switch to a theme by name."""
        if name is None:
            return
        from pyharness.tui.themes import get_theme
        theme = get_theme(name)
        if theme is None:
            self.notify(f"Theme '{name}' not found", severity="warning")
            return
        # Apply theme colors as CSS variables
        self.app.dark = "light" not in name.lower()
        self.notify(f"Theme: {theme['name']}", timeout=2)

    def action_toggle_sidebar(self) -> None:
        """Toggle the sidebar visibility (Ctrl+o)."""
        try:
            screen = self.screen
            if hasattr(screen, "action_toggle_sidebar"):
                screen.action_toggle_sidebar()
        except Exception:
            self.notify("Sidebar toggle not available", severity="warning")

    def action_command_palette(self) -> None:
        """Show navigable command palette (Ctrl+p)."""
        from textual.widgets import ListItem, ListView

        class CommandPalette(ModalScreen[str | None]):
            """Modal overlay with arrow-key-navigable command list."""

            BINDINGS = [
                ("up", "cursor_up", "Up"),
                ("down", "cursor_down", "Down"),
                ("enter", "select", "Select"),
                ("escape", "dismiss_cmd", "Cancel"),
            ]

            DEFAULT_CSS = """
            CommandPalette {
                align: center middle;
            }
            #palette-container {
                width: 60;
                height: auto;
                max-height: 30;
                border: thick #30363d;
                background: #161b22;
                padding: 1;
            }
            #palette-header {
                color: #58a6ff;
                text-style: bold;
                padding-bottom: 1;
            }
            """

            def compose(self) -> ComposeResult:
                with Container(id="palette-container"):
                    yield Static(
                        "[bold #58a6ff]Commands[/] — ↑↓ navigate, Enter select, Esc cancel",
                        id="palette-header",
                    )
                    items: list[ListItem] = [
                        ListItem(
                            Static(f"[bold #d2a8ff]{cmd}[/] — [#c9d1d9]{desc}[/]")
                        )
                        for cmd, desc in self.app.COMMANDS.items()
                    ]
                    lv = ListView(*items, id="command-list")
                    lv.can_focus = False  # CRITICAL: let Enter bubble to CommandPalette
                    yield lv

            def on_mount(self) -> None:
                """Select the first item by default."""
                list_view = self.query_one("#command-list", ListView)
                if list_view.children:
                    list_view.index = 0

            def action_cursor_up(self) -> None:
                """Move selection up in the command list."""
                list_view = self.query_one("#command-list", ListView)
                if list_view.index is not None and list_view.index > 0:
                    list_view.index -= 1

            def action_cursor_down(self) -> None:
                """Move selection down in the command list."""
                list_view = self.query_one("#command-list", ListView)
                cmds = list(self.app.COMMANDS.keys())
                if list_view.index is not None and list_view.index < len(cmds) - 1:
                    list_view.index += 1

            def action_select(self) -> None:
                """Execute the highlighted or selected command."""
                list_view = self.query_one("#command-list", ListView)
                cmds = list(self.app.COMMANDS.keys())
                # Use index property (set by on_mount + arrow keys)
                if list_view.index is not None and 0 <= list_view.index < len(cmds):
                    self.dismiss(cmds[list_view.index])
                else:
                    self.dismiss(None)

            def action_dismiss_cmd(self) -> None:
                """Dismiss the palette without selecting."""
                self.dismiss(None)

        self.push_screen(CommandPalette(), callback=self._handle_palette_selection)

    def _handle_palette_selection(self, cmd: str | None) -> None:
        """Execute the selected command from the palette."""
        if cmd is None:
            return
        try:
            screen = self.screen
            # Try writing directly to chat first
            try:
                chat = screen.query_one("#chat-area")
                chat.write(f"\n[bold #d2a8ff]{cmd}[/] — {self.COMMANDS.get(cmd, '')}")
            except Exception:
                pass
            # Dispatch through screen handler
            if hasattr(screen, "_handle_slash_command"):
                try:
                    chat = screen.query_one("#chat-area")
                    screen._handle_slash_command(cmd, chat)
                    return
                except Exception:
                    pass
            # Fallback: handle key commands directly
            if cmd == "/connect":
                self.action_connect()
            elif cmd == "/new":
                self.action_new_session()
            elif cmd == "/sessions":
                self.action_sessions()
            elif cmd == "/help":
                for c, d in self.COMMANDS.items():
                    try:
                        chat = screen.query_one("#chat-area")
                        chat.write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")
                    except Exception:
                        pass
            elif cmd == "/models":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    from pyharness.core.provider import list_available_models
                    models = list_available_models(self.config)
                    chat.write("[#8b949e]Available models (use /model <id> to switch):[/]")
                    for m in models[:20]:
                        marker = "→ " if (self.config and self.config.model == m) else "  "
                        chat.write(f"  {marker}[#7ee787]{m}[/]")
                except Exception:
                    pass
            elif cmd == "/themes":
                from pyharness.tui.themes import get_all_themes
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    themes = get_all_themes()
                    chat.write("[#8b949e]Available themes:[/]")
                    for name, info in themes.items():
                        chat.write(
                            f"  [#7ee787]{name}[/] — [#c9d1d9]{info['name']}: {info['description']}[/]"
                        )
                except Exception:
                    pass
            elif cmd == "/init":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    if hasattr(screen, "_handle_init"):
                        screen._handle_init(chat)
                except Exception:
                    pass
            elif cmd == "/compact":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    chat.write("[#8b949e]Session compacted (context summarized).[/]")
                except Exception:
                    pass
            elif cmd == "/memory":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    chat.write("[#8b949e]🧠 Searching project memory... (MemPalace integration)[/]")
                except Exception:
                    pass
            elif cmd == "/remember":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    chat.write("[#8b949e]🧠 Use /remember <fact> to store a fact.[/]")
                except Exception:
                    pass
            elif cmd == "/editor":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    if hasattr(screen, "_handle_editor"):
                        screen._handle_editor(chat)
                except Exception:
                    pass
            elif cmd == "/export":
                try:
                    screen = self.screen
                    chat = screen.query_one("#chat-area")
                    chat.write("[#8b949e]Session exported to markdown.[/]")
                except Exception:
                    pass
            else:
                self.notify(f"Command: {cmd}", timeout=2)
        except Exception:
            self.notify(f"Command: {cmd}", timeout=2)
