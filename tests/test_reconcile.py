from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.config import Settings
from docmolder.models import JobStatus
from docmolder.reconcile import main, render_text_report, run_reconciliation
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
            job_history_retention_days=30,
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

    def test_reconciliation_prunes_finished_jobs_using_settings_by_default(self) -> None:
        old_job = self.store.create_job(
            user_id=7,
            chat_id=8,
            reply_to_message_id=None,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(old_job.id, "old")
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.commit()

        report = run_reconciliation(self.settings, stale_running_age_seconds=None, cleanup_runtime=False)

        self.assertEqual(report["pruned_finished_jobs"], 1)
        self.assertEqual(report["prune_finished_days"], 30)
        self.assertIsNone(self.store.get_job(old_job.id))

    def test_reconciliation_can_disable_finished_job_pruning(self) -> None:
        old_job = self.store.create_job(
            user_id=7,
            chat_id=8,
            reply_to_message_id=None,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(old_job.id, "old")
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.commit()

        report = run_reconciliation(
            self.settings,
            stale_running_age_seconds=None,
            prune_finished=False,
            cleanup_runtime=False,
        )

        self.assertEqual(report["pruned_finished_jobs"], 0)
        self.assertIsNotNone(self.store.get_job(old_job.id))

    def test_reconciliation_no_prune_finished_overrides_explicit_prune_days(self) -> None:
        old_job = self.store.create_job(7, 99, None, "pdf_compress", "{}")
        self.store.mark_job_succeeded(old_job.id, "Completato")
        old_timestamp = "2000-01-01T00:00:00+00:00"
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?",
                (old_timestamp, old_timestamp, old_job.id),
            )
            connection.commit()

        report = run_reconciliation(
            self.settings,
            stale_running_age_seconds=None,
            prune_finished_days=7,
            prune_finished=False,
            cleanup_runtime=False,
        )

        self.assertEqual(report["pruned_finished_jobs"], 0)
        self.assertIsNone(report["prune_finished_days"])
        self.assertIsNotNone(self.store.get_job(old_job.id))

    def test_reconciliation_uses_explicit_prune_days_and_can_skip_cleanup(self) -> None:
        report = run_reconciliation(
            self.settings,
            stale_running_age_seconds=None,
            prune_finished_days=7,
            cleanup_runtime=False,
        )

        self.assertEqual(report["requeued_stale_running_jobs"], 0)
        self.assertEqual(report["removed_job_dirs"], 0)
        self.assertEqual(report["prune_finished_days"], 7)
        self.assertEqual(self.store.get_meta("reconcile:last_prune_finished_days"), "7")

    def test_render_text_report_summarizes_reconciliation(self) -> None:
        report = {
            "requeued_stale_running_jobs": 1,
            "removed_job_dirs": 2,
            "pruned_finished_jobs": 3,
            "prune_finished_days": None,
            "health_status": "ok",
        }

        text = render_text_report(report)

        self.assertIn("reconciliation ok", text)
        self.assertIn("requeued_stale_running_jobs=1", text)
        self.assertIn("prune_finished_days=None", text)

    def test_main_prints_json_report(self) -> None:
        report = {
            "ok": True,
            "requeued_stale_running_jobs": 0,
            "requeued_job_ids": [],
            "removed_job_dirs": 0,
            "pruned_finished_jobs": 0,
            "prune_finished_days": None,
            "health_status": "ok",
            "health_warnings": [],
        }
        stdout = io.StringIO()
        with patch("docmolder.reconcile.Settings", return_value=self.settings), patch(
            "docmolder.reconcile.run_reconciliation", return_value=report
        ) as run:
            with redirect_stdout(stdout):
                exit_code = main(["--json", "--stale-running-age-seconds", "0", "--no-prune-finished", "--no-cleanup-runtime"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["health_status"], "ok")
        self.assertIsNone(run.call_args.kwargs["stale_running_age_seconds"])
        self.assertFalse(run.call_args.kwargs["prune_finished"])
        self.assertFalse(run.call_args.kwargs["cleanup_runtime"])

    def test_main_returns_failure_when_report_is_not_ok(self) -> None:
        report = {
            "ok": False,
            "requeued_stale_running_jobs": 0,
            "removed_job_dirs": 0,
            "pruned_finished_jobs": 0,
            "prune_finished_days": 30,
            "health_status": "fail",
        }
        stdout = io.StringIO()
        with patch("docmolder.reconcile.Settings", return_value=self.settings), patch(
            "docmolder.reconcile.run_reconciliation", return_value=report
        ):
            with redirect_stdout(stdout):
                exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("health_status=fail", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
