"""Shared test fixtures for pyharness."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from pyharness.core.testing import (
    FakeLLMProvider,
    make_echo_provider,
)

# ---------------------------------------------------------------------------
# Session store fixtures (pre-existing)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a unique SQLite database path inside a temp directory."""
    return tmp_path / f"test-{uuid.uuid4().hex[:8]}.db"


@pytest.fixture
async def store(tmp_db_path: Path):
    """Return an initialized SessionStore connected to a temp database."""
    from pyharness.core.session import SessionStore

    s = SessionStore(tmp_db_path)
    await s.initialize()
    try:
        yield s
    finally:
        await s.close()


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
async def async_store(temp_session_db: Path):
    """Async session store initialised from *temp_session_db*."""
    from pyharness.core.session import SessionStore

    s = SessionStore(temp_session_db)
    await s.initialize()
    try:
        yield s
    finally:
        await s.close()


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
