from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.config import Settings
from docmolder.models import JobStatus
from docmolder.reconcile import run_reconciliation
from docmolder.session_store import SQLiteSessionStore


class ReconcileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.database_path = self.runtime_dir / "docmolder.db"
        self.backup_dir = self.runtime_dir / "backups"
        (self.runtime_dir / "jobs").mkdir(parents=True)
        self.backup_dir.mkdir()
        self.store = SQLiteSessionStore(self.database_path)
        self.settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            runtime_dir=self.runtime_dir,
            database_path=self.database_path,
            sqlite_backup_dir=self.backup_dir,
            stale_job_retention_hours=1,
            ghostscript_timeout_seconds=120,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reconciliation_requeues_stale_running_jobs_and_cleans_runtime(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=8,
            reply_to_message_id=None,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(job.id)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("UPDATE jobs SET started_at = datetime('now', '-2 hour') WHERE id = ?", (job.id,))
            connection.commit()

        stale_dir = self.runtime_dir / "jobs" / "old-job"
        stale_dir.mkdir()
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=3)).timestamp()
        os.utime(stale_dir, (stale_time, stale_time))

        report = run_reconciliation(self.settings, stale_running_age_seconds=3600)

        self.assertEqual(report["requeued_stale_running_jobs"], 1)
        self.assertFalse(stale_dir.exists())
        self.assertEqual(self.store.get_job(job.id).status, JobStatus.QUEUED)


if __name__ == "__main__":
    unittest.main()
