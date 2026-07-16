"""HTTP server for pyharness — serves the API and optional web UI."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app(config: Any = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: A :class:`~pyharness.config.schema.PyHarnessConfig` instance
            (or ``None`` when no project config is available).

    Returns:
        A fully-configured FastAPI app with health and config endpoints.
    """
    app = FastAPI(title="pyharness", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.3.0"}

    @app.get("/api/config")
    async def get_config() -> dict[str, str]:
        if config:
            return {"model": config.model, "agent": config.agent}
        return {"status": "no config loaded"}

    return app
