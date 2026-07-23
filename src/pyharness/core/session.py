"""Session storage layer — libsql-backed (Turso local/embedded).

Provides the system of record for messages, tool calls, token counts,
git refs, and session metadata.  Uses ``libsql`` (the Turso-maintained
SQLite fork) for concurrent-write support via MVCC.

Schema version tracking enables forward-compatible migrations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import turso

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
    """libsql-backed session persistence with concurrent-write support.

    Usage::

        store = SessionStore(db_path)
        store.initialize()
        session = store.create_session(Session(title="My Session"))
        store.add_message(session.id, Message(role="user", content="Hi!"))
        loaded = store.get_session(session.id)
        store.close()
    """

    SCHEMA_VERSION = SCHEMA_VERSION

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: turso.Connection | None = None

    @property
    def _db(self) -> turso.Connection:
        if self._conn is None:
            raise RuntimeError(
                "SessionStore not initialized — call store.initialize() first."
            )
        return self._conn

    def initialize(self) -> None:
        """Create tables, run migrations.  Idempotent."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = turso.connect(str(self.db_path))
        for pragma in PRAGMAS:
            self._conn.execute(pragma)
        self._conn.execute(CREATE_SCHEMA_VERSION)
        self._conn.execute(CREATE_SESSIONS)
        self._conn.execute(CREATE_MESSAGES)
        for idx in INDEXES:
            self._conn.execute(idx)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        current = self._current_version()
        if current == 0:
            self._conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
                (_now_iso(),),
            )
            self._conn.commit()

    def _current_version(self) -> int:
        try:
            result = self._db.execute("SELECT MAX(version) FROM schema_version")
            row = result.fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception:
            return 0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- CRUD: sessions ---------------------------------------------------------

    def create_session(self, session: Session) -> Session:
        self._db.execute(
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
        self._db.commit()
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Load a session by ID, including all messages."""
        result = self._db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = result.fetchone()
        if row is None:
            return None

        session = _row_to_session(row)
        session.messages = self._get_messages(session_id)
        return session

    def list_sessions(
        self,
        project: str | None = None,
        status: str | None = None,
    ) -> list[Session]:
        """List sessions, optionally filtered, ordered by ``updated_at DESC``."""
        query = "SELECT * FROM sessions WHERE 1 = 1"
        params: list[str] = []

        if project is not None:
            query += " AND project = ?"
            params.append(project)
        if status is not None:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY updated_at DESC"

        result = self._db.execute(query, tuple(params))
        rows = result.fetchall()
        return [_row_to_session(r) for r in rows]

    def update_session(self, session: Session) -> None:
        """Update session metadata."""
        session.updated_at = _now_iso()
        self._db.execute(
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
        self._db.commit()

    def delete_session(self, session_id: str) -> None:
        """Soft-delete (archive) a session."""
        self._db.execute(
            "UPDATE sessions SET status = 'archived', updated_at = ? WHERE id = ?",
            (_now_iso(), session_id),
        )
        self._db.commit()

    def hard_delete(self, session_id: str) -> None:
        """Permanently delete a session and all its messages from the database.

        Messages are cascade-deleted via the FOREIGN KEY constraint.
        """
        self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._db.commit()

    # -- CRUD: messages ---------------------------------------------------------

    def add_message(self, session_id: str, message: Message) -> None:
        """Append a message to a session."""
        self._db.execute(
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
        self._db.execute(
            """UPDATE sessions
               SET updated_at = ?,
                   total_tokens = total_tokens + ?
               WHERE id = ?""",
            (_now_iso(), message.token_count, session_id),
        )
        self._db.commit()

    def _get_messages(self, session_id: str) -> list[Message]:
        """Return all messages for a session, ordered by timestamp."""
        result = self._db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
        rows = result.fetchall()
        return [_row_to_message(r) for r in rows]


# ---------------------------------------------------------------------------
# Row → dataclass helpers  (row is a sqlite3.Row-like tuple)
# ---------------------------------------------------------------------------


def _row_to_session(row: tuple) -> Session:
    """Convert a database row to a Session dataclass."""
    return Session(
        id=row[0],
        title=row[1],
        project=row[2],
        model=row[3],
        agent=row[4],
        created_at=row[5],
        updated_at=row[6],
        status=row[7],
        git_branch=row[8],
        total_tokens=row[9],
        metadata=json.loads(row[10] or "{}"),
    )


def _row_to_message(row: tuple) -> Message:
    """Convert a database row to a Message dataclass."""
    tool_args_raw = row[5]
    tool_args = None
    if tool_args_raw and tool_args_raw.strip():
        try:
            tool_args = json.loads(tool_args_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return Message(
        id=row[0],
        role=row[2],
        content=row[3],
        tool_name=row[4],
        tool_args=tool_args,
        tool_result=row[6],
        timestamp=row[7],
        token_count=row[8],
    )
