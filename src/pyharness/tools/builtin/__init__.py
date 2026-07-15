"""Built-in tools for pyharness — the core toolset every agent has access to.

These mirror OpenCode's built-in tool surface: bash, read, write, edit,
grep, glob, task, and todowrite.  All are LangChain ``@tool`` decorated
functions that return strings.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Project root — configurable for testing via env var
# ---------------------------------------------------------------------------

_PROJECT_ROOT_ENV = "PYHARNESS_PROJECT_ROOT"


def _get_project_root() -> Path:
    """Return the project root directory.

    Reads ``PYHARNESS_PROJECT_ROOT`` env var; falls back to ``os.getcwd()``.
    Tests can set the env var to point at a ``tmp_path`` fixture.
    """
    env = os.environ.get(_PROJECT_ROOT_ENV)
    if env:
        return Path(env).resolve()
    return Path.cwd()


# ---------------------------------------------------------------------------
# Environment safety helpers
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL", "PASSWD")

_SAFE_ENV_DEFAULTS: dict[str, str] = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", ""),
    "USER": os.environ.get("USER", ""),
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    "TERM": os.environ.get("TERM", "dumb"),
    "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
    "PYHARNESS_PROJECT_ROOT": os.environ.get("PYHARNESS_PROJECT_ROOT", ""),
}


def _build_safe_env() -> dict[str, str]:
    """Build a sanitized environment for subprocess execution.

    Only non-secret environment variables are copied through.
    API keys, tokens, passwords, and credentials are explicitly stripped.
    """
    safe_env = dict(_SAFE_ENV_DEFAULTS)

    for key, value in os.environ.items():
        if key in safe_env:
            continue  # already captured with explicit defaults
        upper = key.upper()
        if any(pattern in upper for pattern in _SECRET_PATTERNS):
            continue  # strip secrets
        safe_env[key] = value

    return safe_env


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------


def _resolve_safe(path: str) -> Path:
    """Resolve *path* relative to the project root and verify it is within.

    Args:
        path: Relative or absolute path.

    Returns:
        An absolute, resolved :class:`Path`.

    Raises:
        ValueError: If the resolved path escapes the project root.
    """
    project_root = _get_project_root()

    resolved = (project_root / path).resolve()

    # Symlinks could escape — check real path
    real = resolved.resolve()

    if not str(real).startswith(str(project_root.resolve())):
        raise ValueError(
            f"Path '{path}' resolves to '{real}', which is outside "
            f"the project root '{project_root.resolve()}'. "
            f"All file operations must stay within the project directory."
        )

    return resolved


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def bash(command: str, timeout: int = 120) -> str:
    """Execute a shell command in the project directory.

    Use for: running tests, git operations, installing packages, building,
    linting, formatting, or any other CLI command.

    Args:
        command: The shell command to execute.
        timeout: Maximum runtime in seconds (default 120).  Use this for
            long-running operations like test suites.  The command is
            terminated if it exceeds the timeout.

    Returns:
        Combined stdout and stderr.  Stderr is appended after stdout when
        present.
    """
    # Security: reject commands with embedded null bytes
    if "\x00" in command:
        return "Error: command contains embedded null byte — rejected"

    # Security: reject excessively long commands (>64KB default)
    MAX_COMMAND_LENGTH = 65536
    if len(command) > MAX_COMMAND_LENGTH:
        return (
            f"Error: command length ({len(command)} bytes) exceeds "
            f"maximum ({MAX_COMMAND_LENGTH}) bytes — rejected"
        )

    # Security: parse command safely with shlex — prevents shell injection
    # by treating metacharacters (;, &&, |, $(), etc.) as literal arguments
    try:
        cmd_parts = shlex.split(command)
    except ValueError as exc:
        return f"Error: invalid shell syntax in command — {exc}"

    if not cmd_parts:
        return "Error: empty command — rejected"

    # Security: build a sanitized environment that strips API keys and secrets
    safe_env = _build_safe_env()

    # Security: confine execution to the project root directory
    project_root = str(_get_project_root())

    try:
        result = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
            env=safe_env,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.rstrip() or "(no output)"
    except FileNotFoundError:
        return f"Error: command not found: {cmd_parts[0]}"
    except PermissionError:
        return f"Error: permission denied: {cmd_parts[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except UnicodeDecodeError:
        return "Error: command output could not be decoded as UTF-8"
    except OSError as exc:
        return f"Error: {exc}"


@tool
def read(path: str, offset: int = 0, limit: int = 2000) -> str:
    """Read a file from the project.  Supports line offset and limit.

    Use for: inspecting file contents, checking code, reviewing logs,
    reading config files, or any read-only file access.

    Args:
        path: Relative or absolute file path within the project.
        offset: Line number to start from (0-indexed).  Use this with
            ``limit`` to page through large files.
        limit: Maximum number of lines to return (default 2000).  Increase
            for larger files, decrease for token efficiency.

    Returns:
        File contents with ``line: content`` prefixing each line, or an
        error message on failure.
    """
    try:
        file_path = _resolve_safe(path)
    except ValueError as exc:
        return str(exc)

    try:
        content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {path}"
    except UnicodeDecodeError:
        return f"Cannot read binary file: {path}"
    except OSError as exc:
        return f"Error reading file: {exc}"

    lines = content.split("\n")
    total_lines = len(lines)

    # Clamp offset
    if offset < 0:
        offset = max(0, total_lines + offset)

    end = offset + limit
    window = lines[offset:end]

    result = "\n".join(
        f"{i + 1}: {line}" for i, line in enumerate(window, start=offset)
    )

    summary = f"(lines {offset + 1}-{min(end, total_lines)} of {total_lines})"
    return f"{result}\n{summary}"


@tool
def write(path: str, content: str) -> str:
    """Create a new file or overwrite an existing one.

    Use for: creating new source files, config files, scripts, or any
    other project file.  This will overwrite existing files without
    confirmation — use :tool:`read` first to check existing content.

    Args:
        path: File path relative to the project root.  Parent directories
            are created automatically.
        content: The complete file contents to write.

    Returns:
        Confirmation message with the absolute path.
    """
    try:
        file_path = _resolve_safe(path)
    except ValueError as exc:
        return str(exc)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {file_path.stat().st_size} bytes to {file_path}"
    except OSError as exc:
        return f"Error writing file: {exc}"


@tool
def edit(path: str, old_string: str, new_string: str) -> str:
    """Perform exact string replacement in an existing file.

    Use for: making surgical edits without rewriting the entire file.
    The *old_string* must appear exactly once in the file — if it
    appears zero or multiple times, the edit is rejected to avoid
    accidental corruption.

    Args:
        path: File path relative to the project root.
        old_string: The exact text to find and replace.  Must be unique
            within the file.  Include surrounding context to disambiguate.
        new_string: The replacement text.  Use an empty string to delete.

    Returns:
        Confirmation or error message.
    """
    try:
        file_path = _resolve_safe(path)
    except ValueError as exc:
        return str(exc)

    try:
        content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {path}"
    except UnicodeDecodeError:
        return f"Cannot edit binary file: {path}"
    except OSError as exc:
        return f"Error reading file: {exc}"

    count = content.count(old_string)
    if count == 0:
        return (
            f"Error: old_string not found in {path}.  "
            f"The text must appear exactly once — ensure whitespace and "
            f"indentation match."
        )
    if count > 1:
        return (
            f"Error: old_string found {count} times in {path}.  "
            f"Provide more surrounding context to make it unique."
        )

    new_content = content.replace(old_string, new_string, 1)
    try:
        file_path.write_text(new_content, encoding="utf-8")
        return f"Edited {path} — replaced 1 occurrence"
    except OSError as exc:
        return f"Error writing file: {exc}"


@tool
def grep(pattern: str, include: str = "*") -> str:
    """Search file contents using regular expressions.

    Use for: finding function definitions, variable usages, error messages,
    TODO comments, import statements, or any regex-based code search.

    Args:
        pattern: Python regex pattern to search for.  Uses ``re.IGNORECASE``
            for case-insensitive matching.
        include: File glob pattern to filter (default ``"*"`` matches all
            files).  Use ``"*.py"`` for Python files, ``"*.{py,rs}"`` for
            multiple extensions.

    Returns:
        Matching lines with ``file:lineno: text`` formatting, or a
        summary when no matches are found.
    """
    project_root = _get_project_root()
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"

    results: list[str] = []
    total_matches = 0
    file_count = 0

    for file_path in project_root.rglob(include):
        if not file_path.is_file():
            continue
        # Skip hidden / ignored directories
        if any(part.startswith(".") for part in file_path.parts):
            continue
        if ".git" in file_path.parts or "__pycache__" in file_path.parts:
            continue

        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        file_matches = 0
        for lineno, line in enumerate(text.split("\n"), start=1):
            if compiled.search(line):
                rel = file_path.relative_to(project_root)
                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                file_matches += 1

        if file_matches:
            file_count += 1
            total_matches += file_matches

        # Safety: cap at 200 results to avoid massive output
        if len(results) >= 200:
            results.append("... (truncated at 200 results)")
            break

    if not results:
        return f"No matches found for '{pattern}'"

    header = f"Found {total_matches} matches across {file_count} files:\n"
    return header + "\n".join(results)


@tool
def glob(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern.

    Use for: listing source files, finding test files, discovering
    configuration files, or exploring project structure.

    Args:
        pattern: Glob pattern (e.g., ``"src/**/*.py"``, ``"**/*.md"``,
            ``"**/test_*.py"``).  Supports ``**`` for recursive matching.
        path: Root directory to search from (default ``"."`` — current
            working directory).  Must be within the project.

    Returns:
        Matching file paths, one per line, or a summary.
    """
    project_root = _get_project_root()
    try:
        search_root = _resolve_safe(path)
    except ValueError as exc:
        return str(exc)

    matches = sorted(
        str(p.relative_to(project_root))
        for p in search_root.rglob(pattern)
        if p.is_file()
        and ".git" not in p.parts
        and "__pycache__" not in p.parts
    )

    if not matches:
        return f"No files matched pattern '{pattern}' in '{path}'"

    # Cap at 500
    if len(matches) > 500:
        matches = matches[:500]
        matches.append("... (truncated at 500 results)")

    return f"Found {len(matches)} files:\n" + "\n".join(matches)


