"""Shared test fixtures for pyharness."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

from pyharness.core.testing import (
    FakeLLMProvider,
    make_echo_provider,
)


# ---------------------------------------------------------------------------
# Global config protection
# ---------------------------------------------------------------------------
# Redirect ALL save_config calls during tests to a temp file so the
# user's ~/.config/pyharness/pyharness.json is never overwritten by
# test suite runs.  Individual tests that need precise control over
# their config path can override this with patch.dict.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_pyharness_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set PYHARNESS_CONFIG to a throwaway temp file for every test."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="pyharness_test_")
    os.close(fd)
    Path(path).write_text("{}")
    monkeypatch.setenv("PYHARNESS_CONFIG", path)

# ---------------------------------------------------------------------------
# Session store fixtures (pre-existing)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a unique SQLite database path inside a temp directory."""
    return tmp_path / f"test-{uuid.uuid4().hex[:8]}.db"


@pytest.fixture
def store(tmp_db_path: Path):
    """Return an initialized SessionStore connected to a temp database."""
    from pyharness.core.session import SessionStore

    s = SessionStore(tmp_db_path)
    s.initialize()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Project / filesystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample files."""
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text('print("hello")')
    (project / "README.md").write_text("# Test Project")
    (project / ".git").mkdir()
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main")
    return project


# ---------------------------------------------------------------------------
# Additional session-store helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_session_db(tmp_path: Path) -> Path:
    """Return a path for a session database (not yet initialised)."""
    return tmp_path / f"test_sessions-{uuid.uuid4().hex[:8]}.db"


@pytest.fixture
def async_store(temp_session_db: Path):
    """Session store initialised from *temp_session_db*."""
    from pyharness.core.session import SessionStore

    s = SessionStore(temp_session_db)
    s.initialize()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Mock LLM provider fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_provider() -> type[FakeLLMProvider]:
    """Return the FakeLLMProvider *class* so tests can instantiate with
    custom scripts."""
    return FakeLLMProvider


@pytest.fixture
def echo_provider() -> FakeLLMProvider:
    """Return a pre-configured echo provider that always returns
    ``"Test response"``."""
    return make_echo_provider("Test response")
