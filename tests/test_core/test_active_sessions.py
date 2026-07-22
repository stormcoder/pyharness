"""Tests for R1.11-R1.12 — ActiveSessions replaces current pointer with active.json.

Covers ``active_sessions.py``: save, load, add, remove, list_all, and migration
from the legacy ``current`` pointer file.
"""

from __future__ import annotations

import json
import inspect
from pathlib import Path

import pytest

from pyharness.core.active_sessions import ActiveSessions


# =============================================================================
# R1.11 — Save active.json
# =============================================================================


class TestActiveSessionsSave:
    """active.json is written with correct structure."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """save() creates active.json in the sessions directory."""
        sessions_dir = tmp_path / "sessions"
        active = ActiveSessions(sessions_dir)
        active.add("sess-abc", "chat-1")
        active.save()

        assert (sessions_dir / "active.json").exists()

    def test_save_writes_valid_json(self, tmp_path: Path) -> None:
        """save() writes parseable JSON with a 'tabs' key."""
        sessions_dir = tmp_path / "sessions"
        active = ActiveSessions(sessions_dir)
        active.add("sess-abc", "chat-1")
        active.save()

        data = json.loads((sessions_dir / "active.json").read_text())
        assert "tabs" in data
        assert isinstance(data["tabs"], list)
        assert len(data["tabs"]) == 1
        assert data["tabs"][0]["session_id"] == "sess-abc"
        assert data["tabs"][0]["screen_id"] == "chat-1"

    def test_save_multiple_tabs(self, tmp_path: Path) -> None:
        """save() persists all registered tabs."""
        sessions_dir = tmp_path / "sessions"
        active = ActiveSessions(sessions_dir)
        active.add("sess-a", "chat-1")
        active.add("sess-b", "chat-2")
        active.save()

        data = json.loads((sessions_dir / "active.json").read_text())
        assert len(data["tabs"]) == 2

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save() creates parent directories if they don't exist."""
        sessions_dir = tmp_path / "deeply" / "nested" / "sessions"
        active = ActiveSessions(sessions_dir)
        active.save()

        assert (sessions_dir / "active.json").exists()

    def test_save_empty_tabs(self, tmp_path: Path) -> None:
        """save() with no tabs writes an empty tabs list."""
        sessions_dir = tmp_path / "sessions"
        active = ActiveSessions(sessions_dir)
        active.save()

        data = json.loads((sessions_dir / "active.json").read_text())
        assert data["tabs"] == []


# =============================================================================
# R1.12 — Load active.json
# =============================================================================


