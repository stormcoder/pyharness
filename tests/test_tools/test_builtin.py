"""Tests for the built-in pyharness tools."""

from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _set_project_root(path: Path) -> None:
    """Set PYHARNESS_PROJECT_ROOT env var so tools operate within *path*."""
    os.environ["PYHARNESS_PROJECT_ROOT"] = str(path)


def _clear_project_root() -> None:
    """Remove the project root env override."""
    os.environ.pop("PYHARNESS_PROJECT_ROOT", None)


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_file(tmp_path: Path):
    """read returns file contents with line numbers."""
    from pyharness.tools.builtin import read

    f = tmp_path / "hello.txt"
    f.write_text("line one\nline two\nline three")  # no trailing newline
    _set_project_root(tmp_path)

    result = read.invoke({"path": str(f), "offset": 0, "limit": 50})
    _clear_project_root()

    assert "1: line one" in result
    assert "2: line two" in result
    assert "3: line three" in result
    assert "lines 1-3 of 3" in result


def test_read_with_offset_and_limit(tmp_path: Path):
    """read respects offset and limit parameters."""
    from pyharness.tools.builtin import read

    f = tmp_path / "nums.txt"
    f.write_text("\n".join(str(i) for i in range(20)) + "\n")
    _set_project_root(tmp_path)

    result = read.invoke({"path": str(f), "offset": 5, "limit": 3})
    _clear_project_root()

    assert "6: 5" in result
    assert "7: 6" in result
    assert "8: 7" in result
    assert "9: " not in result  # should stop at offset+limit


def test_read_missing_file(tmp_path: Path):
    """read returns an error for non-existent files."""
    from pyharness.tools.builtin import read

    _set_project_root(tmp_path)
    result = read.invoke({"path": "nonexistent.txt"})
    _clear_project_root()

    assert "File not found" in result


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


def test_write_creates_file(tmp_path: Path):
    """write creates a new file and returns a confirmation."""
    from pyharness.tools.builtin import write

    _set_project_root(tmp_path)
    f = tmp_path / "new_file.py"
    result = write.invoke({"path": str(f), "content": "print('hello')"})
    _clear_project_root()

    assert "Wrote" in result
    assert f.read_text() == "print('hello')"


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


def test_edit_replaces_text(tmp_path: Path):
    """edit replaces exactly one occurrence of old_string."""
    from pyharness.tools.builtin import edit

    f = tmp_path / "script.py"
    f.write_text("foo = 1\nbar = 2\nbaz = 3\n")
    _set_project_root(tmp_path)

    result = edit.invoke(
        {"path": str(f), "old_string": "bar = 2", "new_string": "bar = 42"}
    )
    _clear_project_root()

    assert "replaced 1 occurrence" in result
    assert f.read_text() == "foo = 1\nbar = 42\nbaz = 3\n"


def test_edit_old_string_not_found(tmp_path: Path):
    """edit returns an error when old_string does not exist."""
    from pyharness.tools.builtin import edit

    f = tmp_path / "data.txt"
    f.write_text("hello world\n")
    _set_project_root(tmp_path)

    result = edit.invoke(
        {"path": str(f), "old_string": "nope", "new_string": "yes"}
    )
    _clear_project_root()

    assert "not found" in result.lower()


def test_edit_multiple_matches(tmp_path: Path):
    """edit returns an error when old_string appears more than once."""
    from pyharness.tools.builtin import edit

    f = tmp_path / "dups.txt"
    f.write_text("alpha\nalpha\n")
    _set_project_root(tmp_path)

    result = edit.invoke(
        {"path": str(f), "old_string": "alpha", "new_string": "beta"}
    )
    _clear_project_root()

    assert "found" in result.lower() and "times" in result.lower()


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


def test_grep_finds_matches(tmp_path: Path):
    """grep returns matching lines with file:line formatting."""
    from pyharness.tools.builtin import grep

    (tmp_path / "a.py").write_text("import os\nimport sys\ndef main(): pass\n")
    (tmp_path / "b.py").write_text("print('no match here')\n")
    _set_project_root(tmp_path)

    result = grep.invoke({"pattern": r"import\s+\w+", "include": "*.py"})
    _clear_project_root()

    assert "import os" in result
    assert "import sys" in result
    assert "Found" in result


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------


def test_glob_finds_files(tmp_path: Path):
    """glob returns matching file paths."""
    from pyharness.tools.builtin import glob

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# main")
    (tmp_path / "src" / "utils.py").write_text("# utils")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("# test")
    _set_project_root(tmp_path)

    result = glob.invoke({"pattern": "**/*.py", "path": "."})
    _clear_project_root()

    assert "main.py" in result
    assert "utils.py" in result
    assert "test_main.py" in result
    assert "Found" in result


# ---------------------------------------------------------------------------
# bash
# ---------------------------------------------------------------------------


def test_bash_executes_command():
    """bash runs a simple command and returns its output."""
    from pyharness.tools.builtin import bash

    result = bash.invoke({"command": "echo hello from bash", "timeout": 10})
    assert "hello from bash" in result


