"""Skill discovery — finds and loads SKILL.md files.

Searches global and project directories:

- ``~/.config/pyharness/skills/**/SKILL.md`` (global)
- ``~/.agents/skills/**/SKILL.md`` (global, Claude Code compatible)
- ``~/.claude/skills/**/SKILL.md`` (global, Claude Code compatible)
- ``.pyharness/skills/**/SKILL.md`` (project)
- ``.agents/skills/**/SKILL.md`` (project, Claude Code compatible)
- ``.claude/skills/**/SKILL.md`` (project, Claude Code compatible)

Skills use YAML frontmatter (same format as OpenCode skills):

.. code-block:: markdown

    ---
    name: my-skill
    description: A clear description of what this skill does
    ---
    <skill instructions>
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Search directories — global first, then project-local
# ---------------------------------------------------------------------------

SKILL_SEARCH_DIRS: list[Path] = [
    Path.home() / ".config" / "pyharness" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.cwd() / ".pyharness" / "skills",
    Path.cwd() / ".agents" / "skills",
    Path.cwd() / ".claude" / "skills",
]


def discover_skills() -> list[dict]:
    """Discover all SKILL.md files and return skill metadata.

    Returns:
        List of dicts with keys ``name``, ``description``, ``path``,
        and ``compatibility``, one per discovered ``SKILL.md`` file.
    """
    skills: list[dict] = []
    for d in SKILL_SEARCH_DIRS:
        if d.exists():
            for skill_dir in d.iterdir():
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        try:
                            meta = _parse_skill_frontmatter(skill_md)
                            skills.append(meta)
                        except Exception:
                            continue
    return skills


def discover_skill_paths() -> list[Path]:
    """Discover all SKILL.md file paths (backward-compatible).

    Returns:
        List of paths to ``SKILL.md`` files found across all search
        directories.
    """
    skills: list[Path] = []
    for d in SKILL_SEARCH_DIRS:
        if d.exists():
            for skill_dir in d.iterdir():
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        skills.append(skill_md)
    return sorted(skills)


def _parse_skill_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a SKILL.md file.

    Args:
        path: Path to a ``SKILL.md`` file.

    Returns:
        Dict with ``name``, ``description``, ``path``, and
        ``compatibility`` keys extracted from the frontmatter.
    """
    content = path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml

            try:
                fm = yaml.safe_load(parts[1])
            except Exception:
                fm = {}
            return {
                "name": fm.get("name", path.parent.name),
                "description": fm.get("description", ""),
                "path": str(path),
                "compatibility": fm.get("compatibility", ""),
            }
    return {
        "name": path.parent.name,
        "description": "",
        "path": str(path),
    }
