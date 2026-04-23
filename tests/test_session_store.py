from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.session_store import SQLiteSessionStore
from docmolder.models import JobStatus


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

    def test_user_preference_roundtrip_and_clear(self) -> None:
        self.assertIsNone(self.store.get_user_preference(55, "compression_preset"))

        self.store.set_user_preference(55, "compression_preset", "medium")
        self.store.set_user_preference(55, "image_pdf_layout", "a4")

        self.assertEqual(self.store.get_user_preference(55, "compression_preset"), "medium")
        self.assertEqual(self.store.get_user_preference(55, "image_pdf_layout"), "a4")

        self.store.clear_user_preferences(55)

        self.assertIsNone(self.store.get_user_preference(55, "compression_preset"))
        self.assertIsNone(self.store.get_user_preference(55, "image_pdf_layout"))

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


if __name__ == "__main__":
    unittest.main()
