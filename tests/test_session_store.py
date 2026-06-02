from __future__ import annotations

import tempfile
import unittest
import warnings
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import gc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.session_store import InMemorySessionStore, SQLiteSessionStore
from docmolder.models import JobStatus
from docmolder.sqlite_session_store import _build_since_window_condition, _job_from_row, _safe_average


class SQLiteSessionStoreJobsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "docmolder.db"
        self.store = SQLiteSessionStore(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_job_lifecycle_updates_admin_stats(self) -> None:
        job = self.store.create_job(
            user_id=123,
            chat_id=456,
            reply_to_message_id=789,
            action="images_to_pdf",
            payload_json='{"files": []}',
        )

        queued_stats = self.store.build_admin_stats()
        self.assertEqual(queued_stats.jobs_queued, 1)
        self.assertEqual(queued_stats.jobs_running, 0)
        self.assertEqual(queued_stats.jobs_failed, 0)

        self.store.mark_job_running(job.id)
        running_job = self.store.get_job(job.id)
        self.assertIsNotNone(running_job)
        self.assertEqual(running_job.status.value, "running")
        self.assertIsNotNone(running_job.started_at)

        running_stats = self.store.build_admin_stats()
        self.assertEqual(running_stats.jobs_queued, 0)
        self.assertEqual(running_stats.jobs_running, 1)

        self.store.mark_job_succeeded_with_metrics(
            job.id,
            "Operazione completata.",
            processing_mode="raster",
            input_bytes=4000,
            output_bytes=1500,
            duration_ms=900,
        )
        succeeded_job = self.store.get_job(job.id)
        self.assertIsNotNone(succeeded_job)
        self.assertEqual(succeeded_job.status.value, "succeeded")
        self.assertEqual(succeeded_job.result_message, "Operazione completata.")
        self.assertIsNotNone(succeeded_job.finished_at)
        self.assertEqual(succeeded_job.processing_mode, "raster")
        self.assertEqual(succeeded_job.input_bytes, 4000)
        self.assertEqual(succeeded_job.output_bytes, 1500)
        self.assertEqual(succeeded_job.duration_ms, 900)

        final_stats = self.store.build_admin_stats()
        self.assertEqual(final_stats.jobs_queued, 0)
        self.assertEqual(final_stats.jobs_running, 0)
        self.assertEqual(final_stats.jobs_failed, 0)
        self.assertEqual(final_stats.jobs_succeeded, 1)
        self.assertEqual(final_stats.jobs_finished_last_24h, 1)
        self.assertEqual(final_stats.jobs_failed_last_24h, 0)
        self.assertEqual(final_stats.raster_results_total, 1)
        self.assertEqual(final_stats.avg_duration_ms, 900)
        self.assertEqual(final_stats.avg_input_bytes, 4000)
        self.assertEqual(final_stats.avg_output_bytes, 1500)

    def test_requeue_incomplete_jobs_resets_running_jobs(self) -> None:
        first_job = self.store.create_job(
            user_id=1,
            chat_id=10,
            reply_to_message_id=None,
            action="pdf_merge",
            payload_json='{"files": []}',
        )
        second_job = self.store.create_job(
            user_id=2,
            chat_id=20,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_running(second_job.id)
        running_job = self.store.get_job(second_job.id)
        self.assertIsNotNone(running_job)
        running_job.finished_at = running_job.created_at
        running_job.error_message = "Errore vecchio"
        running_job.processing_mode = "raster"
        running_job.input_bytes = 200
        running_job.output_bytes = 100
        running_job.duration_ms = 50

        requeued_jobs = self.store.requeue_incomplete_jobs()

        self.assertEqual([job.id for job in requeued_jobs], [first_job.id, second_job.id])
        requeued_second_job = self.store.get_job(second_job.id)
        self.assertIsNotNone(requeued_second_job)
        self.assertEqual(requeued_second_job.status.value, "queued")
        self.assertIsNone(requeued_second_job.started_at)
        self.assertIsNone(requeued_second_job.finished_at)
        self.assertIsNone(requeued_second_job.error_message)
        self.assertIsNone(requeued_second_job.processing_mode)
        self.assertIsNone(requeued_second_job.input_bytes)
        self.assertIsNone(requeued_second_job.output_bytes)
        self.assertIsNone(requeued_second_job.duration_ms)

    def test_meta_store_roundtrip(self) -> None:
        self.assertIsNone(self.store.get_meta("admin_report_daily_last_sent"))

        self.store.set_meta("admin_report_daily_last_sent", "2026-04-06")

        self.assertEqual(self.store.get_meta("admin_report_daily_last_sent"), "2026-04-06")

    def test_store_operations_do_not_leak_sqlite_connections(self) -> None:
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always", ResourceWarning)

            self.store.set_meta("admin_report_daily_last_sent", "2026-04-06")
            self.assertEqual(self.store.get_meta("admin_report_daily_last_sent"), "2026-04-06")

            gc.collect()

        sqlite_warnings = [
            warning for warning in recorded if isinstance(warning.message, ResourceWarning) and "sqlite3.Connection" in str(warning.message)
        ]
        self.assertEqual(sqlite_warnings, [])

    def test_user_preference_roundtrip_and_clear(self) -> None:
        self.assertIsNone(self.store.get_user_preference(55, "compression_preset"))

        self.store.set_user_preference(55, "compression_preset", "medium")
        self.store.set_user_preference(55, "image_pdf_layout", "a4")

        self.assertEqual(self.store.get_user_preference(55, "compression_preset"), "medium")
        self.assertEqual(self.store.get_user_preference(55, "image_pdf_layout"), "a4")

        self.store.clear_user_preferences(55)

        self.assertIsNone(self.store.get_user_preference(55, "compression_preset"))
        self.assertIsNone(self.store.get_user_preference(55, "image_pdf_layout"))

    def test_user_preset_roundtrip_and_clear(self) -> None:
        self.assertIsNone(self.store.get_user_preset(55, "compression_preset"))

        self.store.set_user_preset(55, "compression_preset", "medium")
        self.store.set_user_preset(55, "image_pdf_layout", "a4")

        self.assertEqual(self.store.get_user_preset(55, "compression_preset"), "medium")
        self.assertEqual(self.store.get_user_preset(55, "image_pdf_layout"), "a4")

        self.store.clear_user_presets(55)

        self.assertIsNone(self.store.get_user_preset(55, "compression_preset"))
        self.assertIsNone(self.store.get_user_preset(55, "image_pdf_layout"))

    def test_delete_removes_session_files(self) -> None:
        from docmolder.action_catalog import build_session_file
        from docmolder.models import FileKind, UserSession

        self.store.save(
            UserSession(
                user_id=55,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )

        self.store.delete(55)

        with self.store._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM session_files WHERE user_id = 55").fetchone()
        self.assertEqual(int(row["total"]), 0)

    def test_delete_user_data_removes_live_user_records_and_scrubs_audit(self) -> None:
        from docmolder.action_catalog import build_session_file
        from docmolder.models import FileKind, UserSession

        self.store.save(
            UserSession(
                user_id=55,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        self.store.register_user(55, "mario", "Mario", None)
        self.store.record_completed_action(55, "pdf_compress")
        self.store.set_user_preference(55, "compression_preset", "medium")
        self.store.set_user_preset(55, "compression_preset", "medium")
        self.store.set_meta("access:55:status", "approved")
        self.store.set_meta("upload_burst:55", "[1,2]")
        job = self.store.create_job(
            user_id=55,
            chat_id=99,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(job.id, "ok")
        self.store.append_audit_log_entry(
            "access_review",
            actor_user_id=7,
            target_user_id=55,
            outcome="approved",
            detail="callback:access:approve",
        )

        report = self.store.delete_user_data(55)

        self.assertEqual(report.sessions_deleted, 1)
        self.assertEqual(report.jobs_deleted, 1)
        self.assertEqual(report.usage_events_deleted, 1)
        self.assertEqual(report.known_users_deleted, 1)
        self.assertEqual(report.meta_deleted, 4)
        self.assertEqual(report.audit_entries_scrubbed, 1)
        self.assertIsNone(self.store.get(55))
        self.assertIsNone(self.store.get_job(job.id))
        self.assertIsNone(self.store.get_user_preference(55, "compression_preset"))
        self.assertIsNone(self.store.get_user_preset(55, "compression_preset"))
        self.assertIsNone(self.store.get_meta("access:55:status"))
        self.assertIsNone(self.store.get_meta("upload_burst:55"))
        audit_entry = self.store.list_audit_log_entries(limit=1)[0]
        self.assertEqual(audit_entry.actor_user_id, 7)
        self.assertIsNone(audit_entry.target_user_id)
        self.assertEqual(audit_entry.detail, "")

    def test_purge_expired_removes_only_expired_sessions(self) -> None:
        from docmolder.action_catalog import build_session_file
        from docmolder.models import FileKind, UserSession

        self.store.save(
            UserSession(
                user_id=10,
                files=[build_session_file("pdf-1", "vecchio.pdf", FileKind.PDF)],
            )
        )
        self.store.save(
            UserSession(
                user_id=11,
                files=[build_session_file("pdf-2", "nuovo.pdf", FileKind.PDF)],
            )
        )
        old_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
        with self.store._connect() as connection:
            connection.execute("UPDATE sessions SET updated_at = ? WHERE user_id = ?", (old_updated_at, 10))
            connection.commit()

        purged_ids = self.store.purge_expired(ttl_minutes=30)

        self.assertEqual(purged_ids, [10])
        self.assertIsNone(self.store.get(10))
        self.assertIsNotNone(self.store.get(11))
        with self.store._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM session_files WHERE user_id = ?", (10,)).fetchone()
        self.assertEqual(int(row["total"]), 0)

    def test_session_pending_action_roundtrip(self) -> None:
        from docmolder.models import UserSession

        session = UserSession(user_id=55, pending_action="pdf_extract_pages")
        self.store.save(session)

        loaded = self.store.get(55)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.pending_action, "pdf_extract_pages")

    def test_admin_lists_expose_top_users_and_recent_jobs(self) -> None:
        self.store.register_user(10, "mario", "Mario", "Rossi")
        self.store.register_user(20, None, "Luca", "Bianchi")
        self.store.record_completed_action(10, "images_to_pdf")
        self.store.record_completed_action(10, "pdf_merge")
        self.store.record_completed_action(20, "pdf_compress")

        failed_job = self.store.create_job(
            user_id=20,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")

        success_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="images_to_pdf",
            payload_json='{"files": []}',
        )
        self.store.mark_job_succeeded(success_job.id, "Completato")

        top_users = self.store.list_top_users(limit=5, since_days=7)
        failed_actions = self.store.list_failed_actions(limit=5, since_days=7)
        recent_failed_jobs = self.store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
        recent_completed_jobs = self.store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))

        self.assertEqual(top_users[0].user_id, 10)
        self.assertEqual(top_users[0].completed_actions, 2)
        self.assertTrue(top_users[0].label in {"@mario", "mario"})
        self.assertEqual(failed_actions[0].action, "pdf_compress")
        self.assertEqual(failed_actions[0].total, 1)
        self.assertEqual(recent_failed_jobs[0].id, failed_job.id)
        self.assertEqual(recent_completed_jobs[0].id, success_job.id)

    def test_list_user_jobs_returns_latest_jobs_for_user(self) -> None:
        job_one = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="images_to_pdf",
            payload_json='{"files": []}',
        )
        self.store.mark_job_succeeded(job_one.id, "Completato")
        job_two = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_failed(job_two.id, "Errore")
        self.store.create_job(
            user_id=99,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_merge",
            payload_json='{"files": []}',
        )

        jobs = self.store.list_user_jobs(10, limit=5)

        self.assertEqual([job.id for job in jobs], [job_two.id, job_one.id])

    def test_list_user_jobs_can_filter_by_status_and_count_active_jobs(self) -> None:
        queued_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="images_to_pdf",
            payload_json='{"files": []}',
        )
        running_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_running(running_job.id)
        failed_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_merge",
            payload_json='{"files": []}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore")

        filtered_jobs = self.store.list_user_jobs(10, limit=5, statuses=(JobStatus.QUEUED, JobStatus.RUNNING))

        self.assertEqual({job.id for job in filtered_jobs}, {queued_job.id, running_job.id})
        self.assertEqual(self.store.count_active_jobs_for_user(10), 2)

    def test_list_recent_jobs_can_filter_by_period(self) -> None:
        old_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="images_to_pdf",
            payload_json='{"files": []}',
        )
        self.store.mark_job_succeeded(old_job.id, "Vecchio")

        recent_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_succeeded(recent_job.id, "Recente")

        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.commit()

        jobs = self.store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,), since_days=7)

        self.assertEqual([job.id for job in jobs], [recent_job.id])

    def test_list_failed_actions_can_filter_by_recent_minutes(self) -> None:
        old_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_failed(old_job.id, "Vecchio")

        recent_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        self.store.mark_job_failed(recent_job.id, "Recente")

        old_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M:%S")
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.commit()

        failed_actions = self.store.list_failed_actions(limit=5, since_minutes=30)

        self.assertEqual(len(failed_actions), 1)
        self.assertEqual(failed_actions[0].action, "pdf_compress")
        self.assertEqual(failed_actions[0].total, 1)

    def test_create_job_persists_rerun_origin(self) -> None:
        source_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
        )
        rerun_job = self.store.create_job(
            user_id=10,
            chat_id=100,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files": []}',
            rerun_of_job_id=source_job.id,
        )

        loaded = self.store.get_job(rerun_job.id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.rerun_of_job_id, source_job.id)

    def test_audit_log_roundtrip(self) -> None:
        entry = self.store.append_audit_log_entry(
            "service_mode",
            actor_user_id=7,
            target_user_id=None,
            outcome="maintenance",
            detail="command:/pause",
        )

        entries = self.store.list_audit_log_entries(limit=5)

        self.assertIsNotNone(entry.id)
        self.assertEqual(entries[0].event_type, "service_mode")
        self.assertEqual(entries[0].actor_user_id, 7)
        self.assertEqual(entries[0].outcome, "maintenance")

    def test_requeue_stale_running_jobs(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=70,
            reply_to_message_id=None,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(job.id)
        with self.store._connect() as connection:
            connection.execute("UPDATE jobs SET started_at = datetime('now', '-2 hour') WHERE id = ?", (job.id,))
            connection.commit()

        requeued = self.store.requeue_stale_running_jobs(max_age_seconds=3600)

        self.assertEqual([item.id for item in requeued], [job.id])
        self.assertEqual(self.store.get_job(job.id).status, JobStatus.QUEUED)

    def test_prune_finished_jobs_removes_only_old_finished_jobs(self) -> None:
        old_job = self.store.create_job(
            user_id=7,
            chat_id=70,
            reply_to_message_id=None,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(old_job.id, "old")
        recent_job = self.store.create_job(
            user_id=7,
            chat_id=70,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(recent_job.id, "recent")
        running_job = self.store.create_job(
            user_id=7,
            chat_id=70,
            reply_to_message_id=None,
            action="pdf_merge",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(running_job.id)
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.execute(
                "UPDATE jobs SET created_at = ?, started_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, running_job.id),
            )
            connection.commit()

        pruned = self.store.prune_finished_jobs(retention_days=30)

        self.assertEqual(pruned, 1)
        self.assertIsNone(self.store.get_job(old_job.id))
        self.assertIsNotNone(self.store.get_job(recent_job.id))
        self.assertIsNotNone(self.store.get_job(running_job.id))

    def test_meta_delete_list_and_helper_functions(self) -> None:
        self.store.set_meta("admin:daily", "done")
        self.store.set_meta("admin:weekly", "queued")
        self.store.set_meta("other:value", "skip")

        self.assertEqual(self.store.list_meta("admin:"), {"admin:daily": "done", "admin:weekly": "queued"})
        self.store.delete_meta("admin:daily")
        self.assertIsNone(self.store.get_meta("admin:daily"))
        self.assertEqual(_safe_average([100, None, 200]), 150)
        self.assertEqual(_safe_average([None, None]), 0)
        self.assertEqual(_build_since_window_condition(column="created_at", since_days=7, since_minutes=None), ("created_at >= datetime('now', ?)", ["-7 day"]))
        self.assertEqual(
            _build_since_window_condition(column="created_at", since_days=7, since_minutes=15),
            ("created_at >= datetime('now', ?)", ["-15 minute"]),
        )
        self.assertEqual(_build_since_window_condition(column="created_at", since_days=None, since_minutes=None), ("", []))

    def test_store_initialization_migrates_legacy_schema_and_legacy_rows(self) -> None:
        legacy_db_path = Path(self.temp_dir.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    reply_to_message_id INTEGER,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_message TEXT,
                    error_message TEXT
                );
                CREATE TABLE sessions (
                    user_id INTEGER PRIMARY KEY,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.commit()

        migrated_store = SQLiteSessionStore(legacy_db_path)
        with migrated_store._connect() as connection:
            job_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
            session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()}

        self.assertTrue({"processing_mode", "input_bytes", "output_bytes", "duration_ms", "rerun_of_job_id"} <= job_columns)
        self.assertIn("pending_action", session_columns)

        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE legacy_jobs (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    reply_to_message_id INTEGER,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result_message TEXT,
                    error_message TEXT
                );
                INSERT INTO legacy_jobs (
                    id,
                    user_id,
                    chat_id,
                    reply_to_message_id,
                    action,
                    payload_json,
                    status,
                    created_at,
                    started_at,
                    finished_at,
                    result_message,
                    error_message
                ) VALUES (
                    1,
                    7,
                    99,
                    NULL,
                    'pdf_compress',
                    '{"files":[]}',
                    'queued',
                    '2026-06-01 10:00:00',
                    NULL,
                    NULL,
                    NULL,
                    NULL
                );
                """
            )
            row = connection.execute("SELECT * FROM legacy_jobs").fetchone()

        job = _job_from_row(row)
        self.assertIsNone(job.rerun_of_job_id)
        self.assertIsNone(job.processing_mode)
        self.assertIsNone(job.input_bytes)
        self.assertIsNone(job.output_bytes)
        self.assertIsNone(job.duration_ms)


class InMemorySessionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemorySessionStore()

    def test_register_user_preferences_presets_and_meta_roundtrip(self) -> None:
        self.assertTrue(self.store.register_user(10, "mario", "Mario", "Rossi"))
        self.assertFalse(self.store.register_user(10, None, None, None))

        self.store.set_meta("admin:last", "ok")
        self.store.set_meta("other:last", "skip")
        self.store.set_user_preference(10, "compression", "medium")
        self.store.set_user_preset(10, "split", "zip")

        self.assertEqual(self.store.get_meta("admin:last"), "ok")
        self.assertEqual(self.store.list_meta("admin:"), {"admin:last": "ok"})
        self.assertEqual(self.store.get_user_preference(10, "compression"), "medium")
        self.assertEqual(self.store.get_user_preset(10, "split"), "zip")

        self.store.clear_user_preferences(10)
        self.store.clear_user_presets(10)

        self.assertIsNone(self.store.get_user_preference(10, "compression"))
        self.assertIsNone(self.store.get_user_preset(10, "split"))

    def test_delete_user_data_removes_live_records_and_scrubs_audit(self) -> None:
        from docmolder.models import UserSession

        self.store.save(UserSession(user_id=55))
        self.store.register_user(55, "mario", "Mario", None)
        self.store.record_completed_action(55, "pdf_compress")
        self.store.set_user_preference(55, "compression_preset", "medium")
        self.store.set_user_preset(55, "compression_preset", "medium")
        self.store.set_meta("access:55:status", "approved")
        self.store.set_meta("upload_burst:55", "[1,2]")
        job = self.store.create_job(55, 99, None, "pdf_compress", '{"files":[]}')
        self.store.mark_job_failed(job.id, "Errore")
        self.store.append_audit_log_entry(
            "access_review",
            actor_user_id=55,
            target_user_id=7,
            outcome="approved",
            detail="private detail",
        )

        report = self.store.delete_user_data(55)

        self.assertEqual(report.sessions_deleted, 1)
        self.assertEqual(report.jobs_deleted, 1)
        self.assertEqual(report.usage_events_deleted, 1)
        self.assertEqual(report.known_users_deleted, 1)
        self.assertEqual(report.meta_deleted, 4)
        self.assertEqual(report.audit_entries_scrubbed, 1)
        self.assertIsNone(self.store.get(55))
        self.assertIsNone(self.store.get_job(job.id))
        entry = self.store.list_audit_log_entries()[0]
        self.assertIsNone(entry.actor_user_id)
        self.assertEqual(entry.target_user_id, 7)
        self.assertEqual(entry.detail, "")

    def test_job_lists_stats_requeue_and_prune(self) -> None:
        from datetime import datetime, timedelta, timezone

        self.store.record_completed_action(1, "images_to_pdf")
        self.store.record_completed_action(1, "pdf_merge")
        self.store.record_completed_action(2, "pdf_compress")
        running_job = self.store.create_job(1, 10, None, "pdf_compress", "{}")
        self.store.mark_job_running(running_job.id)
        running = self.store.get_job(running_job.id)
        self.assertIsNotNone(running)
        running.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        running.error_message = "old"
        failed_job = self.store.create_job(2, 20, None, "pdf_compress", "{}")
        self.store.mark_job_failed(failed_job.id, "Errore")
        old_success = self.store.create_job(2, 20, None, "images_to_pdf", "{}")
        self.store.mark_job_succeeded_with_metrics(
            old_success.id,
            "ok",
            processing_mode="raster",
            input_bytes=100,
            output_bytes=50,
            duration_ms=20,
        )
        old_success_record = self.store.get_job(old_success.id)
        self.assertIsNotNone(old_success_record)
        old_success_record.finished_at = datetime.now(timezone.utc) - timedelta(days=40)

        stats = self.store.build_admin_stats()
        self.assertEqual(stats.active_users_last_7d, 2)
        self.assertEqual(stats.jobs_running, 1)
        self.assertEqual(stats.jobs_failed, 1)
        self.assertEqual(stats.raster_results_total, 1)
        self.assertEqual(stats.avg_duration_ms, 20)
        self.assertEqual(self.store.count_active_jobs_for_user(1), 1)
        self.assertEqual(self.store.list_top_users(limit=1)[0].user_id, 1)
        self.assertEqual(self.store.list_failed_actions(limit=1)[0].action, "pdf_compress")
        self.assertEqual(self.store.list_user_jobs(2, statuses=(JobStatus.FAILED,))[0].id, failed_job.id)
        self.assertEqual(self.store.list_recent_jobs(statuses=(JobStatus.FAILED,))[0].id, failed_job.id)
        self.assertEqual(self.store.list_stale_running_jobs(max_age_seconds=3600)[0].id, running_job.id)

        requeued = self.store.requeue_stale_running_jobs(max_age_seconds=3600)
        self.assertEqual([job.id for job in requeued], [running_job.id])
        self.assertEqual(self.store.get_job(running_job.id).status, JobStatus.QUEUED)

        pruned = self.store.prune_finished_jobs(retention_days=30)

        self.assertEqual(pruned, 1)
        self.assertIsNone(self.store.get_job(old_success.id))


if __name__ == "__main__":
    unittest.main()
