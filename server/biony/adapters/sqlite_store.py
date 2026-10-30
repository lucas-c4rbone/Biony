"""Persistência em SQLite (um arquivo só, num volume do Docker)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import secrets
from pathlib import Path
import sqlite3

from biony.core.memory import Memory
from biony.core.models import ChatMessage, Role, ToolCall
from biony.core.reminders import Due, Reminder, Task

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
    """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        due TEXT,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        done_at TEXT,
        deleted_at TEXT
    );
    CREATE TABLE reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER REFERENCES tasks(id),
        text TEXT,
        fire_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        cancelled_at TEXT
    );
    CREATE INDEX idx_reminders_pending ON reminders(fire_at) WHERE sent_at IS NULL AND cancelled_at IS NULL;
    CREATE TABLE memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        deleted_at TEXT
    );
    """,
    """
    CREATE TABLE login_tokens (
        token_hash TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT,
        revoked_at TEXT
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteReminderStore:
    """Tarefas e lembretes. Nada é apagado de verdade: só marcado (deleted_at, cancelled_at)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _write(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._db.connection:
            return self._db.connection.execute(sql, params)

    def add_task(self, title: str, due: Due | None, notes: str = "") -> Task:
        cursor = self._write(
            "INSERT INTO tasks (title, due, notes, created_at) VALUES (?, ?, ?, ?)",
            (title, due.iso() if due else None, notes, _now()),
        )
        return Task(cursor.lastrowid, title, due, notes)

    def get_task(self, task_id: int) -> Task | None:
        row = self._db.connection.execute(
            "SELECT * FROM tasks WHERE id = ? AND deleted_at IS NULL", (task_id,)
        ).fetchone()
        return _row_to_task(row) if row else None

    def open_tasks(self) -> list[Task]:
        rows = self._db.connection.execute(
            "SELECT * FROM tasks WHERE done_at IS NULL AND deleted_at IS NULL ORDER BY id"
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    def complete_task(self, task_id: int) -> bool:
        cursor = self._write(
            "UPDATE tasks SET done_at = ? WHERE id = ? AND done_at IS NULL AND deleted_at IS NULL",
            (_now(), task_id),
        )
        return cursor.rowcount == 1

    def delete_task(self, task_id: int) -> bool:
        cursor = self._write(
            "UPDATE tasks SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (_now(), task_id)
        )
        return cursor.rowcount == 1

    def add_reminder(self, fire_at: datetime, task_id: int | None = None, text: str | None = None) -> Reminder:
        if fire_at.tzinfo is None:
            raise ValueError("fire_at precisa ter fuso horário")
        cursor = self._write(
            "INSERT INTO reminders (task_id, text, fire_at, created_at) VALUES (?, ?, ?, ?)",
            (task_id, text, fire_at.astimezone(timezone.utc).isoformat(), _now()),
        )
        return Reminder(cursor.lastrowid, fire_at, task_id, text)

    def get_reminder(self, reminder_id: int) -> Reminder | None:
        row = self._db.connection.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return _row_to_reminder(row) if row else None

    def pending_reminders(self, task_id: int | None = None) -> list[Reminder]:
        sql = "SELECT * FROM reminders WHERE sent_at IS NULL AND cancelled_at IS NULL"
        params: tuple = ()
        if task_id is not None:
            sql += " AND task_id = ?"
            params = (task_id,)
        rows = self._db.connection.execute(sql + " ORDER BY fire_at", params).fetchall()
        return [_row_to_reminder(row) for row in rows]

    def mark_sent(self, reminder_id: int) -> None:
        self._write("UPDATE reminders SET sent_at = ? WHERE id = ?", (_now(), reminder_id))

    def record_failure(self, reminder_id: int) -> int:
        self._write("UPDATE reminders SET attempts = attempts + 1 WHERE id = ?", (reminder_id,))
        row = self._db.connection.execute("SELECT attempts FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return row["attempts"]

    def cancel_reminder(self, reminder_id: int) -> bool:
        cursor = self._write(
            "UPDATE reminders SET cancelled_at = ? WHERE id = ? AND sent_at IS NULL AND cancelled_at IS NULL",
            (_now(), reminder_id),
        )
        return cursor.rowcount == 1

    def cancel_task_reminders(self, task_id: int) -> int:
        cursor = self._write(
            "UPDATE reminders SET cancelled_at = ? WHERE task_id = ? AND sent_at IS NULL AND cancelled_at IS NULL",
            (_now(), task_id),
        )
        return cursor.rowcount


def _row_to_task(row: sqlite3.Row) -> Task:
    due = Due.parse(row["due"]) if row["due"] else None
    return Task(row["id"], row["title"], due, row["notes"], done=row["done_at"] is not None)


def _row_to_reminder(row: sqlite3.Row) -> Reminder:
    return Reminder(
        row["id"],
        datetime.fromisoformat(row["fire_at"]),
        row["task_id"],
        row["text"],
        row["attempts"],
        pending=row["sent_at"] is None and row["cancelled_at"] is None,
    )


class SqliteMemoryStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, content: str) -> Memory:
        with self._db.connection:
            cursor = self._db.connection.execute(
                "INSERT INTO memories (content, created_at) VALUES (?, ?)", (content, _now())
            )
        return Memory(cursor.lastrowid, content)

    def all(self) -> list[Memory]:
        rows = self._db.connection.execute(
            "SELECT id, content FROM memories WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
        return [Memory(row["id"], row["content"]) for row in rows]

    def remove(self, memory_id: int) -> bool:
        with self._db.connection:
            cursor = self._db.connection.execute(
                "UPDATE memories SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (_now(), memory_id)
            )
        return cursor.rowcount == 1


class SqliteLoginTokenStore:
    """Tokens de login por aparelho. Só o hash fica no banco."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, label: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._db.connection:
            self._db.connection.execute(
                "INSERT INTO login_tokens (token_hash, label, created_at) VALUES (?, ?, ?)",
                (_hash(token), label[:100], _now()),
            )
        return token

    def is_valid(self, token: str) -> bool:
        with self._db.connection:
            cursor = self._db.connection.execute(
                "UPDATE login_tokens SET last_used_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (_now(), _hash(token)),
            )
        return cursor.rowcount == 1

    def revoke(self, token: str) -> bool:
        with self._db.connection:
            cursor = self._db.connection.execute(
                "UPDATE login_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (_now(), _hash(token)),
            )
        return cursor.rowcount == 1


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
