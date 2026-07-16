"""Load custom agents from markdown files and AGENTS.md.

Discovers agent definitions from:
- ``~/.config/pyharness/agents/*.md`` (global)
- ``~/.agents/*.md`` (global, Claude Code compatible)
- ``~/.claude/agents/*.md`` (global, Claude Code compatible)
- ``.pyharness/agents/*.md`` (project)
- ``.agents/*.md`` (project, Claude Code compatible)
- ``.claude/agents/*.md`` (project, Claude Code compatible)
- ``AGENTS.md`` in project root (special — detected but not parsed as agent)

Each ``*.md`` file uses YAML frontmatter format (same as OpenCode/Claude Code):

.. code-block:: markdown

    ---
    description: My custom agent
    mode: subagent
    model: anthropic:claude-sonnet-4-5
    color: "#58a6ff"
    ---
    You are a custom agent that...
"""

from __future__ import annotations

from pathlib import Path

from pyharness.config.schema import AgentDefinition

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_agents_from_directory(agents_dir: Path) -> dict[str, AgentDefinition]:
    """Load agent definitions from markdown files in a directory.

    Scans ``*.md`` files with YAML frontmatter and parses them into
    :class:`~pyharness.config.schema.AgentDefinition` instances.

    Args:
        agents_dir: Path to a directory containing agent ``*.md`` files.

    Returns:
        Mapping of ``{name: AgentDefinition}`` for all parsed agents.
    """
    agents: dict[str, AgentDefinition] = {}
    if not agents_dir.exists():
        return agents

    for md_file in sorted(agents_dir.glob("*.md")):
        try:
            agent = _parse_agent_markdown(md_file)
            if agent:
                name = md_file.stem
                agents[name] = agent
        except Exception:
            continue

    return agents


def discover_agent_directories(project_root: Path) -> list[Path]:
    """Find all agent directories (global + project).

    Searches in priority order — project dirs override global dirs
    with the same agent name in the loader merge step.

    Args:
        project_root: Root directory of the current project.

    Returns:
        List of existing directory paths to scan for agent markdown files.
    """
    dirs: list[Path] = []
    home = Path.home()

    # Global directories (lowest priority)
    for d in [
        home / ".config" / "pyharness" / "agents",
        home / ".agents",
        home / ".claude" / "agents",  # Claude Code compatibility
    ]:
        if d.exists():
            dirs.append(d)

    # Project directories (highest priority)
    for d in [
        project_root / ".pyharness" / "agents",
        project_root / ".agents",
        project_root / ".claude" / "agents",  # Claude Code compatibility
    ]:
        if d.exists():
            dirs.append(d)

    return dirs


def detect_agents_md(project_root: Path) -> Path | None:
    """Check if AGENTS.md exists in project root.

    Args:
        project_root: Root directory of the current project.

    Returns:
        Path to ``AGENTS.md`` if it exists, otherwise ``None``.
    """
    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        return agents_md
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML or JSON frontmatter from a markdown file.

    Tries ``yaml`` first (if installed), falls back to ``json5`` for a
    JSON-compatible subset.
    """
    try:
        import yaml  # type: ignore[import-untyped,unused-ignore]

        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    # Fallback: parse as JSON (YAML subset)
    try:
        import json5

        return json5.loads(text)
    except Exception:
        return {}


def _parse_agent_markdown(path: Path) -> AgentDefinition | None:
    """Parse a markdown agent file with YAML frontmatter.

    File format (same as OpenCode agent definitions)::

        ---
        description: ...
        mode: subagent
        model: anthropic:claude-sonnet-4-5
        temperature: 0.7
        steps: 50
        hidden: false
        color: "#58a6ff"
        ---
        <system prompt body>

    Args:
        path: Path to the markdown agent file.

    Returns:
        :class:`AgentDefinition` or ``None`` if parsing fails.
    """
    content = path.read_text(encoding="utf-8")

    # Extract YAML frontmatter between --- delimiters
    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = _parse_frontmatter(parts[1].strip())
    except Exception:
        frontmatter = {}

    prompt = parts[2].strip()
    if not prompt:
        return None

    return AgentDefinition(
        description=frontmatter.get("description", f"Agent: {path.stem}"),
        mode=frontmatter.get("mode", "subagent"),  # type: ignore[arg-type]
        model=frontmatter.get("model"),
        prompt=prompt,
        temperature=frontmatter.get("temperature"),
        steps=frontmatter.get("steps"),
        hidden=frontmatter.get("hidden", False),
        color=frontmatter.get("color"),
    )
