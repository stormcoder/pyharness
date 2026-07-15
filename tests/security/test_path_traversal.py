"""Security tests for path traversal attacks against file tools.

Tests that the built-in read, write, and edit tools correctly enforce
the project-root sandbox via ``_resolve_safe()``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyharness.tools.builtin import read, write, edit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_project_root(path: Path) -> None:
    os.environ["PYHARNESS_PROJECT_ROOT"] = str(path)


def _clear_project_root() -> None:
    os.environ.pop("PYHARNESS_PROJECT_ROOT", None)


# ---------------------------------------------------------------------------
# read — Path traversal
# ---------------------------------------------------------------------------


class TestReadPathTraversal:
    """Path traversal attacks against the ``read`` tool."""

    def test_read_rejects_parent_traversal(self):
        """Reading ``../../../etc/passwd`` should be rejected."""
        result = read.invoke({"path": "../../../etc/passwd"})
        rejection_terms = ("rejected", "outside", "error", "not found")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Parent traversal should be rejected, got: {result!r}"
        )

    def test_read_rejects_absolute_etc_passwd(self):
        """Reading ``/etc/passwd`` directly should be rejected."""
        result = read.invoke({"path": "/etc/passwd"})
        rejection_terms = ("rejected", "outside", "error")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Absolute /etc/passwd should be rejected, got: {result!r}"
        )

    def test_read_rejects_double_dot_in_middle(self, tmp_path: Path):
        """``foo/../../etc/passwd`` should be rejected even with nesting."""
        _set_project_root(tmp_path)
        try:
            result = read.invoke({"path": "subdir/../../etc/passwd"})
            rejection_terms = ("rejected", "outside", "error", "not found")
            assert any(term in result.lower() for term in rejection_terms), (
                f"Nested parent traversal should be rejected, got: {result!r}"
            )
        finally:
            _clear_project_root()

    def test_read_rejects_encoded_traversal(self, tmp_path: Path):
        """URL-encoded traversal (``..%2F..%2F``) should be rejected."""
        _set_project_root(tmp_path)
        try:
            result = read.invoke({"path": "..%2F..%2F..%2Fetc%2Fpasswd"})
            rejection_terms = ("rejected", "outside", "error", "not found")
            assert any(term in result.lower() for term in rejection_terms), (
                f"Encoded traversal should be rejected, got: {result!r}"
            )
        finally:
            _clear_project_root()

    def test_read_allows_relative_files(self, tmp_path: Path):
        """Normal relative file reads within the project should succeed."""
        (tmp_path / "data.txt").write_text("hello")
        _set_project_root(tmp_path)
        try:
            result = read.invoke({"path": "data.txt"})
            assert "1: hello" in result
        finally:
            _clear_project_root()


# ---------------------------------------------------------------------------
# write — Path traversal
# ---------------------------------------------------------------------------


class TestWritePathTraversal:
    """Path traversal attacks against the ``write`` tool."""

    def test_write_rejects_absolute_path(self):
        """Writing to ``/etc/hosts`` should be rejected."""
        result = write.invoke({"path": "/etc/hosts", "content": "evil"})
        rejection_terms = ("rejected", "outside", "error")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Absolute path write should be rejected, got: {result!r}"
        )

    def test_write_rejects_parent_traversal(self):
        """Writing to ``../../../tmp/evil`` should be rejected."""
        result = write.invoke({"path": "../../../tmp/evil.sh", "content": "echo pwned"})
        rejection_terms = ("rejected", "outside", "error")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Parent traversal write should be rejected, got: {result!r}"
        )

    def test_write_rejects_symlink_escape(self, tmp_path: Path):
        """Writing through a symlink that points outside should be detected.

        This tests the real-path check in ``_resolve_safe()``.
        """
        _set_project_root(tmp_path)
        try:
            # Create a symlink inside the project pointing outside
            outside = tmp_path.parent / "outside.txt"
            outside.write_text("target")
            symlink = tmp_path / "escape_link"
            os.symlink(str(outside), str(symlink))

            result = write.invoke({"path": str(symlink), "content": "hijacked"})
            # The real-path check should catch this
            rejection_terms = ("rejected", "outside", "error")
            assert any(term in result.lower() for term in rejection_terms), (
                f"Symlink escape should be rejected, got: {result!r}"
            )
        finally:
            _clear_project_root()

    def test_write_allows_relative_paths(self, tmp_path: Path):
        """Normal relative file writes within the project should succeed."""
        _set_project_root(tmp_path)
        try:
            result = write.invoke({"path": "new_file.txt", "content": "safe"})
            assert "Wrote" in result
            assert (tmp_path / "new_file.txt").read_text() == "safe"
        finally:
            _clear_project_root()


# ---------------------------------------------------------------------------
# edit — Path traversal
# ---------------------------------------------------------------------------


class TestEditPathTraversal:
    """Path traversal attacks against the ``edit`` tool."""

    def test_edit_rejects_absolute_path(self):
        """Editing ``/etc/passwd`` should be rejected."""
        result = edit.invoke(
            {"path": "/etc/passwd", "old_string": "root", "new_string": "hacked"}
        )
        rejection_terms = ("rejected", "outside", "error", "not found")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Absolute path edit should be rejected, got: {result!r}"
        )

    def test_edit_rejects_parent_traversal(self):
        """Editing ``../../../etc/passwd`` should be rejected."""
        result = edit.invoke(
            {
                "path": "../../../etc/passwd",
                "old_string": "root",
                "new_string": "hacked",
            }
        )
        rejection_terms = ("rejected", "outside", "error", "not found")
        assert any(term in result.lower() for term in rejection_terms), (
            f"Parent traversal edit should be rejected, got: {result!r}"
        )

    def test_edit_allows_relative_paths(self, tmp_path: Path):
        """Normal relative file edits within the project should succeed."""
        (tmp_path / "config.txt").write_text("debug = true\n")
        _set_project_root(tmp_path)
        try:
            result = edit.invoke(
                {
                    "path": "config.txt",
                    "old_string": "debug = true",
                    "new_string": "debug = false",
                }
            )
            assert "replaced 1 occurrence" in result
            assert (tmp_path / "config.txt").read_text() == "debug = false\n"
        finally:
            _clear_project_root()


# ---------------------------------------------------------------------------
# Symlink edge cases
# ---------------------------------------------------------------------------


class TestSymlinkEdgeCases:
    """Additional symlink-based attack vectors."""

    def test_read_symlink_chain(self, tmp_path: Path):
        """A chain of symlinks that eventually points outside should be caught."""
        _set_project_root(tmp_path)
        try:
            outside = tmp_path.parent / "secret.txt"
            outside.write_text("SECRET")

            # Chain: link1 → link2 → outside
            link2 = tmp_path / "link2"
            os.symlink(str(outside), str(link2))
            link1 = tmp_path / "link1"
            os.symlink(str(link2), str(link1))

            result = read.invoke({"path": str(link1)})
            rejection_terms = ("rejected", "outside", "error")
            # resolve() follows all symlinks, so this should be caught
            assert any(term in result.lower() for term in rejection_terms), (
                f"Symlink chain should be rejected, got: {result!r}"
            )
        finally:
            _clear_project_root()
