from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Protocol

from docmolder.models import FileKind, SessionFile, SessionStatus, UserSession


class SessionStore(Protocol):
    def get(self, user_id: int) -> UserSession | None: ...

    def save(self, session: UserSession) -> None: ...

    def delete(self, user_id: int) -> None: ...

    def purge_expired(self, ttl_minutes: int) -> list[int]: ...

    def register_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> bool: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[int, UserSession] = {}
        self._known_user_ids: set[int] = set()

    def get(self, user_id: int) -> UserSession | None:
        with self._lock:
            return self._sessions.get(user_id)

    def save(self, session: UserSession) -> None:
        with self._lock:
            self._sessions[session.user_id] = session

    def delete(self, user_id: int) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)

    def purge_expired(self, ttl_minutes: int) -> list[int]:
        expired_ids: list[int] = []
        with self._lock:
            for user_id, session in list(self._sessions.items()):
                if session.is_expired(ttl_minutes):
                    expired_ids.append(user_id)
                    self._sessions.pop(user_id, None)
        return expired_ids

    def register_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> bool:
        del username, first_name, last_name
        with self._lock:
            if user_id in self._known_user_ids:
                return False
            self._known_user_ids.add(user_id)
            return True


class SQLiteSessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get(self, user_id: int) -> UserSession | None:
        with self._lock, self._connect() as connection:
            session_row = connection.execute(
                """
                SELECT user_id, status, created_at, updated_at
                FROM sessions
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if session_row is None:
                return None

            file_rows = connection.execute(
                """
                SELECT telegram_file_id, file_name, kind, received_at
                FROM session_files
                WHERE user_id = ?
                ORDER BY position ASC, id ASC
                """,
                (user_id,),
            ).fetchall()

        files = [
            SessionFile(
                telegram_file_id=row["telegram_file_id"],
                file_name=row["file_name"],
                kind=FileKind(row["kind"]),
                received_at=_from_isoformat(row["received_at"]),
            )
            for row in file_rows
        ]

        return UserSession(
            user_id=session_row["user_id"],
            status=SessionStatus(session_row["status"]),
            created_at=_from_isoformat(session_row["created_at"]),
            updated_at=_from_isoformat(session_row["updated_at"]),
            files=files,
        )

    def save(self, session: UserSession) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (user_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.user_id,
                    session.status.value,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
            connection.execute("DELETE FROM session_files WHERE user_id = ?", (session.user_id,))
            for position, session_file in enumerate(session.files):
                connection.execute(
                    """
                    INSERT INTO session_files (
                        user_id,
                        position,
                        telegram_file_id,
                        file_name,
                        kind,
                        received_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.user_id,
                        position,
                        session_file.telegram_file_id,
                        session_file.file_name,
                        session_file.kind.value,
                        session_file.received_at.isoformat(),
                    ),
                )
            connection.commit()

    def delete(self, user_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            connection.commit()

    def purge_expired(self, ttl_minutes: int) -> list[int]:
        expired_ids: list[int] = []
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT user_id, updated_at FROM sessions").fetchall()
            for row in rows:
                session = UserSession(
                    user_id=row["user_id"],
                    updated_at=_from_isoformat(row["updated_at"]),
                )
                if session.is_expired(ttl_minutes):
                    expired_ids.append(row["user_id"])
            if expired_ids:
                placeholders = ", ".join("?" for _ in expired_ids)
                connection.execute(f"DELETE FROM session_files WHERE user_id IN ({placeholders})", expired_ids)
                connection.execute(f"DELETE FROM sessions WHERE user_id IN ({placeholders})", expired_ids)
                connection.commit()
        return expired_ids

    def register_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO known_users (
                    user_id,
                    username,
                    first_name,
                    last_name,
                    first_seen_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, username, first_name, last_name),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES sessions(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_session_files_user_position
                    ON session_files(user_id, position);

                CREATE TABLE IF NOT EXISTS known_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    first_seen_at TEXT NOT NULL
                );
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _from_isoformat(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
