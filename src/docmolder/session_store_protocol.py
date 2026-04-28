from __future__ import annotations

from typing import Protocol

from docmolder.models import (
    AdminActionStat,
    AdminStats,
    AdminUserStat,
    AuditLogEntry,
    JobRecord,
    JobStatus,
    SupportedActionValue,
    UserDataDeletionReport,
    UserSession,
)


class SessionStore(Protocol):
    def get(self, user_id: int) -> UserSession | None: ...

    def save(self, session: UserSession) -> None: ...

    def delete(self, user_id: int) -> None: ...

    def purge_expired(self, ttl_minutes: int) -> list[int]: ...

    def register_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> bool: ...

    def record_completed_action(self, user_id: int, action: SupportedActionValue) -> None: ...

    def get_meta(self, key: str) -> str | None: ...

    def set_meta(self, key: str, value: str) -> None: ...

    def list_meta(self, prefix: str) -> dict[str, str]: ...

    def get_user_preference(self, user_id: int, key: str) -> str | None: ...

    def set_user_preference(self, user_id: int, key: str, value: str) -> None: ...

    def clear_user_preferences(self, user_id: int) -> None: ...

    def delete_user_data(self, user_id: int) -> UserDataDeletionReport: ...

    def build_admin_stats(self) -> AdminStats: ...

    def create_job(
        self,
        user_id: int,
        chat_id: int,
        reply_to_message_id: int | None,
        action: SupportedActionValue,
        payload_json: str,
        rerun_of_job_id: int | None = None,
    ) -> JobRecord: ...

    def get_job(self, job_id: int) -> JobRecord | None: ...

    def mark_job_running(self, job_id: int) -> None: ...

    def mark_job_succeeded(self, job_id: int, result_message: str) -> None: ...

    def mark_job_succeeded_with_metrics(
        self,
        job_id: int,
        result_message: str,
        *,
        processing_mode: str | None,
        input_bytes: int | None,
        output_bytes: int | None,
        duration_ms: int | None,
    ) -> None: ...

    def mark_job_failed(self, job_id: int, error_message: str) -> None: ...

    def requeue_incomplete_jobs(self) -> list[JobRecord]: ...

    def count_active_jobs_for_user(self, user_id: int) -> int: ...

    def list_top_users(self, limit: int = 5, since_days: int = 7) -> list[AdminUserStat]: ...

    def list_failed_actions(
        self,
        limit: int = 5,
        since_days: int = 7,
        since_minutes: int | None = None,
    ) -> list[AdminActionStat]: ...

    def list_user_jobs(
        self,
        user_id: int,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
    ) -> list[JobRecord]: ...

    def list_recent_jobs(
        self,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
        since_days: int | None = None,
        since_minutes: int | None = None,
    ) -> list[JobRecord]: ...

    def list_stale_running_jobs(self, max_age_seconds: int, limit: int = 20) -> list[JobRecord]: ...

    def requeue_stale_running_jobs(self, max_age_seconds: int) -> list[JobRecord]: ...

    def prune_finished_jobs(self, retention_days: int) -> int: ...

    def append_audit_log_entry(
        self,
        event_type: str,
        *,
        actor_user_id: int | None,
        outcome: str,
        target_user_id: int | None = None,
        detail: str = "",
    ) -> AuditLogEntry: ...

    def list_audit_log_entries(self, limit: int = 100) -> list[AuditLogEntry]: ...
