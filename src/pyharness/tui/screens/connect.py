"""Connect screen — select a provider and enter API key."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from pyharness.core.provider import list_available_providers


class ConnectScreen(ModalScreen[str | None]):
    """Modal dialog for connecting to an LLM provider."""

    BINDINGS = [
        ("escape", "dismiss", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConnectScreen {
        align: center middle;
    }
    #connect-container {
        width: 56;
        height: auto;
        border: thick #30363d;
        background: #161b22;
        padding: 1 2;
    }
    #connect-title {
        color: #58a6ff;
        text-style: bold;
    }
    #connect-instructions {
        color: #8b949e;
        margin-bottom: 1;
    }
    #provider-label {
        color: #d2a8ff;
        text-style: bold;
    }
    #provider-list {
        height: 8;
        margin: 1 0;
        border: solid #30363d;
    }
    #api-key-input {
        margin-top: 1;
        border: solid #30363d;
    }
    #connect-buttons {
        margin-top: 1;
        align: right middle;
        height: auto;
    }
    #btn-connect {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        providers = list_available_providers()
        items = [ListItem(Static(f"[#7ee787]{p}[/]")) for p in providers]
        with Container(id="connect-container"):
            yield Static("[bold #58a6ff]Connect Provider[/]\n", id="connect-title")
            yield Static("[#8b949e]Select a provider, then enter your API key.[/]", id="connect-instructions")
            yield Static("[bold #d2a8ff]Providers:[/]", id="provider-label")
            yield ListView(*items, id="provider-list")
            yield Input(placeholder="Paste API key here...", id="api-key-input", password=True)
            with Container(id="connect-buttons"):
                yield Button("Connect", variant="primary", id="btn-connect")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-connect":
            list_view = self.query_one("#provider-list", ListView)
            api_input = self.query_one("#api-key-input", Input)

            # Find selected provider via highlighted child (robust fallback)
            children = list(list_view.children)
            highlighted = list_view.highlighted_child
            if highlighted is None or highlighted not in children:
                self.notify("Please select a provider first", severity="warning")
                return

            idx = children.index(highlighted)
            providers = list_available_providers()
            if idx >= len(providers):
                return
            provider = providers[idx]
            key = api_input.value.strip()

            if not key:
                self.notify("Please enter an API key", severity="warning")
                return

            # 1. Save the actual key (not a placeholder)
            self._save_provider_key(provider, key)

            # 2. Verify the connection asynchronously via Textual worker
            self._run_verification(provider, key)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _run_verification(self, provider: str, key: str) -> None:
        """Run async connection verification via a Textual worker.

        On success: dismiss with green message, update sidebar to green.
        On failure: show error notification, update sidebar to red, keep
            screen open for retry.
        """

        async def _verify() -> None:
            connected = await self._verify_and_report(provider, key)
            if connected:
                self._update_sidebar_provider_status(provider, True)
                self.dismiss(f"Connected to {provider}")
            else:
                self._update_sidebar_provider_status(provider, False)
                self.notify(
                    f"Connection failed for {provider}. "
                    "Check your API key and try again.",
                    severity="error",
                    timeout=5,
                )

        self.run_worker(_verify(), exclusive=False)

    def _save_provider_key(self, provider: str, key: str) -> None:
        """Save the provider API key via the canonical config persistence path.

        Uses :func:`pyharness.config.loader.save_config` to ensure
        JSON5 compatibility, env-var placeholder preservation,
        and proper deep-merge with the existing config file.
        """
        from pathlib import Path

        from pyharness.config.loader import load_config, save_config

        # Load the existing config with JSON5 support
        existing = load_config(Path.cwd())

        # Update the provider with the actual key
        from pyharness.config.schema import ProviderConfig

        if existing.provider is None:
            existing.provider = {}
        existing.provider[provider] = ProviderConfig(apiKey=key)

        # Persist via canonical path (handles JSON5 comments, env placeholders, merge)
        save_config(existing)

        # Also update the in-memory app config so the provider is
        # immediately visible without waiting for callback reload
        app = self.app
        if hasattr(app, "config"):
            app_config = app.config
            if app_config.provider is None:
                app_config.provider = {}
            app_config.provider[provider] = ProviderConfig(apiKey=key)

    async def _verify_and_report(self, provider: str, key: str) -> bool:
        """Verify the connection and return True if successful.

        Called after saving the key.  Tests the key against the
        provider API via :func:`verify_connection`.
        """
        from pyharness.core.provider import verify_connection

        try:
            return await verify_connection(provider, key)
        except Exception:
            return False

    def _update_sidebar_provider_status(
        self, provider: str, connected: bool
    ) -> None:
        """Update the sidebar's provider status indicator.

        On success: 🟢 provider_name
        On failure: 🔴 provider_name

        Stores status on the app and pushes it to the sidebar widget.
        """
        try:
            # Store on app so _handle_connect_result can also read it
            self.app._provider_status[provider] = connected
            # Push to sidebar if accessible (may be on the screen underneath)
            app = self.app
            if hasattr(app, "_update_sidebar_providers"):
                app._update_sidebar_providers()
        except Exception:
            pass
