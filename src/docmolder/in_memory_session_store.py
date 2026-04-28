from __future__ import annotations

from threading import Lock

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


class InMemorySessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[int, UserSession] = {}
        self._known_user_ids: set[int] = set()
        self._completed_actions: list[tuple[int, SupportedActionValue]] = []
        self._jobs: dict[int, JobRecord] = {}
        self._audit_entries: list[AuditLogEntry] = []
        self._meta: dict[str, str] = {}
        self._next_job_id = 1
        self._next_audit_id = 1

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

    def record_completed_action(self, user_id: int, action: SupportedActionValue) -> None:
        with self._lock:
            self._completed_actions.append((user_id, action))

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            return self._meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._meta[key] = value

    def list_meta(self, prefix: str) -> dict[str, str]:
        with self._lock:
            return {key: value for key, value in self._meta.items() if key.startswith(prefix)}

    def get_user_preference(self, user_id: int, key: str) -> str | None:
        with self._lock:
            return self._meta.get(f"user_pref:{user_id}:{key}")

    def set_user_preference(self, user_id: int, key: str, value: str) -> None:
        with self._lock:
            self._meta[f"user_pref:{user_id}:{key}"] = value

    def clear_user_preferences(self, user_id: int) -> None:
        prefix = f"user_pref:{user_id}:"
        with self._lock:
            for meta_key in [meta_key for meta_key in self._meta if meta_key.startswith(prefix)]:
                self._meta.pop(meta_key, None)

    def get_user_preset(self, user_id: int, key: str) -> str | None:
        with self._lock:
            return self._meta.get(f"user_preset:{user_id}:{key}")

    def set_user_preset(self, user_id: int, key: str, value: str) -> None:
        with self._lock:
            self._meta[f"user_preset:{user_id}:{key}"] = value

    def clear_user_presets(self, user_id: int) -> None:
        prefix = f"user_preset:{user_id}:"
        with self._lock:
            for meta_key in [meta_key for meta_key in self._meta if meta_key.startswith(prefix)]:
                self._meta.pop(meta_key, None)

    def delete_user_data(self, user_id: int) -> UserDataDeletionReport:
        with self._lock:
            meta_prefixes = (f"user_pref:{user_id}:", f"user_preset:{user_id}:")
            meta_keys = [
                key
                for key in self._meta
                if key in {f"access:{user_id}:status", f"upload_burst:{user_id}"}
                or any(key.startswith(prefix) for prefix in meta_prefixes)
            ]
            sessions_deleted = 1 if user_id in self._sessions else 0
            self._sessions.pop(user_id, None)
            jobs_deleted = sum(1 for job in self._jobs.values() if job.user_id == user_id)
            self._jobs = {job_id: job for job_id, job in self._jobs.items() if job.user_id != user_id}
            usage_events_deleted = sum(1 for event_user_id, _action in self._completed_actions if event_user_id == user_id)
            self._completed_actions = [
                (event_user_id, action)
                for event_user_id, action in self._completed_actions
                if event_user_id != user_id
            ]
            known_users_deleted = 1 if user_id in self._known_user_ids else 0
            self._known_user_ids.discard(user_id)
            for meta_key in meta_keys:
                self._meta.pop(meta_key, None)
            audit_entries_scrubbed = 0
            for entry in self._audit_entries:
                if entry.actor_user_id == user_id or entry.target_user_id == user_id:
                    entry.actor_user_id = None if entry.actor_user_id == user_id else entry.actor_user_id
                    entry.target_user_id = None if entry.target_user_id == user_id else entry.target_user_id
                    entry.detail = ""
                    audit_entries_scrubbed += 1
            return UserDataDeletionReport(
                sessions_deleted=sessions_deleted,
                jobs_deleted=jobs_deleted,
                usage_events_deleted=usage_events_deleted,
                known_users_deleted=known_users_deleted,
                meta_deleted=len(meta_keys),
                audit_entries_scrubbed=audit_entries_scrubbed,
            )

    def build_admin_stats(self) -> AdminStats:
        with self._lock:
            active_user_ids = {user_id for user_id, _action in self._completed_actions}
            jobs_finished_last_24h = sum(
                1 for job in self._jobs.values() if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}
            )
            return AdminStats(
                known_users_total=len(self._known_user_ids),
                known_users_last_24h=len(self._known_user_ids),
                known_users_last_7d=len(self._known_user_ids),
                active_users_last_24h=len(active_user_ids),
                active_users_last_7d=len(active_user_ids),
                completed_actions_total=len(self._completed_actions),
                completed_actions_last_24h=len(self._completed_actions),
                completed_actions_last_7d=len(self._completed_actions),
                active_sessions=len(self._sessions),
                images_to_pdf_total=sum(1 for _, action in self._completed_actions if action == "images_to_pdf"),
                pdf_compress_total=sum(1 for _, action in self._completed_actions if action == "pdf_compress"),
                pdf_grayscale_total=sum(1 for _, action in self._completed_actions if action == "pdf_grayscale"),
                pdf_merge_total=sum(1 for _, action in self._completed_actions if action == "pdf_merge"),
                pdf_split_total=sum(1 for _, action in self._completed_actions if action == "pdf_split"),
                pdf_extract_pages_total=sum(
                    1 for _, action in self._completed_actions if action == "pdf_extract_pages"
                ),
                pdf_reorder_pages_total=sum(
                    1 for _, action in self._completed_actions if action == "pdf_reorder_pages"
                ),
                pdf_delete_pages_total=sum(1 for _, action in self._completed_actions if action == "pdf_delete_pages"),
                pdf_rotate_total=sum(1 for _, action in self._completed_actions if action == "pdf_rotate"),
                pdf_watermark_total=sum(1 for _, action in self._completed_actions if action == "pdf_watermark"),
                auto_orient_total=sum(1 for _, action in self._completed_actions if action == "auto_orient"),
                jobs_queued=sum(1 for job in self._jobs.values() if job.status == JobStatus.QUEUED),
                jobs_running=sum(1 for job in self._jobs.values() if job.status == JobStatus.RUNNING),
                jobs_failed=sum(1 for job in self._jobs.values() if job.status == JobStatus.FAILED),
                jobs_succeeded=sum(1 for job in self._jobs.values() if job.status == JobStatus.SUCCEEDED),
                jobs_finished_last_24h=jobs_finished_last_24h,
                jobs_failed_last_24h=sum(1 for job in self._jobs.values() if job.status == JobStatus.FAILED),
                raster_results_total=sum(1 for job in self._jobs.values() if job.processing_mode == "raster"),
                avg_duration_ms=_safe_average(
                    job.duration_ms for job in self._jobs.values() if job.status == JobStatus.SUCCEEDED
                ),
                avg_input_bytes=_safe_average(
                    job.input_bytes for job in self._jobs.values() if job.status == JobStatus.SUCCEEDED
                ),
                avg_output_bytes=_safe_average(
                    job.output_bytes for job in self._jobs.values() if job.status == JobStatus.SUCCEEDED
                ),
            )

    def create_job(
        self,
        user_id: int,
        chat_id: int,
        reply_to_message_id: int | None,
        action: SupportedActionValue,
        payload_json: str,
        rerun_of_job_id: int | None = None,
    ) -> JobRecord:
        from datetime import datetime, timezone

        with self._lock:
            job = JobRecord(
                id=self._next_job_id,
                user_id=user_id,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                action=action,
                payload_json=payload_json,
                status=JobStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
                rerun_of_job_id=rerun_of_job_id,
            )
            self._jobs[job.id] = job
            self._next_job_id += 1
            return job

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_job_running(self, job_id: int) -> None:
        from datetime import datetime, timezone

        with self._lock:
            job = self._jobs[job_id]
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)

    def mark_job_succeeded(self, job_id: int, result_message: str) -> None:
        from datetime import datetime, timezone

        with self._lock:
            job = self._jobs[job_id]
            job.status = JobStatus.SUCCEEDED
            job.finished_at = datetime.now(timezone.utc)
            job.result_message = result_message

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
        self.mark_job_succeeded(job_id, result_message)
        with self._lock:
            job = self._jobs[job_id]
            job.processing_mode = processing_mode
            job.input_bytes = input_bytes
            job.output_bytes = output_bytes
            job.duration_ms = duration_ms

    def mark_job_failed(self, job_id: int, error_message: str) -> None:
        from datetime import datetime, timezone

        with self._lock:
            job = self._jobs[job_id]
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = error_message

    def requeue_incomplete_jobs(self) -> list[JobRecord]:
        from dataclasses import replace

        with self._lock:
            jobs: list[JobRecord] = []
            for job in self._jobs.values():
                if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                    job.status = JobStatus.QUEUED
                    job.started_at = None
                    job.finished_at = None
                    job.result_message = None
                    job.error_message = None
                    job.processing_mode = None
                    job.input_bytes = None
                    job.output_bytes = None
                    job.duration_ms = None
                    jobs.append(replace(job))
            return sorted(jobs, key=lambda item: item.id)

    def count_active_jobs_for_user(self, user_id: int) -> int:
        with self._lock:
            return sum(
                1
                for job in self._jobs.values()
                if job.user_id == user_id and job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
            )

    def list_top_users(self, limit: int = 5, since_days: int = 7) -> list[AdminUserStat]:
        del since_days
        with self._lock:
            counts: dict[int, int] = {}
            for user_id, _action in self._completed_actions:
                counts[user_id] = counts.get(user_id, 0) + 1
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [
            AdminUserStat(
                user_id=user_id,
                label=f"Utente {user_id}",
                completed_actions=completed_actions,
            )
            for user_id, completed_actions in ranked
        ]

    def list_failed_actions(
        self,
        limit: int = 5,
        since_days: int = 7,
        since_minutes: int | None = None,
    ) -> list[AdminActionStat]:
        from datetime import datetime, timedelta, timezone

        with self._lock:
            counts: dict[str, int] = {}
            for job in self._jobs.values():
                if job.status != JobStatus.FAILED:
                    continue
                if since_minutes is not None:
                    threshold = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
                    if (job.finished_at or job.created_at) < threshold:
                        continue
                elif since_days is not None:
                    threshold = datetime.now(timezone.utc) - timedelta(days=since_days)
                    if (job.finished_at or job.created_at) < threshold:
                        continue
                counts[job.action] = counts.get(job.action, 0) + 1
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return [AdminActionStat(action=action, total=total) for action, total in ranked]

    def list_user_jobs(
        self,
        user_id: int,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
    ) -> list[JobRecord]:
        with self._lock:
            jobs = [job for job in self._jobs.values() if job.user_id == user_id]
            if statuses is not None:
                allowed = set(statuses)
                jobs = [job for job in jobs if job.status in allowed]
            jobs.sort(
                key=lambda job: (
                    job.finished_at or job.created_at,
                    job.id,
                ),
                reverse=True,
            )
            return jobs[:limit]

    def list_recent_jobs(
        self,
        limit: int = 5,
        statuses: tuple[JobStatus, ...] | None = None,
        since_days: int | None = None,
        since_minutes: int | None = None,
    ) -> list[JobRecord]:
        from datetime import datetime, timedelta, timezone

        with self._lock:
            jobs = list(self._jobs.values())
            if statuses is not None:
                allowed = set(statuses)
                jobs = [job for job in jobs if job.status in allowed]
            if since_minutes is not None:
                threshold = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
                jobs = [job for job in jobs if (job.finished_at or job.created_at) >= threshold]
            elif since_days is not None:
                threshold = datetime.now(timezone.utc) - timedelta(days=since_days)
                jobs = [job for job in jobs if (job.finished_at or job.created_at) >= threshold]
            jobs.sort(
                key=lambda job: (
                    job.finished_at or job.created_at,
                    job.id,
                ),
                reverse=True,
            )
            return jobs[:limit]

    def list_stale_running_jobs(self, max_age_seconds: int, limit: int = 20) -> list[JobRecord]:
        from datetime import datetime, timedelta, timezone

        threshold = datetime.now(timezone.utc) - timedelta(seconds=max(0, max_age_seconds))
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if job.status == JobStatus.RUNNING and job.started_at is not None and job.started_at < threshold
            ]
            jobs.sort(key=lambda job: (job.started_at or job.created_at, job.id))
            return jobs[:limit]

    def requeue_stale_running_jobs(self, max_age_seconds: int) -> list[JobRecord]:
        from dataclasses import replace

        stale_jobs = self.list_stale_running_jobs(max_age_seconds=max_age_seconds, limit=1000)
        with self._lock:
            for stale_job in stale_jobs:
                job = self._jobs[stale_job.id]
                job.status = JobStatus.QUEUED
                job.started_at = None
                job.finished_at = None
                job.error_message = None
                job.result_message = None
                job.processing_mode = None
                job.input_bytes = None
                job.output_bytes = None
                job.duration_ms = None
            return [replace(self._jobs[job.id]) for job in stale_jobs]

    def prune_finished_jobs(self, retention_days: int) -> int:
        from datetime import datetime, timedelta, timezone

        threshold = datetime.now(timezone.utc) - timedelta(days=max(0, retention_days))
        with self._lock:
            prune_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}
                and (job.finished_at or job.created_at) < threshold
            ]
            for job_id in prune_ids:
                self._jobs.pop(job_id, None)
            return len(prune_ids)

    def append_audit_log_entry(
        self,
        event_type: str,
        *,
        actor_user_id: int | None,
        outcome: str,
        target_user_id: int | None = None,
        detail: str = "",
    ) -> AuditLogEntry:
        from datetime import datetime, timezone

        with self._lock:
            entry = AuditLogEntry(
                id=self._next_audit_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                outcome=outcome,
                detail=detail,
                created_at=datetime.now(timezone.utc),
            )
            self._audit_entries.append(entry)
            self._next_audit_id += 1
            return entry

    def list_audit_log_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        with self._lock:
            return list(reversed(self._audit_entries))[:limit]


def _safe_average(values) -> int:
    collected = [int(value) for value in values if value is not None]
    if not collected:
        return 0
    return sum(collected) // len(collected)
