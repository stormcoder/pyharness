"""Tests for git-backed undo/redo middleware.

Covers both happy path (commits created in git repos) and graceful degradation
(when outside a git repo).
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from pyharness.middleware.git_undo import GitUndoMiddleware


class TestGitUndoMiddleware:
    """Core git undo middleware tests."""

    def test_git_undo_available_in_git_repo(self, tmp_path: Path):
        """Initialize succeeds inside a temp git repo."""
        # Create a git repo
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@pyharness.dev"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "pyharness test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        # Create an initial file and commit so HEAD exists
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        sid = str(uuid.uuid4().hex[:8])
        mw = GitUndoMiddleware(repo_path=tmp_path, session_id=sid)
        result = mw.initialize()
        assert result is True
        assert mw.available is True
        assert mw.can_undo is False
        assert mw.can_redo is False

    def test_git_undo_not_available_outside_git(self, tmp_path: Path):
        """Initialize returns False when not in a git repo."""
        sid = str(uuid.uuid4().hex[:8])
        mw = GitUndoMiddleware(repo_path=tmp_path, session_id=sid)
        result = mw.initialize()
        assert result is False
        assert mw.available is False

    def test_git_undo_commit_on_file_change(self, tmp_path: Path):
        """A file change creates a commit and pushes to the undo stack."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@pyharness.dev"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "pyharness test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "initial.txt").write_text("initial")
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        sid = str(uuid.uuid4().hex[:8])
        mw = GitUndoMiddleware(repo_path=tmp_path, session_id=sid)
        assert mw.initialize() is True

        # Simulate a file change
        (tmp_path / "main.py").write_text('print("hello")')
        subprocess.run(
            ["git", "add", "main.py"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        entry = mw.on_file_change("write", "created main.py")
        assert entry is not None
        assert entry.tool_name == "write"
        assert mw.can_undo is True
        assert mw.can_redo is False

    def test_git_undo_noop_on_uninitialized(self, tmp_path: Path):
        """on_file_change returns None when middleware is not initialized."""
        sid = str(uuid.uuid4().hex[:8])
        mw = GitUndoMiddleware(repo_path=tmp_path, session_id=sid)
        # Don't call initialize
        assert mw.on_file_change("write", "test") is None
        assert mw.undo() is None
        assert mw.redo() is None
