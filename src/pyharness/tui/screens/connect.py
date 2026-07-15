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
            if list_view.index is not None:
                provider = list_available_providers()[list_view.index]
                key = api_input.value.strip()
                if key:
                    self._save_provider_key(provider, key)
                    self.dismiss(f"Connected to {provider}")
                else:
                    self.notify("Please enter an API key", severity="warning")
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _save_provider_key(self, provider: str, key: str) -> None:
        """Save provider API key. For now, display instructions."""
        env_var = f"{provider.upper()}_API_KEY".replace("-", "_")
        self.notify(
            f"Set environment variable: export {env_var}=your-key\n"
            f"Or add to ~/.config/pyharness/pyharness.json",
            severity="information", timeout=5,
        )
