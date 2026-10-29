"""Persistência em SQLite (um arquivo só, num volume do Docker)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from biony.core.models import ChatMessage, Role, ToolCall

# Cada item é uma migração; a posição na lista é a versão do schema.
# Nunca editar uma migração já aplicada: acrescente uma nova no fim.
_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        tool_calls TEXT,
        tool_call_id TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_messages_session ON messages(session_id, id);
    """,
    """
    CREATE TABLE presumed_state (
        device TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
)


class Database:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            # executescript ignora o controle de transação do Python, então a
            # transação vai explícita no script: ou aplica tudo, ou nada.
            self.connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")

    def close(self) -> None:
        self.connection.close()


class SqliteConversationStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def append(self, session_id: str, message: ChatMessage) -> None:
        tool_calls = (
            json.dumps(
                [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in message.tool_calls],
                ensure_ascii=False,
            )
            if message.tool_calls
            else None
        )
        with self._db.connection:
            self._db.connection.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    message.role.value,
                    message.content,
                    tool_calls,
                    message.tool_call_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def recent(self, session_id: str, limit: int) -> list[ChatMessage]:
        rows = self._db.connection.execute(
            "SELECT role, content, tool_calls, tool_call_id FROM messages"
            " WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [_row_to_message(row) for row in reversed(rows)]


def _row_to_message(row: sqlite3.Row) -> ChatMessage:
    calls = tuple(
        ToolCall(item["id"], item["name"], item["arguments"])
        for item in json.loads(row["tool_calls"] or "[]")
    )
    return ChatMessage(Role(row["role"]), row["content"], calls, row["tool_call_id"])


class SqlitePresumedStateStore:
    """Estado presumido de aparelhos IR, para sobreviver a reinícios."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, device: str) -> str | None:
        row = self._db.connection.execute(
            "SELECT state FROM presumed_state WHERE device = ?", (device,)
        ).fetchone()
        return row["state"] if row else None

    def set(self, device: str, state: str) -> None:
        with self._db.connection:
            self._db.connection.execute(
                "INSERT INTO presumed_state (device, state, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(device) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
                (device, state, datetime.now(timezone.utc).isoformat()),
            )
