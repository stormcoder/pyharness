"""Tests for the structured logging module."""

from __future__ import annotations

import logging

from pyharness.core.logging import get_logger, setup_logging


def test_setup_logging_console() -> None:
    """setup_logging should configure structlog without errors."""
    setup_logging(level="INFO")
    logger = get_logger("test")
    assert logger is not None
    # Should not raise
    logger.info("test_event", key="value")


def test_get_logger_returns_structlog() -> None:
    """get_logger should return a structlog BoundLogger."""
    setup_logging(level="INFO")
    logger = get_logger("my_module")
    assert hasattr(logger, "info")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "error")
    assert hasattr(logger, "debug")


def test_level_filtering_respects_level() -> None:
    """When level is WARNING, DEBUG and INFO should not appear in root handlers."""
    setup_logging(level="WARNING")
    root = logging.getLogger()
    # Root handler should be set to WARNING
    assert root.level == logging.WARNING

    # Reset for other tests
    setup_logging(level="INFO")


def test_silence_third_party_loggers() -> None:
    """Popular noisy libraries should be silenced to WARNING or above."""
    setup_logging(level="INFO")

    for name in ("asyncio", "httpx", "urllib3", "aiosqlite"):
        lib_logger = logging.getLogger(name)
        assert lib_logger.level >= logging.WARNING, (
            f"{name} logger should be WARNING+, got {lib_logger.level}"
        )
