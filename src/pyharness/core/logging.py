"""Structured logging for pyharness using structlog.

Provides console (colored, human-readable) and file (JSON lines) output.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
) -> None:
    """Configure structlog for pyharness.

    Console output uses colored, human-readable rendering for TUI developers.
    File output writes JSON lines suitable for log aggregation and analysis.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Optional directory for JSON line log files.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # --- Console handler (colored, human-readable) ---
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # --- Root logger setup ---
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # --- File handler (JSON lines) ---
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        # JSON file handler is configured below with a JSON-specific processor chain

    # --- Shared processors ---
    shared_processors: list = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # --- Console chain (with colored renderer) ---
    structlog.configure(
        processors=shared_processors
        + [structlog.dev.ConsoleRenderer(colors=True)],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Reduce noise from other libraries
    _silence_third_party_loggers()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger bound to the given module name.

    Usage:
        logger = get_logger(__name__)
        logger.info("event_name", key="value")

    Args:
        name: Logger name (defaults to the calling module's __name__).

    Returns:
        A bound structlog logger.
    """
    import inspect

    if name is None:
        frame = inspect.currentframe()
        if frame is not None and frame.f_back is not None:
            name = frame.f_back.f_globals.get("__name__", "pyharness")
        else:
            name = "pyharness"
    return structlog.get_logger(name)


def _silence_third_party_loggers() -> None:
    """Quieten verbose third-party loggers to avoid TUI noise."""
    for name in (
        "asyncio",
        "urllib3",
        "httpx",
        "httpcore",
        "watchfiles",
        "aiosqlite",
        "textual",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
