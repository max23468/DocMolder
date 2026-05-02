from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.config import Settings
from docmolder.healthcheck import (
    _directory_size_bytes,
    _disk_usage,
    _load_average,
    _memory_info,
    build_health_report,
    main,
    render_text_report,
)
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
        self.store = SQLiteSessionStore(self.database_path)
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

    def test_build_health_report_alerts_on_growth_guardrails(self) -> None:
        for index in range(3):
            job = self.store.create_job(
                user_id=index + 1,
                chat_id=10,
                reply_to_message_id=None,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore")
            self.store.record_completed_action(index + 1, "pdf_compress")

        report = build_health_report(
            self.settings,
            max_database_bytes=1,
            max_finished_jobs_24h=2,
            max_active_users_7d=2,
            max_failure_rate_percent=50,
            failure_rate_min_finished_jobs=2,
        )

        self.assertFalse(report["ok"])
        self.assertIn("database_size_exceeded", report["alerts"])
        self.assertIn("finished_jobs_24h_exceeded", report["alerts"])
        self.assertIn("active_users_7d_exceeded", report["alerts"])
        self.assertIn("failure_rate_24h_exceeded", report["alerts"])
        self.assertEqual(report["jobs"]["failure_rate_last_24h_percent"], 100)

    def test_build_health_report_reports_missing_runtime_database_and_backup(self) -> None:
        missing_settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            runtime_dir=self.root / "missing-runtime",
            database_path=self.root / "missing-runtime" / "docmolder.db",
            sqlite_backup_dir=self.root / "missing-runtime" / "backups",
        )

        with patch("docmolder.healthcheck._disk_usage", return_value=None):
            report = build_health_report(missing_settings)

        self.assertFalse(report["ok"])
        self.assertIn("runtime_dir_missing", report["reasons"])
        self.assertIn("database_missing", report["reasons"])
        self.assertIn("backup_dir_missing", report["warnings"])
        self.assertIsNone(report["runtime"]["disk_free_bytes"])

    def test_build_health_report_flags_inactive_service(self) -> None:
        completed = subprocess.CompletedProcess(["systemctl"], 3, stdout="", stderr="")
        with patch("docmolder.healthcheck.subprocess.run", return_value=completed):
            report = build_health_report(self.settings, check_service_active=True, service_name="docmolder")

        self.assertFalse(report["ok"])
        self.assertEqual(report["service"]["active"], False)
        self.assertIn("service_inactive", report["alerts"])

    def test_build_health_report_treats_missing_systemctl_as_unknown_service_state(self) -> None:
        with patch("docmolder.healthcheck.subprocess.run", side_effect=FileNotFoundError("systemctl")):
            report = build_health_report(self.settings, check_service_active=True, service_name="docmolder")

        self.assertTrue(report["ok"])
        self.assertIsNone(report["service"]["active"])

    def test_system_helpers_handle_platform_and_filesystem_edges(self) -> None:
        class FakeStat:
            st_size = 5

        class FakeCandidate:
            def __init__(self, *, is_file: bool = True, raises: bool = False) -> None:
                self._is_file = is_file
                self._raises = raises

            def is_file(self) -> bool:
                return self._is_file

            def stat(self) -> FakeStat:
                if self._raises:
                    raise OSError("cannot stat")
                return FakeStat()

        class FakePath:
            def exists(self) -> bool:
                return True

            def rglob(self, pattern: str):
                return [
                    FakeCandidate(),
                    FakeCandidate(raises=True),
                    FakeCandidate(is_file=False),
                ]

        fake_path = FakePath()
        self.assertEqual(_directory_size_bytes(fake_path), 5)
        self.assertEqual(_directory_size_bytes(self.root / "missing-dir"), 0)

        with patch("docmolder.healthcheck.shutil.disk_usage", side_effect=OSError("disk unavailable")):
            self.assertIsNone(_disk_usage(self.runtime_dir))
        with patch("docmolder.healthcheck.os.getloadavg", side_effect=OSError("load unavailable")):
            self.assertIsNone(_load_average())

    def test_memory_info_parses_linux_meminfo_and_handles_invalid_data(self) -> None:
        meminfo_path = self.root / "meminfo"
        meminfo_path.write_text(
            "\n".join(
                [
                    "MemTotal:       1000 kB",
                    "MemAvailable:    250 kB",
                ]
            ),
            encoding="utf-8",
        )
        with patch("docmolder.healthcheck.Path", return_value=meminfo_path):
            parsed = _memory_info()

        self.assertEqual(parsed, {"total_bytes": 1_024_000, "available_bytes": 256_000, "used_bytes": 768_000})

        meminfo_path.write_text(
            "\n".join(
                [
                    "MemTotal:       1000 kB",
                    "MemFree:         100 kB",
                ]
            ),
            encoding="utf-8",
        )
        with patch("docmolder.healthcheck.Path", return_value=meminfo_path):
            fallback = _memory_info()

        self.assertEqual(fallback["available_bytes"], 102_400)

        meminfo_path.write_text("MemTotal: nope kB\n", encoding="utf-8")
        with patch("docmolder.healthcheck.Path", return_value=meminfo_path):
            self.assertIsNone(_memory_info())

        missing_meminfo_path = self.root / "missing-meminfo"
        with patch("docmolder.healthcheck.Path", return_value=missing_meminfo_path):
            self.assertIsNone(_memory_info())

    def test_render_text_report_includes_reasons_warnings_and_alerts(self) -> None:
        report = build_health_report(self.settings, max_database_bytes=1)

        text = render_text_report(report)

        self.assertIn("status: fail", text)
        self.assertIn("database_size_exceeded", text)
        self.assertIn("warnings: none", text)
        self.assertIn("jobs_failure_rate_last_24h_percent", text)

    def test_main_prints_json_report_and_returns_failure_status(self) -> None:
        report = {
            "ok": False,
            "status": "fail",
            "reasons": ["database_missing"],
            "warnings": [],
            "alerts": [],
            "service": {"checked": False},
            "runtime": {},
            "system": {},
            "database": {},
            "backup": {},
            "jobs": {},
        }
        stdout = io.StringIO()
        with patch("docmolder.healthcheck.Settings", return_value=self.settings), patch(
            "docmolder.healthcheck.build_health_report", return_value=report
        ):
            with redirect_stdout(stdout):
                exit_code = main(["--json", "--max-queued-jobs", "1"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["reasons"], ["database_missing"])


if __name__ == "__main__":
    unittest.main()
