from __future__ import annotations

import tempfile
import unittest
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
        self.assertEqual(queued_stats["jobs_queued"], 1)
        self.assertEqual(queued_stats["jobs_running"], 0)
        self.assertEqual(queued_stats["jobs_failed"], 0)

        self.store.mark_job_running(job.id)
        running_job = self.store.get_job(job.id)
        self.assertIsNotNone(running_job)
        self.assertEqual(running_job.status.value, "running")
        self.assertIsNotNone(running_job.started_at)

        running_stats = self.store.build_admin_stats()
        self.assertEqual(running_stats["jobs_queued"], 0)
        self.assertEqual(running_stats["jobs_running"], 1)

        self.store.mark_job_succeeded(job.id, "Operazione completata.")
        succeeded_job = self.store.get_job(job.id)
        self.assertIsNotNone(succeeded_job)
        self.assertEqual(succeeded_job.status.value, "succeeded")
        self.assertEqual(succeeded_job.result_message, "Operazione completata.")
        self.assertIsNotNone(succeeded_job.finished_at)

        final_stats = self.store.build_admin_stats()
        self.assertEqual(final_stats["jobs_queued"], 0)
        self.assertEqual(final_stats["jobs_running"], 0)
        self.assertEqual(final_stats["jobs_failed"], 0)

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

        requeued_jobs = self.store.requeue_incomplete_jobs()

        self.assertEqual([job.id for job in requeued_jobs], [first_job.id, second_job.id])
        requeued_second_job = self.store.get_job(second_job.id)
        self.assertIsNotNone(requeued_second_job)
        self.assertEqual(requeued_second_job.status.value, "queued")
        self.assertIsNone(requeued_second_job.started_at)

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
        recent_failed_jobs = self.store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
        recent_completed_jobs = self.store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))

        self.assertEqual(top_users[0].user_id, 10)
        self.assertEqual(top_users[0].completed_actions, 2)
        self.assertTrue(top_users[0].label in {"@mario", "mario"})
        self.assertEqual(recent_failed_jobs[0].id, failed_job.id)
        self.assertEqual(recent_completed_jobs[0].id, success_job.id)


if __name__ == "__main__":
    unittest.main()
