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

            if key:
                self._save_provider_key(provider, key)
                self.dismiss(f"Connected to {provider}")
            else:
                self.notify("Please enter an API key", severity="warning")
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _save_provider_key(self, provider: str, key: str) -> None:
        """Save the provider API key to the user's pyharness config."""
        import json
        from pathlib import Path

        # Map provider name to config key
        env_var = f"{provider.upper()}_API_KEY".replace("-", "_")

        # Try to update global config
        config_path = Path.home() / ".config" / "pyharness" / "pyharness.json"

        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
            except Exception:
                config = {}
        else:
            config = {}

        # Update provider section
        if "provider" not in config:
            config["provider"] = {}
        config["provider"][provider] = {
            "apiKey": f"{{env:{env_var}}}",
        }

        # Write back
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        self.notify(
            f"[#7ee787]Provider {provider} configured![/]\n"
            f"[#8b949e]Set env var: export {env_var}=<your-key>[/]\n"
            f"[#8b949e]Or paste key directly in {config_path}[/]",
            severity="information",
            timeout=5,
        )
