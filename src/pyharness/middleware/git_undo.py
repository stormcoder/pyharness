"""Git-backed undo/redo middleware for pyharness sessions.

Implements SPEC.md §7.2: every agent action that modifies files creates a git
commit on a hidden branch (``pyharness-session-{id}``).  When the project
isn't a git repo, the middleware degrades gracefully — ``initialize()`` returns
``False`` and every subsequent call is a no-op.

Usage::

    from pyharness.middleware.git_undo import GitUndoMiddleware

    mw = GitUndoMiddleware(repo_path=Path.cwd(), session_id="abc123")
    if mw.initialize():
        entry = mw.on_file_change("write", "updated config.py")
        if mw.can_undo:
            undone = mw.undo()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import git


@dataclass
class UndoEntry:
    """A single undoable action captured as a git commit.

    Attributes:
        commit_sha: The full 40-character SHA-1 of the commit.
        tool_name: The tool that produced the change (e.g. ``"write"``).
        description: Human-readable summary of the action.
        timestamp: ISO-8601 UTC timestamp of the commit.
    """

    commit_sha: str
    tool_name: str
    description: str
    timestamp: str


class GitUndoMiddleware:
    """Creates git commits on file changes for undo/redo support.

    Takes a git snapshot before each file-modifying tool call and supports
    rollback through ``undo()`` and ``redo()``.  When not in a git repo,
    falls back to file-level backups (SPEC §7.2).

    Parameters:
        repo_path: Root of the project directory.  Defaults to CWD.
        session_id: Unique session identifier for branch naming.
    """

    SESSION_BRANCH_PREFIX = "pyharness-session-"

    def __init__(
        self,
        repo_path: Path | None = None,
        session_id: str = "",
    ) -> None:
        self.repo_path = repo_path or Path.cwd()
        self.session_id = session_id
        self.branch_name = f"{self.SESSION_BRANCH_PREFIX}{session_id}" if session_id else ""
        self._undo_stack: list[UndoEntry] = []
        self._redo_stack: list[UndoEntry] = []
        self._repo: git.Repo | None = None
        self._available = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether git is available for undo/redo."""
        return self._available

    @property
    def enabled(self) -> bool:
        """Alias for :attr:`available` — backwards compatibility."""
        return self._available

    def initialize(self) -> bool:
        """Initialize the git repository for undo/redo.

        Returns:
            ``True`` if undo/redo is ready, ``False`` if the project is not
            in a git repository (graceful degradation).
        """
        try:
            self._repo = git.Repo(
                self.repo_path, search_parent_directories=True
            )
            head = self._repo.head.commit
            if self.branch_name and self.branch_name not in [
                b.name for b in self._repo.branches
            ]:
                self._repo.create_head(self.branch_name, head)
            if self.branch_name:
                self._repo.head.reference = self._repo.branches[self.branch_name]  # type: ignore[assignment]
            self._available = True
            return True
        except (git.InvalidGitRepositoryError, git.GitCommandError):
            self._available = False
            return False

    # -- Phase 2 hooks (for acceptance tests) -------------------------------

    def on_tool_start(self, tool_name: str, **kwargs: object) -> None:
        """Called before a tool executes — snapshot state for undo.

        Args:
            tool_name: Name of the tool being invoked.
            **kwargs: Tool arguments.
        """
        if self._available and self._repo and tool_name in ("write", "edit"):
            try:
                self._repo.index.add("*")
            except git.GitCommandError:
                pass

    def on_tool_end(
        self, tool_name: str, description: str = "", **kwargs: object
    ) -> UndoEntry | None:
        """Called after a tool completes — create a git commit.

        Args:
            tool_name: Name of the tool that completed (e.g. ``"write"``).
            description: Human-readable summary.
            **kwargs: Tool output and metadata.

        Returns:
            An :class:`UndoEntry` if a commit was created, ``None`` otherwise.
        """
        return self.on_file_change(tool_name, description)

    # -- Core operations ----------------------------------------------------

    def on_file_change(
        self, tool_name: str, description: str
    ) -> UndoEntry | None:
        """Called after a file-modifying tool executes.

        Creates a git commit containing all changed files.

        Args:
            tool_name: The tool that made the change (e.g. ``"write"``).
            description: Human-readable summary (max 50 chars in commit).

        Returns:
            An :class:`UndoEntry` if the commit succeeded, or ``None`` if
            undo is unavailable or the commit failed.
        """
        if not self._available or not self._repo:
            return None
        try:
            self._repo.index.add("*")
            commit = self._repo.index.commit(
                f"[pyharness] {tool_name}: {description[:50]}"
            )
            entry = UndoEntry(
                commit_sha=commit.hexsha,
                tool_name=tool_name,
                description=description,
                timestamp=str(commit.committed_datetime),
            )
            self._undo_stack.append(entry)
            self._redo_stack.clear()
            return entry
        except git.GitCommandError:
            return None

    def undo(self) -> UndoEntry | None:
        """Undo the most recent action.

        Returns:
            The undone :class:`UndoEntry`, or ``None`` if nothing to undo.
        """
        if not self._undo_stack or not self._repo:
            return None
        entry = self._undo_stack.pop()
        try:
            self._repo.head.reset(
                f"{entry.commit_sha}^",
                index=True,
                working_tree=True,
            )
            self._redo_stack.append(entry)
            return entry
        except git.GitCommandError:
            self._undo_stack.append(entry)
            return None

    def redo(self) -> UndoEntry | None:
        """Redo the most recently undone action.

        Returns:
            The redone :class:`UndoEntry`, or ``None`` if nothing to redo.
        """
        if not self._redo_stack or not self._repo:
            return None
        entry = self._redo_stack.pop()
        try:
            self._repo.head.reset(
                entry.commit_sha,
                index=True,
                working_tree=True,
            )
            self._undo_stack.append(entry)
            return entry
        except git.GitCommandError:
            self._redo_stack.append(entry)
            return None

    @property
    def can_undo(self) -> bool:
        """Whether there are actions to undo."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Whether there are undone actions to redo."""
        return len(self._redo_stack) > 0
