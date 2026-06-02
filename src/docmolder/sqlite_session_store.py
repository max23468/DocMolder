from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from docmolder.models import (
    AdminActionStat,
    AdminStats,
    AdminUserStat,
    AuditLogEntry,
    FileKind,
    JobRecord,
    JobStatus,
    SessionFile,
    SessionStatus,
    SupportedActionValue,
    UserDataDeletionReport,
    UserSession,
)

SQLiteParameter = str | int | float | bytes | None


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
                SELECT user_id, status, pending_action, created_at, updated_at
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
            pending_action=session_row["pending_action"] if "pending_action" in session_row.keys() else None,
            created_at=_from_isoformat(session_row["created_at"]),
            updated_at=_from_isoformat(session_row["updated_at"]),
            files=files,
        )

    def save(self, session: UserSession) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (user_id, status, pending_action, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = excluded.status,
                    pending_action = excluded.pending_action,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.user_id,
                    session.status.value,
                    session.pending_action,
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
            connection.execute("DELETE FROM session_files WHERE user_id = ?", (user_id,))
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

    def record_completed_action(self, user_id: int, action: SupportedActionValue) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO usage_events (user_id, action, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, action),
            )
            connection.commit()

    def get_meta(self, key: str) -> str | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            connection.commit()

    def delete_meta(self, key: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM app_meta WHERE key = ?", (key,))
            connection.commit()

    def list_meta(self, prefix: str) -> dict[str, str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT key, value FROM app_meta WHERE key LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def get_user_preference(self, user_id: int, key: str) -> str | None:
        return self.get_meta(f"user_pref:{user_id}:{key}")

    def set_user_preference(self, user_id: int, key: str, value: str) -> None:
        self.set_meta(f"user_pref:{user_id}:{key}", value)

    def clear_user_preferences(self, user_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM app_meta WHERE key LIKE ?",
                (f"user_pref:{user_id}:%",),
            )
            connection.commit()

    def get_user_preset(self, user_id: int, key: str) -> str | None:
        return self.get_meta(f"user_preset:{user_id}:{key}")

    def set_user_preset(self, user_id: int, key: str, value: str) -> None:
        self.set_meta(f"user_preset:{user_id}:{key}", value)

    def clear_user_presets(self, user_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM app_meta WHERE key LIKE ?",
                (f"user_preset:{user_id}:%",),
            )
            connection.commit()

    def delete_user_data(self, user_id: int) -> UserDataDeletionReport:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM session_files WHERE user_id = ?", (user_id,))
            sessions_deleted = _delete_count(connection, "DELETE FROM sessions WHERE user_id = ?", (user_id,))
            jobs_deleted = _delete_count(connection, "DELETE FROM jobs WHERE user_id = ?", (user_id,))
            usage_events_deleted = _delete_count(
                connection,
                "DELETE FROM usage_events WHERE user_id = ?",
                (user_id,),
            )
            known_users_deleted = _delete_count(
                connection,
                "DELETE FROM known_users WHERE user_id = ?",
                (user_id,),
            )
            meta_deleted = _delete_count(
                connection,
                """
                DELETE FROM app_meta
                WHERE key IN (?, ?)
                   OR key LIKE ?
                   OR key LIKE ?
                """,
                (
                    f"access:{user_id}:status",
                    f"upload_burst:{user_id}",
                    f"user_pref:{user_id}:%",
                    f"user_preset:{user_id}:%",
                ),
            )
            audit_cursor = connection.execute(
                """
                UPDATE audit_log
                SET
                    actor_user_id = CASE WHEN actor_user_id = ? THEN NULL ELSE actor_user_id END,
                    target_user_id = CASE WHEN target_user_id = ? THEN NULL ELSE target_user_id END,
                    detail = ''
                WHERE actor_user_id = ? OR target_user_id = ?
                """,
                (user_id, user_id, user_id, user_id),
            )
            connection.commit()
            return UserDataDeletionReport(
                sessions_deleted=sessions_deleted,
                jobs_deleted=jobs_deleted,
                usage_events_deleted=usage_events_deleted,
                known_users_deleted=known_users_deleted,
                meta_deleted=meta_deleted,
                audit_entries_scrubbed=int(audit_cursor.rowcount),
            )

    def build_admin_stats(self) -> AdminStats:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM known_users) AS known_users_total,
                    (SELECT COUNT(*) FROM known_users WHERE first_seen_at >= datetime('now', '-1 day')) AS known_users_last_24h,
                    (SELECT COUNT(*) FROM known_users WHERE first_seen_at >= datetime('now', '-7 day')) AS known_users_last_7d,
                    (SELECT COUNT(DISTINCT user_id) FROM usage_events WHERE created_at >= datetime('now', '-1 day')) AS active_users_last_24h,
                    (SELECT COUNT(DISTINCT user_id) FROM usage_events WHERE created_at >= datetime('now', '-7 day')) AS active_users_last_7d,
                    (SELECT COUNT(*) FROM usage_events) AS completed_actions_total,
                    (SELECT COUNT(*) FROM usage_events WHERE created_at >= datetime('now', '-1 day')) AS completed_actions_last_24h,
                    (SELECT COUNT(*) FROM usage_events WHERE created_at >= datetime('now', '-7 day')) AS completed_actions_last_7d,
                    (SELECT COUNT(*) FROM sessions) AS active_sessions,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'images_to_pdf') AS images_to_pdf_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_compress') AS pdf_compress_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_grayscale') AS pdf_grayscale_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_merge') AS pdf_merge_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_split') AS pdf_split_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_extract_pages') AS pdf_extract_pages_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_reorder_pages') AS pdf_reorder_pages_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_delete_pages') AS pdf_delete_pages_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_rotate') AS pdf_rotate_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'pdf_watermark') AS pdf_watermark_total,
                    (SELECT COUNT(*) FROM usage_events WHERE action = 'auto_orient') AS auto_orient_total,
                    (SELECT COUNT(*) FROM jobs WHERE status = 'queued') AS jobs_queued,
                    (SELECT COUNT(*) FROM jobs WHERE status = 'running') AS jobs_running,
                    (SELECT COUNT(*) FROM jobs WHERE status = 'failed') AS jobs_failed,
                    (SELECT COUNT(*) FROM jobs WHERE status = 'succeeded') AS jobs_succeeded,
                    (SELECT COUNT(*) FROM jobs WHERE status IN ('failed', 'succeeded') AND COALESCE(finished_at, created_at) >= datetime('now', '-1 day')) AS jobs_finished_last_24h,
                    (SELECT COUNT(*) FROM jobs WHERE status = 'failed' AND COALESCE(finished_at, created_at) >= datetime('now', '-1 day')) AS jobs_failed_last_24h,
                    (SELECT COUNT(*) FROM jobs WHERE processing_mode = 'raster') AS raster_results_total,
                    (SELECT COALESCE(ROUND(AVG(duration_ms)), 0) FROM jobs WHERE status = 'succeeded' AND duration_ms IS NOT NULL) AS avg_duration_ms,
                    (SELECT COALESCE(ROUND(AVG(input_bytes)), 0) FROM jobs WHERE status = 'succeeded' AND input_bytes IS NOT NULL) AS avg_input_bytes,
                    (SELECT COALESCE(ROUND(AVG(output_bytes)), 0) FROM jobs WHERE status = 'succeeded' AND output_bytes IS NOT NULL) AS avg_output_bytes
                """
            ).fetchone()

        return AdminStats(**{key: int(row[key]) for key in row.keys()})

    def create_job(
        self,
        user_id: int,
        chat_id: int,
        reply_to_message_id: int | None,
        action: SupportedActionValue,
        payload_json: str,
        rerun_of_job_id: int | None = None,
    ) -> JobRecord:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (
                    user_id,
                    chat_id,
                    reply_to_message_id,
                    action,
                    payload_json,
                    rerun_of_job_id,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, chat_id, reply_to_message_id, action, payload_json, rerun_of_job_id, JobStatus.QUEUED.value),
            )
            connection.commit()
            job_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row)

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return _job_from_row(row)

    def mark_job_running(self, job_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = CURRENT_TIMESTAMP, error_message = NULL
                WHERE id = ?
                """,
                (JobStatus.RUNNING.value, job_id),
            )
            connection.commit()

    def mark_job_succeeded(self, job_id: int, result_message: str) -> None:
        self.mark_job_succeeded_with_metrics(
            job_id,
            result_message,
            processing_mode=None,
            input_bytes=None,
            output_bytes=None,
            duration_ms=None,
        )

    def mark_job_succeeded_with_metrics(
        self,
        job_id: int,
        result_message: str,
        *,
        processing_mode: str | None,
        input_bytes: int | None,
        output_bytes: int | None,
        duration_ms: int | None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = CURRENT_TIMESTAMP, result_message = ?, error_message = NULL,
                    processing_mode = ?, input_bytes = ?, output_bytes = ?, duration_ms = ?
                WHERE id = ?
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    result_message,
                    processing_mode,
                    input_bytes,
                    output_bytes,
                    duration_ms,
                    job_id,
                ),
            )
            connection.commit()

    def mark_job_failed(self, job_id: int, error_message: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, error_message, job_id),
            )
            connection.commit()

    def requeue_incomplete_jobs(self) -> list[JobRecord]:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = NULL, finished_at = NULL, result_message = NULL, error_message = NULL,
                    processing_mode = NULL, input_bytes = NULL, output_bytes = NULL, duration_ms = NULL
                WHERE status IN (?, ?)
                """,
                (JobStatus.QUEUED.value, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            )
            rows = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE status = ?
                ORDER BY id ASC
                """,
                (JobStatus.QUEUED.value,),
            ).fetchall()
            connection.commit()
        return [_job_from_row(row) for row in rows]

    def count_active_jobs_for_user(self, user_id: int) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM jobs
                WHERE user_id = ? AND status IN (?, ?)
                """,
                (user_id, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            ).fetchone()
        return int(row["total"])

    def list_top_users(self, limit: int = 5, since_days: int = 7) -> list[AdminUserStat]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    usage_events.user_id AS user_id,
                    COALESCE(
                        known_users.username,
                        TRIM(COALESCE(known_users.first_name, '') || ' ' || COALESCE(known_users.last_name, '')),
                        ''
                    ) AS raw_label,
                    COUNT(*) AS completed_actions
                FROM usage_events
                LEFT JOIN known_users ON known_users.user_id = usage_events.user_id
                WHERE usage_events.created_at >= datetime('now', ?)
                GROUP BY usage_events.user_id
                ORDER BY completed_actions DESC, usage_events.user_id ASC
                LIMIT ?
                """,
                (f"-{since_days} day", limit),
            ).fetchall()
        top_users: list[AdminUserStat] = []
        for row in rows:
            raw_label = (row["raw_label"] or "").strip()
            label = raw_label if raw_label else f"Utente {row['user_id']}"
            if raw_label and not raw_label.startswith("@") and " " not in raw_label:
                label = f"@{raw_label}"
            top_users.append(
                AdminUserStat(
                    user_id=row["user_id"],
                    label=label,
                    completed_actions=int(row["completed_actions"]),
                )
            )
        return top_users

    def list_failed_actions(
        self,
        limit: int = 5,
        since_days: int = 7,
        since_minutes: int | None = None,
    ) -> list[AdminActionStat]:
        since_condition, since_params = _build_since_window_condition(
            column="COALESCE(finished_at, created_at)",
            since_days=since_days,
            since_minutes=since_minutes,
        )
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT action, COUNT(*) AS total
                FROM jobs
                WHERE status = ?{" AND " + since_condition if since_condition else ""}
                GROUP BY action
                ORDER BY total DESC, action ASC
                LIMIT ?
                """,
                (JobStatus.FAILED.value, *since_params, limit),
            ).fetchall()
        return [AdminActionStat(action=row["action"], total=int(row["total"])) for row in rows]

    def list_user_jobs(
        self,
        user_id: int,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
    ) -> list[JobRecord]:
        conditions = ["user_id = ?"]
        params: list[SQLiteParameter] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(status.value for status in statuses)
        params.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM jobs
                WHERE {" AND ".join(conditions)}
                ORDER BY COALESCE(finished_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def list_recent_jobs(
        self,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
        since_days: int | None = None,
        since_minutes: int | None = None,
    ) -> list[JobRecord]:
        query = """
            SELECT *
            FROM jobs
        """
        params: list[SQLiteParameter] = []
        conditions: list[str] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(status.value for status in statuses)
        since_condition, since_params = _build_since_window_condition(
            column="COALESCE(finished_at, created_at)",
            since_days=since_days,
            since_minutes=since_minutes,
        )
        if since_condition:
            conditions.append(since_condition)
            params.extend(since_params)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY COALESCE(finished_at, created_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_job_from_row(row) for row in rows]

    def list_stale_running_jobs(self, max_age_seconds: int, limit: int = 20) -> list[JobRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE status = ? AND started_at IS NOT NULL AND started_at < datetime('now', ?)
                ORDER BY started_at ASC, id ASC
                LIMIT ?
                """,
                (JobStatus.RUNNING.value, f"-{max(0, max_age_seconds)} second", limit),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def requeue_stale_running_jobs(self, max_age_seconds: int) -> list[JobRecord]:
        stale_jobs = self.list_stale_running_jobs(max_age_seconds=max_age_seconds, limit=1000)
        if not stale_jobs:
            return []
        stale_ids = [job.id for job in stale_jobs]
        placeholders = ", ".join("?" for _ in stale_ids)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"""
                UPDATE jobs
                SET status = ?, started_at = NULL, finished_at = NULL, result_message = NULL, error_message = NULL,
                    processing_mode = NULL, input_bytes = NULL, output_bytes = NULL, duration_ms = NULL
                WHERE id IN ({placeholders})
                """,
                (JobStatus.QUEUED.value, *stale_ids),
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM jobs
                WHERE id IN ({placeholders})
                ORDER BY id ASC
                """,
                stale_ids,
            ).fetchall()
            connection.commit()
        return [_job_from_row(row) for row in rows]

    def prune_finished_jobs(self, retention_days: int) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM jobs
                WHERE status IN (?, ?)
                  AND COALESCE(finished_at, created_at) < datetime('now', ?)
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    JobStatus.FAILED.value,
                    f"-{max(0, retention_days)} day",
                ),
            )
            connection.commit()
            return int(cursor.rowcount)

    def append_audit_log_entry(
        self,
        event_type: str,
        *,
        actor_user_id: int | None,
        outcome: str,
        target_user_id: int | None = None,
        detail: str = "",
    ) -> AuditLogEntry:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_log (
                    event_type,
                    actor_user_id,
                    target_user_id,
                    outcome,
                    detail,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (event_type, actor_user_id, target_user_id, outcome, detail),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM audit_log WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
        return _audit_entry_from_row(row)

    def list_audit_log_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_audit_entry_from_row(row) for row in rows]

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions (
                    user_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    pending_action TEXT,
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

                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_usage_events_created_at
                    ON usage_events(created_at);

                CREATE INDEX IF NOT EXISTS idx_usage_events_action
                    ON usage_events(action);

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    reply_to_message_id INTEGER,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    rerun_of_job_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_message TEXT,
                    error_message TEXT,
                    processing_mode TEXT,
                    input_bytes INTEGER,
                    output_bytes INTEGER,
                    duration_ms INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
                    ON jobs(status, created_at);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor_user_id INTEGER,
                    target_user_id INTEGER,
                    outcome TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
                    ON audit_log(created_at);

                CREATE INDEX IF NOT EXISTS idx_audit_log_event_type
                    ON audit_log(event_type);
                """
            )
            self._ensure_job_metrics_columns(connection)
            self._ensure_session_columns(connection)
            self._ensure_job_rerun_column(connection)
            connection.commit()

    def _ensure_job_metrics_columns(self, connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        if "processing_mode" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN processing_mode TEXT")
        if "input_bytes" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN input_bytes INTEGER")
        if "output_bytes" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN output_bytes INTEGER")
        if "duration_ms" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN duration_ms INTEGER")

    def _ensure_job_rerun_column(self, connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        if "rerun_of_job_id" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN rerun_of_job_id INTEGER")

    def _ensure_session_columns(self, connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}
        if "pending_action" not in columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN pending_action TEXT")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def _from_isoformat(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _from_sqlite_datetime(value: str | None):
    from datetime import datetime, timezone

    if value is None:
        return None
    return datetime.fromisoformat(value.replace(" ", "T")).replace(tzinfo=timezone.utc)


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        user_id=row["user_id"],
        chat_id=row["chat_id"],
        reply_to_message_id=row["reply_to_message_id"],
        action=row["action"],
        payload_json=row["payload_json"],
        status=JobStatus(row["status"]),
        created_at=_from_sqlite_datetime(row["created_at"]),
        rerun_of_job_id=row["rerun_of_job_id"] if "rerun_of_job_id" in row.keys() else None,
        started_at=_from_sqlite_datetime(row["started_at"]),
        finished_at=_from_sqlite_datetime(row["finished_at"]),
        result_message=row["result_message"],
        error_message=row["error_message"],
        processing_mode=row["processing_mode"] if "processing_mode" in row.keys() else None,
        input_bytes=row["input_bytes"] if "input_bytes" in row.keys() else None,
        output_bytes=row["output_bytes"] if "output_bytes" in row.keys() else None,
        duration_ms=row["duration_ms"] if "duration_ms" in row.keys() else None,
    )


def _audit_entry_from_row(row: sqlite3.Row) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        event_type=row["event_type"],
        actor_user_id=row["actor_user_id"],
        target_user_id=row["target_user_id"],
        outcome=row["outcome"],
        detail=row["detail"],
        created_at=_from_sqlite_datetime(row["created_at"]),
    )


def _delete_count(connection: sqlite3.Connection, query: str, params: tuple[SQLiteParameter, ...]) -> int:
    cursor = connection.execute(query, params)
    return int(cursor.rowcount)


def _safe_average(values) -> int:
    collected = [int(value) for value in values if value is not None]
    if not collected:
        return 0
    return sum(collected) // len(collected)


def _build_since_window_condition(
    *,
    column: str,
    since_days: int | None,
    since_minutes: int | None,
) -> tuple[str, list[str]]:
    if since_minutes is not None:
        return f"{column} >= datetime('now', ?)", [f"-{since_minutes} minute"]
    if since_days is not None:
        return f"{column} >= datetime('now', ?)", [f"-{since_days} day"]
    return "", []