class TestActiveSessionsLoad:
    """active.json is read back correctly, including migration."""

    def test_load_reads_tabs(self, tmp_path: Path) -> None:
        """load() restores tabs that were previously saved."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "active.json").write_text(
            json.dumps({"tabs": [{"session_id": "sess-x", "screen_id": "chat-3"}]})
        )

        active = ActiveSessions(sessions_dir)
        active.load()

        tabs = active.list_all()
        assert len(tabs) == 1
        assert tabs[0]["session_id"] == "sess-x"
        assert tabs[0]["screen_id"] == "chat-3"

    def test_load_empty_when_no_file(self, tmp_path: Path) -> None:
        """load() with no active.json returns empty tabs."""
        sessions_dir = tmp_path / "nonexistent"
        active = ActiveSessions(sessions_dir)
        active.load()

        assert active.list_all() == []

    def test_load_handles_corrupt_json(self, tmp_path: Path) -> None:
        """load() with corrupt JSON returns empty tabs (no crash)."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "active.json").write_text("not json at all {{{")

        active = ActiveSessions(sessions_dir)
        active.load()

        assert active.list_all() == []

    def test_load_missing_tabs_key(self, tmp_path: Path) -> None:
        """load() with missing 'tabs' key returns empty tabs."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "active.json").write_text('{"other": 42}')

        active = ActiveSessions(sessions_dir)
        active.load()

        assert active.list_all() == []


# =============================================================================
# Migration from legacy 'current' pointer
# =============================================================================


class TestMigrationFromCurrent:
    """Legacy 'current' file is migrated to active.json on first load."""

    def test_migration_creates_active_json(self, tmp_path: Path) -> None:
        """When current exists and active.json does not, load() migrates."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "current").write_text("legacy-session-id\n")

        active = ActiveSessions(sessions_dir)
        active.load()

        # active.json should now exist with the migrated session
        assert (sessions_dir / "active.json").exists()
        tabs = active.list_all()
        assert len(tabs) == 1
        assert tabs[0]["session_id"] == "legacy-session-id"
        assert tabs[0]["screen_id"] == "_default"

    def test_migration_deletes_current_file(self, tmp_path: Path) -> None:
        """After migration, the legacy current file is deleted."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "current").write_text("sess-xyz\n")

        active = ActiveSessions(sessions_dir)
        active.load()

        assert not (sessions_dir / "current").exists()

    def test_no_migration_when_active_json_exists(self, tmp_path: Path) -> None:
        """If active.json already exists, current is ignored (not migrated).
        The current file is left untouched — not deleted — because no
        migration occurred."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "active.json").write_text(
            json.dumps({"tabs": [{"session_id": "existing-sess", "screen_id": "chat-1"}]})
        )
        (sessions_dir / "current").write_text("legacy-should-be-ignored\n")

        active = ActiveSessions(sessions_dir)
        active.load()

        tabs = active.list_all()
        assert len(tabs) == 1
        assert tabs[0]["session_id"] == "existing-sess"
        # current file still exists because migration was skipped
        assert (sessions_dir / "current").exists()

    def test_migration_empty_current(self, tmp_path: Path) -> None:
        """Empty current file does not create a spurious tab entry."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "current").write_text("   \n")

        active = ActiveSessions(sessions_dir)
        active.load()

        assert active.list_all() == []


# =============================================================================
# Add / Remove / List
# =============================================================================


class TestActiveSessionsCRUD:
    """add(), remove(), and list_all() operations."""

    def test_add_new_tab(self, tmp_path: Path) -> None:
        """add() appends a new tab entry."""
        active = ActiveSessions(tmp_path / "sessions")
        active.add("sess-1", "chat-1")
        assert len(active.list_all()) == 1

    def test_add_duplicate_session_id_updates(self, tmp_path: Path) -> None:
        """add() with existing session_id updates screen_id, not duplicates."""
        active = ActiveSessions(tmp_path / "sessions")
        active.add("sess-1", "chat-1")
        active.add("sess-1", "chat-2")
        tabs = active.list_all()
        assert len(tabs) == 1
        assert tabs[0]["screen_id"] == "chat-2"

    def test_remove_existing(self, tmp_path: Path) -> None:
        """remove() deletes the matching tab entry."""
        active = ActiveSessions(tmp_path / "sessions")
        active.add("sess-a", "chat-1")
        active.add("sess-b", "chat-2")
        active.remove("sess-a")
        tabs = active.list_all()
        assert len(tabs) == 1
        assert tabs[0]["session_id"] == "sess-b"

    def test_remove_nonexistent_noop(self, tmp_path: Path) -> None:
        """remove() on unknown session_id does not raise."""
        active = ActiveSessions(tmp_path / "sessions")
        active.add("sess-a", "chat-1")
        active.remove("nonexistent")  # Must not raise
        assert len(active.list_all()) == 1

    def test_list_all_returns_list(self) -> None:
        """list_all() returns a list of TabEntry dicts."""
        active = ActiveSessions(Path("/tmp/fake"))
        result = active.list_all()
        assert isinstance(result, list)
        assert all(isinstance(e, dict) for e in result)


# =============================================================================
# Shape / schema validation
# =============================================================================


class TestTabEntryShape:
    """TabEntry dicts have the correct keys and types."""

    def test_tab_entry_has_required_keys(self, tmp_path: Path) -> None:
        """Each tab entry is a dict with session_id and screen_id."""
        active = ActiveSessions(tmp_path / "sessions")
        active.add("sess-abc", "chat-1")
        entry = active.list_all()[0]
        assert "session_id" in entry
        assert "screen_id" in entry
        assert isinstance(entry["session_id"], str)
        assert isinstance(entry["screen_id"], str)


# =============================================================================
# Round-trip
# =============================================================================


class TestRoundTrip:
    """save() + load() round-trip preserves all data."""

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Data saved by one instance is loadable by another."""
        sessions_dir = tmp_path / "sessions"
        a = ActiveSessions(sessions_dir)
        a.add("sess-a", "chat-1")
        a.add("sess-b", "chat-2")
        a.save()

        b = ActiveSessions(sessions_dir)
        b.load()

        assert b.list_all() == a.list_all()

    def test_multiple_save_load_cycles(self, tmp_path: Path) -> None:
        """save() → load() → mutate → save() → load() preserves state."""
        sessions_dir = tmp_path / "sessions"
        a = ActiveSessions(sessions_dir)
        a.add("s1", "c1")
        a.save()

        b = ActiveSessions(sessions_dir)
        b.load()
        b.add("s2", "c2")
        b.save()

        c = ActiveSessions(sessions_dir)
        c.load()
        tabs = c.list_all()
        assert len(tabs) == 2
        ids = {t["session_id"] for t in tabs}
        assert ids == {"s1", "s2"}
