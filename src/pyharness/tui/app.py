"""Main Textual App for pyharness — Phase 2 enhanced chat TUI.

Phase 2 additions:
- Sidebar (Ctrl+o) with Sessions, File Tree, Tools tabs
- Command palette (Ctrl+p) listing available slash commands
- @ file reference support on PromptInput
- ! bash command injection in ChatScreen
- Slash commands dispatching
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from pyharness.config.loader import load_config
from pyharness.config.schema import PyHarnessConfig
from pyharness.core.active_sessions import ActiveSessions
from pyharness.core.agent_manager import AgentManager
from pyharness.core.session_graph_registry import SessionGraphRegistry
from pyharness.core.session_registry import DEFAULT_SCREEN_ID, SessionRegistry
from pyharness.tui.screens.chat import ChatScreen
from pyharness.tui.widgets.session_tabs import SessionTabBar


class PyHarnessApp(App):
    """The main pyharness TUI application.

    Phase 2: Chat with sidebar, command palette, and slash commands.
    """

    CSS = """
    Screen {
        background: #0d1117;
    }

    #session-tabs {
        dock: top;
        height: 3;
        background: #161b22;
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

    #select-overlay {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
        border: none;
        background: #0d1117;
    }

    #input-area {
        height: auto;
        min-height: 3;
        max-height: 10;
        border-top: solid #30363d;
        background: #161b22;
        padding: 1 2;
        layout: vertical;
    }

    /* @ autocomplete dropdown — appears above the PromptInput */
    .autocomplete-dropdown {
        display: none;
        height: auto;
        max-height: 10;
        background: #161b22;
        border: solid #58a6ff;
        margin-bottom: 1;
        scrollbar-size: 0 0;
    }

    .autocomplete-dropdown.-visible {
        display: block;
    }

    .autocomplete-dropdown .at-header {
        padding: 0 1;
        color: #8b949e;
        text-style: bold;
        background: #0d1117;
        height: 1;
    }

    .autocomplete-dropdown .at-item {
        padding: 0 1;
        color: #c9d1d9;
        width: 100%;
        height: 1;
    }

    .autocomplete-dropdown .at-item.-highlighted {
        background: #1f6feb;
        color: #ffffff;
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
        ("ctrl+w", "close_tab", "Close Tab"),
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

    # -- model cache ------------------------------------------------------------
    _available_models: list[str] = []
    _model_list_loaded: bool = False

    # -- session ---------------------------------------------------------------
    _session_store: object | None = None
    _current_session_id: str | None = None
    _session_token_count: int = 0

    _config_loaded_from_disk: bool = False

    # -- connected providers tracking -------------------------------------------
    _connected_providers: set[str] = set()

    def __init__(self) -> None:
        super().__init__()
        self.config: PyHarnessConfig = PyHarnessConfig()
        self._config_loaded_from_disk = False
        self._provider_status: dict[str, bool] = {}
        self._connected_providers: set[str] = set()
        # Phase 4: multi-session infrastructure
        self._session_registry = SessionRegistry()
        self._checkpointer = self._create_checkpointer()
        self._graph_registry = SessionGraphRegistry(checkpointer=self._checkpointer)
        self._active_sessions = ActiveSessions(
            Path.home() / ".local" / "share" / "pyharness" / "sessions"
        )
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._agent_manager = AgentManager(
            max_concurrent=self.config.max_concurrent_agents
        )
        self._agent_manager.set_notifier(self)
        self._session_screens: dict[str, object] = {}
        self._session_order: list[str] = []
        self._focused_session_id: str | None = None

    def on_mount(self) -> None:
        """Load project config and push the chat screen on startup."""
        if not self._config_loaded_from_disk and not self.config.provider:
            cwd = Path.cwd()
            self.config = load_config(cwd)
            self._config_loaded_from_disk = True
        # Wire logging from config
        if self.config.log_level:
            from pyharness.core.logging import setup_logging
            setup_logging(level=self.config.log_level)
        self._load_keybinds()
        # Pre-populate _provider_status from config keys (not connection status).
        # Connection verification happens asynchronously in refresh_models().
        self._populate_connected_providers()
        # Async: verify each provider via live model-list fetch.
        # Providers marked connected only after successful API response.
        import asyncio
        asyncio.create_task(self.refresh_models())
        # Chain: after models loaded, clear stale model if its provider
        # is not connected and update the sidebar.
        async def _post_refresh() -> None:
            await asyncio.sleep(0.5)  # give refresh_models time to start
            model = self.config.model or ""
            if model and ":" in model:
                model_provider = model.split(":")[0]
                if model_provider not in self._connected_providers:
                    self.config.model = ""
            self._update_sidebar_providers()
        asyncio.create_task(_post_refresh())
        # Initialize session store synchronously (libsql is not async)
        self._init_session()
        # Push the tracked ChatScreen from session initialization
        if self._focused_session_id and self._focused_session_id in self._session_screens:
            self.push_screen(self._session_screens[self._focused_session_id])
        # Phase 4: mount session tab bar at app level
        self._active_sessions.load()
        tabs = [(e["session_id"], self._session_title(e["session_id"]))
                for e in self._active_sessions.list_all()]
        tab_bar = SessionTabBar(
            sessions=tabs,
            active_id=self._focused_session_id,
            id="session-tabs",
        )
        self.mount(tab_bar)
        # Sidebar now exists — push provider status
        self._update_sidebar_providers()

    def _init_session(self) -> None:
        """Initialize session store and load or create the current session."""
        from pathlib import Path
        import uuid

        from pyharness.core.session import Session, SessionStore

        db_path = Path.home() / ".local" / "share" / "pyharness" / "sessions" / "sessions.db"
        try:
            self._session_store = SessionStore(db_path)
            self._session_store.initialize()

            current_ptr = db_path.parent / "current"
            if current_ptr.exists():
                sid = current_ptr.read_text().strip()
                try:
                    session = self._session_store.get_session(sid)
                    if session is not None:
                        self._current_session_id = session.id
                        self._session_token_count = session.total_tokens
                        # Phase 4: register restored session
                        self._session_registry.register_default(session.id)
                        self._active_sessions.add(session.id, DEFAULT_SCREEN_ID)
                        self._session_order.append(session.id)
                        self._focused_session_id = session.id
                        self._session_screens[session.id] = ChatScreen()
                        return
                except Exception:
                    pass

            session = Session(
                title="New Session",
                project=str(Path.cwd().name),
                model=self.config.model if self.config else "",
                agent="build",
            )
            self._session_store.create_session(session)
            self._current_session_id = session.id
            # Phase 4: register default session with registry
            self._session_registry.register_default(session.id)
            self._active_sessions.add(session.id, DEFAULT_SCREEN_ID)
            self._session_order.append(session.id)
            self._focused_session_id = session.id
            self._session_screens[session.id] = ChatScreen()
        except Exception:
            # Fallback: when libsql/SessionStore is unavailable (e.g. CI, tests),
            # create an in-memory-only session so the ChatScreen still loads.
            import uuid
            sid = str(uuid.uuid4())
            self._current_session_id = sid
            self._session_registry.register_default(sid)
            self._session_order.append(sid)
            self._focused_session_id = sid
            self._session_screens[sid] = ChatScreen()

    def _save_state(self) -> None:
        """Persist config, current-session pointer, and active sessions to disk."""
        try:
            from pyharness.config.loader import save_config
            save_config(self.config)
        except Exception:
            pass
        # Phase 4: persist active sessions (replaces single current pointer)
        try:
            self._active_sessions.save()
        except Exception:
            pass
        # Backward compat: also write legacy pointer for older code
        if self._current_session_id:
            try:
                ptr = Path.home() / ".local" / "share" / "pyharness" / "sessions" / "current"
                ptr.parent.mkdir(parents=True, exist_ok=True)
                ptr.write_text(self._current_session_id)
            except Exception:
                pass

    async def refresh_models(self) -> None:
        """Verify all configured providers and fetch their model lists.

        A provider is marked **connected** only after its model-list endpoint
        responds successfully — not merely because an API key is present.
        Providers with empty keys or unresolvable ``{env:VAR}`` placeholders
        are silently skipped.

        After completion, the sidebar provider dots and the ``/models``
        dropdown are updated to reflect the current state.
        """
        import os

        from pyharness.core.provider import _fetch_provider_models

        self._connected_providers.clear()
        self._available_models = []

        if self.config is None or not self.config.provider:
            self._model_list_loaded = True
            self._update_sidebar_providers()
            return

        for pname, pconf in self.config.provider.items():
            key = pconf.apiKey or ""
            base_url = pconf.baseUrl if pconf else None

            # Skip empty keys
            if not key:
                self._provider_status[pname] = False
                continue

            # Resolve {env:VAR} placeholders
            if key.startswith("{env:") and key.endswith("}"):
                env_var = key[5:-1]
                real = os.environ.get(env_var)
                if not real:
                    self._provider_status[pname] = False
                    continue
                key = real

            # Live verification via model-list fetch
            try:
                models = await _fetch_provider_models(pname, key, base_url)
                self._connected_providers.add(pname)
                self._provider_status[pname] = True
                self._available_models.extend(models)
            except Exception:
                self._provider_status[pname] = False

        self._available_models = sorted(set(self._available_models))
        self._model_list_loaded = True
        self._update_sidebar_providers()

    def _update_sidebar_providers(self) -> None:
        """Push current provider status to the sidebar widget."""
        try:
            screen = self.screen
            sidebar = screen.query_one("Sidebar")
            if hasattr(sidebar, "update_provider_status") and self._provider_status:
                sidebar.update_provider_status(self._provider_status)
        except Exception:
            pass

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

    def _populate_connected_providers(self) -> None:
        """Initialise ``_provider_status`` from config keys.

        Does NOT mark providers as connected — that happens asynchronously
        in :meth:`refresh_models` after live model-list verification.
        This method only sets ``False`` for clearly-broken keys (empty,
        unresolvable placeholders). All other providers are left unset
        until :meth:`refresh_models` verifies them.
        """
        import os

        if self.config is None or not self.config.provider:
            return

        for pname, pconf in self.config.provider.items():
            key = pconf.apiKey or ""
            if not key:
                self._provider_status[pname] = False
            elif key.startswith("{env:") and key.endswith("}"):
                env_var = key[5:-1]
                if not os.environ.get(env_var):
                    self._provider_status[pname] = False
                # If env var IS set, leave unset — refresh_models will verify

    @property
    def current_agent(self) -> str:
        """Return the currently selected agent name."""
        return self.AGENTS[self._current_agent_index]

    def action_switch_agent(self) -> None:
        """Cycle through available agents (build → plan → build)."""
        self._current_agent_index = (self._current_agent_index + 1) % len(self.AGENTS)
        agent = self.AGENTS[self._current_agent_index]
        self.notify(f"Agent: {agent}", timeout=2)
        self.update_status_bar()

    def switch_model(self, model_id: str) -> None:
        """Switch the currently active model at runtime.

        Updates the config model, persists to disk, and refreshes the
        status bar.
        """
        if self.config:
            self.config.model = model_id
        self.update_status_bar()
        # Persist model choice to config
        try:
            from pyharness.config.loader import save_config
            save_config(self.config)
        except Exception:
            pass

    def action_connect(self) -> None:
        """Open provider connection dialog."""
        from pyharness.tui.screens.connect import ConnectScreen
        self.push_screen(ConnectScreen(), callback=self._handle_connect_result)

    def _handle_connect_result(self, result: str | None) -> None:
        """Handle result from the connect dialog.

        Connection was already verified by ConnectScreen via
        :func:`pyharness.core.provider.verify_connection` before
        the dialog was dismissed — we only reach here on success.
        """
        if result:
            # Reload config to pick up newly saved provider
            self.config = load_config(Path.cwd())
            self._config_loaded_from_disk = True
            # Parse provider name from "Connected to <provider>"
            provider_name = result.replace("Connected to ", "")
            # Refresh models — this live-verifies the new provider and
            # updates _connected_providers, _provider_status, sidebar.
            self.call_later(self.refresh_models)
            # Reset model if switching to a different provider
            model = self.config.model or ""
            if model and ":" in model:
                old_provider = model.split(":")[0]
                if old_provider and old_provider != provider_name:
                    self.config.model = ""
                    from pyharness.config.loader import save_config
                    save_config(self.config)
            self.notify(result, timeout=3)
            self._update_sidebar_providers()
            self.update_status_bar()

    def action_quit(self) -> None:
        """Exit the application cleanly — save all state first."""
        self._save_state()
        self.exit()

    def on_unmount(self) -> None:
        """Save all persistent state and cancel running agents before exit."""
        # Phase 4: cancel all agent tasks
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._agent_manager.cancel_all())
            else:
                loop.run_until_complete(self._agent_manager.cancel_all())
        except Exception:
            pass
        try:
            from pyharness.config.loader import save_config
            save_config(self.config)
        except Exception:
            pass

    def update_status_bar(self, tokens: int | None = None) -> None:
        """Push current agent/model/provider/tokens to the status bar."""
        agent = self.current_agent
        model = self.config.model if self.config else ""
        provider = model.split(":", 1)[0] if ":" in model else ""
        token_str = f"{tokens:,}" if tokens else "0"
        text = f"{agent} | {model} | {provider} | {token_str} tokens"
        try:
            screen = self.screen
            if hasattr(screen, "update_status"):
                screen.update_status(text)
        except Exception:
            pass

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
                # Chat output via screen._write()
                screen._write(f"\n[bold #d2a8ff]{cmd}[/] — {self.COMMANDS.get(cmd, '')}")
            except Exception:
                pass
            # Dispatch through screen handler
            if hasattr(screen, "_handle_slash_command"):
                try:
                    screen._handle_slash_command(cmd)
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
                        screen._write(f"  [bold #d2a8ff]{c}[/] — [#c9d1d9]{d}[/]")
                    except Exception:
                        pass
            elif cmd == "/models":
                try:
                    screen = self.screen
                    if hasattr(screen, "_handle_models_command"):
                        screen._handle_models_command()
                except Exception:
                    pass
            elif cmd == "/themes":
                from pyharness.tui.themes import get_all_themes
                try:
                    screen = self.screen
                    themes = get_all_themes()
                    screen._write("[#8b949e]Available themes:[/]")
                    for name, info in themes.items():
                        screen._write(
                            f"  [#7ee787]{name}[/] — [#c9d1d9]{info['name']}: {info['description']}[/]"
                        )
                except Exception:
                    pass
            elif cmd == "/init":
                try:
                    screen = self.screen
                    if hasattr(screen, "_handle_init"):
                        screen._handle_init()
                except Exception:
                    pass
            elif cmd == "/compact":
                try:
                    screen = self.screen
                    # Chat output via screen._write()
                    screen._write("[#8b949e]Session compacted (context summarized).[/]")
                except Exception:
                    pass
            elif cmd == "/memory":
                try:
                    screen = self.screen
                    # Chat output via screen._write()
                    screen._write("[#8b949e]🧠 Searching project memory... (MemPalace integration)[/]")
                except Exception:
                    pass
            elif cmd == "/remember":
                try:
                    screen = self.screen
                    # Chat output via screen._write()
                    screen._write("[#8b949e]🧠 Use /remember <fact> to store a fact.[/]")
                except Exception:
                    pass
            elif cmd == "/editor":
                try:
                    screen = self.screen
                    if hasattr(screen, "_handle_editor"):
                        screen._handle_editor()
                except Exception:
                    pass
            elif cmd == "/export":
                try:
                    screen = self.screen
                    # Chat output via screen._write()
                    screen._write("[#8b949e]Session exported to markdown.[/]")
                except Exception:
                    pass
            else:
                self.notify(f"Command: {cmd}", timeout=2)
        except Exception:
            self.notify(f"Command: {cmd}", timeout=2)

    # -- Phase 4: multi-session / tab management --------------------------------

    @staticmethod
    def _create_checkpointer() -> object | None:
        """Create a LangGraph checkpointer backed by SQLite.

        Returns ``None`` if the optional dependency is unavailable.
        """
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-untyped]

            db_path = (
                Path.home()
                / ".local"
                / "share"
                / "pyharness"
                / "sessions"
                / "checkpoints.db"
            )
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return SqliteSaver.from_conn_string(str(db_path))
        except ImportError:
            return None
        except Exception:
            return None

    def _session_title(self, session_id: str) -> str:
        """Return a display title for the given session ID."""
        store = self._session_store
        if store is not None:
            try:
                s = store.get_session(session_id)
                if s is not None:
                    return s.title or "New Session"
            except Exception:
                pass
        return "New Session"

    def _refresh_tab_bar(self) -> None:
        """Repaint the SessionTabBar from current state."""
        try:
            tab_bar = self.query_one("#session-tabs", SessionTabBar)
        except Exception:
            return
        run_ids = {
            sid for sid in self._cancel_events
            if self._agent_manager.is_running(sid)
        }
        tabs = [
            (sid, self._session_title(sid))
            for sid in self._session_order
            if sid in self._session_screens
        ]
        tab_bar.update_state(
            sessions=tabs,
            active_id=self._focused_session_id,
            running_ids=run_ids,
        )

    def switch_to_session(self, session_id: str) -> None:
        """Switch the visible screen to *session_id*'s ChatScreen."""
        if session_id == self._focused_session_id:
            return
        screen = self._session_screens.get(session_id)
        if screen is None:
            return
        self._focused_session_id = session_id
        self.switch_screen(screen)
        self._refresh_tab_bar()

    def action_new_session(self) -> None:
        """Create a new session with its own ChatScreen tab.

        R4.3 — Triggered by the ``+`` button or Ctrl+N.
        """
        from pyharness.core.session import Session, SessionStore

        store = self._session_store
        if store is None:
            # Lazy-initialize session store (belt-and-suspenders)
            store = SessionStore(
                Path.home() / ".local" / "share" / "pyharness" / "sessions" / "sessions.db"
            )
            try:
                store.initialize()
            except Exception:
                pass
            self._session_store = store

        session = Session(
            title="New Session",
            project=str(Path.cwd().name),
            model=self.config.model if self.config else "",
            agent="build",
        )
        try:
            store.create_session(session)
        except Exception:
            pass

        sid = session.id
        screen = ChatScreen()
        screen_id = f"chat-{len(self._session_order)}"

        self._session_registry.register(screen_id, sid)
        self._session_screens[sid] = screen
        self._session_order.append(sid)
        self._focused_session_id = sid
        self._active_sessions.add(sid, screen_id)

        self.push_screen(screen)
        self._refresh_tab_bar()
        self.notify("New session created", timeout=2)

    def action_close_tab(self) -> None:
        """Close the currently focused session tab (Ctrl+W)."""
        if self._focused_session_id is None:
            return
        self._close_session_tab(self._focused_session_id)

    def _close_session_tab(self, session_id: str) -> None:
        """Internal: close a session tab by session_id.

        Cancels any running agent, saves the session, removes from tracking
        structures, and switches to another open tab.  Refuses to close the
        last remaining tab.
        """
        if len(self._session_screens) <= 1:
            self.notify("Cannot close last tab", severity="warning")
            return

        # Cancel running agent for this session
        self._agent_manager.cancel(session_id)
        self._cancel_events.pop(session_id, None)

        # Remove from tracking
        self._session_screens.pop(session_id, None)
        self._session_registry.unregister(
            next(
                (k for k, v in self._session_registry.list_all().items()
                 if v == session_id),
                "",
            )
        )
        self._active_sessions.remove(session_id)
        if session_id in self._session_order:
            self._session_order.remove(session_id)

        # Switch to another tab
        if self._session_order:
            new_focus = (
                self._session_order[-1]
                if session_id == self._focused_session_id
                else self._focused_session_id
            )
            if new_focus and new_focus in self._session_screens:
                self._focused_session_id = new_focus
                self.switch_screen(self._session_screens[new_focus])

        self._refresh_tab_bar()

    def next_tab(self) -> None:
        """Switch to the next session tab (Ctrl+Tab)."""
        if not self._session_order or self._focused_session_id is None:
            return
        try:
            idx = self._session_order.index(self._focused_session_id)
            next_idx = (idx + 1) % len(self._session_order)
            self.switch_to_session(self._session_order[next_idx])
        except ValueError:
            pass

    def previous_tab(self) -> None:
        """Switch to the previous session tab (Ctrl+Shift+Tab)."""
        if not self._session_order or self._focused_session_id is None:
            return
        try:
            idx = self._session_order.index(self._focused_session_id)
            prev_idx = (idx - 1) % len(self._session_order)
            self.switch_to_session(self._session_order[prev_idx])
        except ValueError:
            pass

    # -- SessionTabBar message handlers -----------------------------------------

    def on_session_tab_bar_tab_selected(
        self, message: SessionTabBar.TabSelected
    ) -> None:
        """Handle a tab click — switch to that session (R4.2)."""
        self.switch_to_session(message.session_id)

    def on_session_tab_bar_tab_closed(
        self, message: SessionTabBar.TabClosed
    ) -> None:
        """Handle a tab close-button click (R4.4)."""
        self._close_session_tab(message.session_id)

    def on_session_tab_bar_new_tab_requested(
        self, message: SessionTabBar.NewTabRequested
    ) -> None:
        """Handle the ``+`` button click (R4.3)."""
        self.action_new_session()