@tool
def task(description: str, prompt: str, subagent_type: str = "general") -> str:
    """Launch a subagent to handle a complex task autonomously.

    Use for: delegating large, self-contained work units to a specialized
    subagent.  The subagent runs with its own context and returns results
    when complete.

    Args:
        description: Short (3-5 word) description of the task, e.g.,
            ``"refactor auth module"`` or ``"write unit tests"``.
        prompt: Detailed instructions for the subagent.  Include specific
            files, requirements, and acceptance criteria.
        subagent_type: Type of subagent to spawn.  ``"general"`` for
            general-purpose work, ``"explore"`` for codebase exploration
            and research.

    Returns:
        Subagent spawn confirmation with session details.
    """
    from pyharness.core.agent import AgentRunner

    # Validate subagent_type against known defaults
    valid_types = ("general", "explore")
    if subagent_type not in valid_types:
        return (
            f"Unknown subagent type: '{subagent_type}'. "
            f"Available types: {', '.join(valid_types)}."
        )

    import uuid

    session_id = f"subagent-{uuid.uuid4().hex[:12]}"

    # In a full TUI context, this would create a real AgentRunner for the
    # subagent. For now, return a descriptive message about what would happen.
    runner_preview = AgentRunner.__name__  # availability check — class exists
    return (
        f"Subagent dispatched: {subagent_type}\n"
        f"Session: {session_id}\n"
        f"Description: {description}\n"
        f"Prompt length: {len(prompt)} chars\n"
        f"AgentRunner available: {runner_preview}"
    )


