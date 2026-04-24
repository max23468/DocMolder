from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.config import Settings
from docmolder.healthcheck import build_health_report
from docmolder.session_store import SQLiteSessionStore


class HealthcheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_dir = self.root / "runtime"
        self.database_path = self.runtime_dir / "docmolder.db"
        self.backup_dir = self.runtime_dir / "backups"
        self.runtime_dir.mkdir(parents=True)
        (self.runtime_dir / "jobs").mkdir()
        self.backup_dir.mkdir()
        (self.backup_dir / "docmolder.db.backup").write_text("backup", encoding="utf-8")
        SQLiteSessionStore(self.database_path)
        self.settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            runtime_dir=self.runtime_dir,
            database_path=self.database_path,
            sqlite_backup_dir=self.backup_dir,
            health_max_queued_jobs=20,
            health_max_running_jobs=5,
            health_max_running_job_age_seconds=3600,
            health_max_runtime_dir_bytes=1024 * 1024,
            health_max_backup_age_seconds=3600,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_health_report_reports_ok_runtime(self) -> None:
        report = build_health_report(self.settings)

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["runtime"]["writable"])
        self.assertTrue(report["database"]["integrity_ok"])
        self.assertIn("system", report)

    def test_build_health_report_alerts_on_low_disk_high_load_and_low_memory(self) -> None:
        with (
            patch("docmolder.healthcheck._disk_usage", return_value=(1000, 950, 50)),
            patch("docmolder.healthcheck._cpu_count", return_value=2),
            patch("docmolder.healthcheck._load_average", return_value=(5.0, 4.0, 3.0)),
            patch(
                "docmolder.healthcheck._memory_info",
                return_value={"total_bytes": 2000, "used_bytes": 1900, "available_bytes": 100},
            ),
        ):
            report = build_health_report(
                self.settings,
                min_disk_free_bytes=100,
                min_disk_free_percent=10,
                max_load_per_cpu=2.0,
                min_memory_available_bytes=500,
            )

        self.assertFalse(report["ok"])
        self.assertIn("disk_free_bytes_below_min", report["alerts"])
        self.assertIn("disk_free_percent_below_min", report["alerts"])
        self.assertIn("load_average_exceeded", report["alerts"])
        self.assertIn("memory_available_below_min", report["alerts"])


if __name__ == "__main__":
    unittest.main()
