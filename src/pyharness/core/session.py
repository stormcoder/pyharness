"""Session storage layer — SQLite-backed with WAL mode and async access.

Provides the system of record for messages, tool calls, token counts,
git refs, and session metadata.

Schema version tracking enables forward-compatible migrations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A single chat message within a session."""

    id: str = field(default_factory=lambda: str(f"msg-{_short_ulid()}"))
    role: str = ""  # "user", "assistant", "tool"
    content: str = ""
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    token_count: int = 0


@dataclass
class Session:
    """A pyharness coding session."""

    id: str = field(default_factory=lambda: str(f"sess-{_short_ulid()}"))
    title: str = "New Session"
    project: str = ""
    model: str = ""
    agent: str = "build"
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    status: str = "active"  # active, idle, compacted, archived
    git_branch: str | None = None
    total_tokens: int = 0
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL
);
"""

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    title         TEXT    NOT NULL DEFAULT 'New Session',
    project       TEXT    NOT NULL DEFAULT '',
    model         TEXT    NOT NULL DEFAULT '',
    agent         TEXT    NOT NULL DEFAULT 'build',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'active',
    git_branch    TEXT,
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT    NOT NULL DEFAULT '{}'
);
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id             TEXT PRIMARY KEY,
    session_id     TEXT    NOT NULL,
    role           TEXT    NOT NULL,
    content        TEXT    NOT NULL DEFAULT '',
    tool_name      TEXT,
    tool_args_json TEXT,
    tool_result    TEXT,
    timestamp      TEXT    NOT NULL,
    token_count    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(session_id, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);",
]

PRAGMAS = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA busy_timeout = 5000;",
    "PRAGMA foreign_keys = ON;",
]


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def _short_ulid() -> str:
    """Generate a short ID using uuid4 hex, trimmed for compactness."""
    import uuid

    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """SQLite-backed session persistence with WAL mode and async access.

    Usage::

        store = SessionStore(db_path)
        await store.initialize()
        session = await store.create_session(Session(title="My Session"))
        await store.add_message(session.id, Message(role="user", content="Hi!"))
        loaded = await store.get_session(session.id)
        await store.close()
    """

    SCHEMA_VERSION = SCHEMA_VERSION

    def __init__(self, db_path: Path) -> None:
        """Create a session store pointing at *db_path*.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    # -- connection management --------------------------------------------------

    @property
    def _db(self) -> aiosqlite.Connection:
        """Return the active connection; raises if not initialized."""
        if self._conn is None:
            raise RuntimeError(
                "SessionStore not initialized — call await store.initialize() first."
            )
        return self._conn

    async def initialize(self) -> None:
        """Create tables, enable WAL, run migrations.

        This must be called once before using the store.  It is idempotent.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row

        # Enable WAL + safety pragmas
        for pragma in PRAGMAS:
            await self._conn.execute(pragma)

        # Create tables
        await self._conn.execute(CREATE_SCHEMA_VERSION)
        await self._conn.execute(CREATE_SESSIONS)
        await self._conn.execute(CREATE_MESSAGES)

        for idx in INDEXES:
            await self._conn.execute(idx)

        # Run any pending migrations
        await self._migrate()

        await self._conn.commit()

    async def _migrate(self) -> None:
        """Apply pending schema migrations in forward order."""
        current = await self._current_version()

        # Migration 1: bootstrap (only if schema_version row absent)
        if current == 0:
            await self._conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
                (_now_iso(),),
            )
            await self._conn.commit()
            current = 1

        # Future migrations go here, e.g.:
        # if current == 1:
        #     await self._conn.execute("ALTER TABLE ...")
        #     await self._conn.execute(
        #         "INSERT INTO schema_version (version, applied_at) VALUES (2, ?)",
        #         (_now_iso(),),
        #     )
        #     current = 2

    async def _current_version(self) -> int:
        """Return the highest applied schema version, or 0 if none."""
        try:
            cursor = await self._db.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except aiosqlite.OperationalError:
            return 0

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- CRUD: sessions ---------------------------------------------------------

    async def create_session(self, session: Session) -> Session:
        """Insert a new session and return it with the generated ID."""
        await self._db.execute(
            """INSERT INTO sessions
               (id, title, project, model, agent, created_at, updated_at,
                status, git_branch, total_tokens, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.title,
                session.project,
                session.model,
                session.agent,
                session.created_at,
                session.updated_at,
                session.status,
                session.git_branch,
                session.total_tokens,
                json.dumps(session.metadata),
            ),
        )
        await self._db.commit()
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Load a session by ID, including all messages."""
        cursor = await self._db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        session = _row_to_session(row)
        session.messages = await self._get_messages(session_id)
        return session

    async def list_sessions(
        self,
        project: str | None = None,
        status: str | None = None,
    ) -> list[Session]:
        """List sessions, optionally filtered by project and/or status.

        Returns sessions ordered by ``updated_at DESC`` (most recent first).
        Messages are *not* loaded — use :meth:`get_session` for full details.
        """
        query = "SELECT * FROM sessions WHERE 1 = 1"
        params: list[str] = []

        if project is not None:
            query += " AND project = ?"
            params.append(project)
        if status is not None:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY updated_at DESC"

        cursor = await self._db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [_row_to_session(r) for r in rows]

    async def update_session(self, session: Session) -> None:
        """Update session metadata (title, status, tokens, branch, etc.)."""
        session.updated_at = _now_iso()
        await self._db.execute(
            """UPDATE sessions
               SET title = ?, project = ?, model = ?, agent = ?,
                   updated_at = ?, status = ?, git_branch = ?,
                   total_tokens = ?, metadata_json = ?
               WHERE id = ?""",
            (
                session.title,
                session.project,
                session.model,
                session.agent,
                session.updated_at,
                session.status,
                session.git_branch,
                session.total_tokens,
                json.dumps(session.metadata),
                session.id,
            ),
        )
        await self._db.commit()

    async def delete_session(self, session_id: str) -> None:
        """Soft-delete (archive) a session by setting its status to 'archived'."""
        await self._db.execute(
            "UPDATE sessions SET status = 'archived', updated_at = ? WHERE id = ?",
            (_now_iso(), session_id),
        )
        await self._db.commit()

    # -- CRUD: messages ----------------------------------------------------------

    async def add_message(self, session_id: str, message: Message) -> None:
        """Append a message to a session. Auto-updates ``updated_at``."""
        await self._db.execute(
            """INSERT INTO messages
               (id, session_id, role, content, tool_name, tool_args_json,
                tool_result, timestamp, token_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message.id,
                session_id,
                message.role,
                message.content,
                message.tool_name,
                json.dumps(message.tool_args) if message.tool_args else None,
                message.tool_result,
                message.timestamp,
                message.token_count,
            ),
        )
        # Bump session timestamp + token total
        await self._db.execute(
            """UPDATE sessions
               SET updated_at = ?,
                   total_tokens = total_tokens + ?
               WHERE id = ?""",
            (_now_iso(), message.token_count, session_id),
        )
        await self._db.commit()

    async def _get_messages(self, session_id: str) -> list[Message]:
        """Return all messages for a session, ordered by timestamp."""
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_message(r) for r in rows]


# ---------------------------------------------------------------------------
# Row → dataclass helpers
# ---------------------------------------------------------------------------


def _row_to_session(row: aiosqlite.Row) -> Session:
    """Convert a database row to a Session dataclass."""
    return Session(
        id=row["id"],
        title=row["title"],
        project=row["project"],
        model=row["model"],
        agent=row["agent"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        status=row["status"],
        git_branch=row["git_branch"],
        total_tokens=row["total_tokens"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )


def _row_to_message(row: aiosqlite.Row) -> Message:
    """Convert a database row to a Message dataclass."""
    tool_args_raw = row["tool_args_json"]
    return Message(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        tool_name=row["tool_name"],
        tool_args=json.loads(tool_args_raw) if tool_args_raw else None,
        tool_result=row["tool_result"],
        timestamp=row["timestamp"],
        token_count=row["token_count"],
    )