def test_bash_captures_stderr():
    """bash includes stderr in the output."""
    from pyharness.tools.builtin import bash

    # Use shlex-compatible quoting: single-quoted Python code preserves
    # inner double-quotes and semicolons correctly.
    result = bash.invoke(
        {
            "command": (
                'python -c '
                '"import sys; print(\'stdout\'); print(\'stderr\', file=sys.stderr)"'
            ),
            "timeout": 10,
        }
    )
    assert "stdout" in result
    assert "stderr" in result


def test_bash_rejects_shell_injection():
    """Shell metacharacters are treated as literal arguments, not interpreted.

    With shell=False, ``echo hello; rm -rf .`` must NOT execute the
    ``rm`` command — the semicolon is passed as a literal character to
    ``echo`` rather than being interpreted as a command separator.
    """
    from pyharness.tools.builtin import bash

    command = "echo hello; rm -rf ."
    result = bash.invoke({"command": command, "timeout": 10})

    # The output should contain the literal string "; rm -rf ." that was
    # echoed, NOT any evidence of rm actually executing
    assert "hello" in result
    # The semicolon and rm text should appear as literal arguments echoed
    # by the echo command
    assert "; rm -rf" in result or "hello; rm -rf" in result


def test_bash_uses_safe_environment():
    """API keys must not be present in the subprocess environment.

    Sets a fake API key in os.environ and verifies that a bash command
    that echoes env vars cannot access it.
    """
    import os

    from pyharness.tools.builtin import bash

    os.environ["PYHARNESS_FAKE_API_KEY"] = "sk-test-should-not-appear"
    os.environ["PYHARNESS_FAKE_TOKEN"] = "tk-should-be-stripped"
    os.environ["PYHARNESS_FAKE_SECRET"] = "sec-leaked-if-visible"

    try:
        # Try reading the fake secret via env
        result = bash.invoke(
            {"command": "echo $PYHARNESS_FAKE_API_KEY", "timeout": 10}
        )
        assert "sk-test-should-not-appear" not in result, (
            f"API key leaked into subprocess environment! Output: {result!r}"
        )

        result2 = bash.invoke(
            {"command": "echo $PYHARNESS_FAKE_TOKEN", "timeout": 10}
        )
        assert "tk-should-be-stripped" not in result2

        result3 = bash.invoke(
            {"command": "echo $PYHARNESS_FAKE_SECRET", "timeout": 10}
        )
        assert "sec-leaked-if-visible" not in result3
    finally:
        os.environ.pop("PYHARNESS_FAKE_API_KEY", None)
        os.environ.pop("PYHARNESS_FAKE_TOKEN", None)
        os.environ.pop("PYHARNESS_FAKE_SECRET", None)


def test_bash_is_confined_to_project_root(tmp_path: Path):
    """bash commands run in the project root, not the process cwd."""
    from pyharness.tools.builtin import bash

    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "sentinel.txt").write_text("i am here")

    _set_project_root(project_dir)

    try:
        # pwd should show the project root
        result = bash.invoke({"command": "pwd", "timeout": 10})
        _clear_project_root()
        assert str(project_dir) in result or project_dir.name in result
    except AssertionError:
        _clear_project_root()
        raise


# ---------------------------------------------------------------------------
# todowrite
# ---------------------------------------------------------------------------


def test_todowrite_valid_todos():
    """todowrite accepts a valid JSON todo list."""
    from pyharness.tools.builtin import todowrite

    todos = json.dumps(
        [
            {"content": "Add tests", "status": "completed", "priority": "high"},
            {"content": "Write docs", "status": "in_progress", "priority": "medium"},
            {"content": "Deploy", "status": "pending", "priority": "high"},
        ]
    )
    result = todowrite.invoke({"todos": todos})
    assert "3 items" in result
    assert "1 completed" in result
    assert "1 in progress" in result
    assert "1 pending" in result


def test_todowrite_invalid_json():
    """todowrite returns an error for invalid JSON."""
    from pyharness.tools.builtin import todowrite

    result = todowrite.invoke({"todos": "not json"})
    assert "Invalid JSON" in result


# ---------------------------------------------------------------------------
# task
# ---------------------------------------------------------------------------


def test_task_stub():
    """task returns subagent dispatch confirmation."""
    from pyharness.tools.builtin import task

    result = task.invoke(
        {"description": "refactor module", "prompt": "Clean up auth.py"}
    )
    assert "Subagent dispatched" in result
    assert "refactor module" in result


def test_task_rejects_unknown_subagent_type():
    """task rejects unknown subagent types."""
    from pyharness.tools.builtin import task

    result = task.invoke(
        {
            "description": "test",
            "prompt": "test",
            "subagent_type": "nonexistent",
        }
    )
    assert "Unknown subagent type" in result


# ---------------------------------------------------------------------------
# path safety
# ---------------------------------------------------------------------------


def test_path_safety_prevents_escape(tmp_path: Path):
    """File tools reject paths that escape the project root."""
    from pyharness.tools.builtin import read

    _set_project_root(tmp_path)
    result = read.invoke({"path": "../../etc/passwd"})
    _clear_project_root()

    assert "outside" in result.lower() or "error" in result.lower()
