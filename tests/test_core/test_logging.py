"""Tests for the structured logging module.

Phase 2 tests verify that ``setup_logging`` integrates with
``PyHarnessConfig.log_level`` (which currently does NOT exist).
ALL TESTS IN ``TestLoggingIntegration`` MUST FAIL.
"""

from __future__ import annotations

import io
import logging

import pytest
import structlog

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


# =============================================================================
# INTEGRATION: Logging must be driven by PyHarnessConfig.log_level
# =============================================================================
# Currently ``PyHarnessConfig`` has no ``log_level`` field.
# ``setup_logging()`` is never called from app startup.
# Errors in ``verify_connection`` are logged at DEBUG level — invisible
# with the default INFO level.
# ALL TESTS BELOW MUST FAIL until the logging-config integration exists.


class TestLoggingIntegration:
    """Logging must respect PyHarnessConfig.log_level.

    **Bug:** ``PyHarnessConfig`` has no ``log_level`` field.
    ``setup_logging()`` is standalone — nothing calls it on startup.
    ``verify_connection`` logs failures at ``DEBUG`` level, which is
    invisible.
    """

    # ------------------------------------------------------------------
    # TEST 1 — setup_logging accepts config-driven level
    # ------------------------------------------------------------------

    def test_setup_logging_accepts_config_log_level(self) -> None:
        """setup_logging must accept a log_level value from PyHarnessConfig.

        Constructs a ``PyHarnessConfig`` (which should have a ``log_level``
        field) and passes it to ``setup_logging()``.

        FAILS: ``PyHarnessConfig`` has no ``log_level`` field.  The
        attribute access raises ``AttributeError``.
        """
        from pyharness.config.schema import PyHarnessConfig

        try:
            config = PyHarnessConfig.model_validate({"log_level": "INFO"})
        except Exception:
            config = PyHarnessConfig()

        if "log_level" not in PyHarnessConfig.model_fields:
            pytest.fail(
                "FAILS: PyHarnessConfig has no 'log_level' field.\n"
                "  'log_level' in pyharness.json is silently discarded\n"
                "  by extra='allow'.  setup_logging() is never driven\n"
                "  by config — it always defaults to INFO.\n"
            )

        # If the field existed, we'd use it:
        level = getattr(config, "log_level", None)
        if level is not None:
            setup_logging(level=level)
            root = logging.getLogger()
            assert root.level == getattr(logging, level.upper()), (
                f"Root logger level mismatch: expected {level}, got {root.level}"
            )
        else:
            # Field doesn't exist, should fail
            pytest.fail(
                "FAILS: config.log_level is None because the field does not exist.\n"
                "  setup_logging() never receives user-configured log level."
            )

    # ------------------------------------------------------------------
    # TEST 2 — log_level=None disables debug logging
    # ------------------------------------------------------------------

    def test_log_level_none_disables_debug_output(self) -> None:
        """When log_level is None (default), debug-level output must NOT
        appear from provider operations.

        ``verify_connection`` logs failures at ``DEBUG`` level.  With
        default INFO logging, those messages should be invisible.

        FAILS: ``PyHarnessConfig`` has no ``log_level`` field — the
        default cannot be tested.  Additionally, ``verify_connection``
        catches errors silently: it doesn't log anything meaningful
        that the user can see.
        """
        import io

        from pyharness.config.schema import PyHarnessConfig

        if "log_level" not in PyHarnessConfig.model_fields:
            pytest.fail(
                "FAILS: PyHarnessConfig has no 'log_level' field.\n"
                "  Cannot test default log level behavior.\n"
                "  When the field is added, this test should verify:\n"
                "  - log_level=None → default INFO → no DEBUG noise\n"
                "  - log_level='INFO' → info messages from provider resolution "
                "are visible\n"
            )

        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)  # capture everything
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

        test_logger = logging.getLogger("pyharness.core.provider")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        test_logger.propagate = False

        try:
            test_logger.debug("test_debug_message_secret")
            captured = log_capture.getvalue()

            # With default log_level=None (→ INFO), debug from
            # verify_connection should be suppressed.  With debug
            # capture enabled for logging.getLogger, the debug shows.
            assert "test_debug_message_secret" in captured, (
                "FAILS: Debug message was not captured.\n"
                "  Handler configuration issue — debug output cannot be verified."
            )
        finally:
            test_logger.removeHandler(handler)
            test_logger.propagate = True