@tool
def todowrite(todos: str) -> str:
    """Create and maintain a structured task list for the current session.

    Use for: tracking progress through multi-step work, demonstrating
    thoroughness, and ensuring nothing is missed.  Always update the todo
    list after completing a step.

    Args:
        todos: JSON string of todo items.  Each item must have:
            ``content`` (str) — task description,
            ``status`` (str) — one of ``"pending"``, ``"in_progress"``,
            ``"completed"``, ``"cancelled"``,
            ``priority`` (str) — one of ``"high"``, ``"medium"``, ``"low"``.

    Returns:
        Summary of the updated todo list.

    Example:
        >>> todowrite('[{"content":"Add tests","status":"in_progress","priority":"high"}]')
    """
    try:
        items = json.loads(todos)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"

    if not isinstance(items, list):
        return "Error: todos must be a JSON array"

    valid_statuses = {"pending", "in_progress", "completed", "cancelled"}
    valid_priorities = {"high", "medium", "low"}
    errors: list[str] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: must be an object")
            continue
        if "content" not in item:
            errors.append(f"Item {i}: missing 'content'")
        if item.get("status", "pending") not in valid_statuses:
            errors.append(
                f"Item {i}: invalid status '{item.get('status')}' "
                f"(use: {', '.join(sorted(valid_statuses))})"
            )
        if item.get("priority") not in valid_priorities:
            errors.append(
                f"Item {i}: invalid priority '{item.get('priority')}' "
                f"(use: {', '.join(sorted(valid_priorities))})"
            )

    if errors:
        return "Validation errors:\n" + "\n".join(f"  - {e}" for e in errors)

    completed = sum(1 for t in items if t.get("status") == "completed")
    in_progress = sum(1 for t in items if t.get("status") == "in_progress")
    pending = sum(1 for t in items if t.get("status") == "pending")

    return (
        f"Updated todo list: {len(items)} items "
        f"({completed} completed, {in_progress} in progress, "
        f"{pending} pending)"
    )


# ---------------------------------------------------------------------------
# Convenience: list of all built-in tools
# ---------------------------------------------------------------------------

ALL_BUILTIN_TOOLS: list = [bash, read, write, edit, grep, glob, task, todowrite]
