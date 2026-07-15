"""pyharness — The terminal coding agent that remembers."""

from __future__ import annotations

import asyncio
import sys


async def main_async() -> None:
    """Start the pyharness TUI."""
    from pyharness.tui.app import PyHarnessApp

    app = PyHarnessApp()
    await app.run_async()


def main() -> None:
    """CLI entrypoint."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
