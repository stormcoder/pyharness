"""pyharness — The terminal coding agent that remembers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def main_async() -> None:
    """Start the pyharness application.

    Modes (auto-detected from CLI args):
    - ``--serve`` / ``-s``   → HTTP server mode (port 4096)
    - ``run <prompt>``       → single-shot CLI mode
    - (default)              → interactive TUI
    """
    args = sys.argv[1:]

    if "--serve" in args or "-s" in args:
        await serve_mode()
    elif len(args) > 1 and args[0] == "run":
        prompt = " ".join(args[1:])
        await run_mode(prompt)
    else:
        await tui_mode()


async def tui_mode() -> None:
    """Start the TUI."""
    from pyharness.tui.app import PyHarnessApp

    app = PyHarnessApp()
    await app.run_async()


async def run_mode(prompt: str) -> None:
    """Single-shot CLI mode.

    Resolves the configured model, binds tools, and invokes the agent
    with *prompt*, printing the response to stdout.
    """
    from pyharness.config.loader import load_config
    from pyharness.core.provider import resolve_model
    from pyharness.tools import register_all_tools
    from pyharness.tools.registry import get_registry

    register_all_tools()
    config = load_config(Path.cwd())
    model = resolve_model(config.model, config)
    tools = get_registry().get_all()

    print(f"pyharness v0.3.0 — {config.model}")
    print(f"Prompt: {prompt}")
    print("---")

    model_with_tools = model.bind_tools(tools)
    response = await model_with_tools.ainvoke(prompt)
    print(response.content)


async def serve_mode() -> None:
    """Start HTTP server mode."""
    import uvicorn
    from pyharness.config.loader import load_config
    from pyharness.server import create_app

    config = load_config(Path.cwd())
    app = create_app(config)

    host = "0.0.0.0"
    port = 4096
    print(f"pyharness server starting on http://{host}:{port}")
    server_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


def main() -> None:
    """CLI entrypoint."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
