from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.config import Settings, load_settings


class SettingsEnvParsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.previous_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.previous_env)
        self.temp_dir.cleanup()

    def _set_base_env(self) -> None:
        os.environ["DOCMOLDER_TELEGRAM_TOKEN"] = "test-token"
        os.environ["DOCMOLDER_RUNTIME_DIR"] = str(self.runtime_dir)
        os.environ["DOCMOLDER_DATABASE_PATH"] = str(self.runtime_dir / "docmolder.db")
        os.environ["DOCMOLDER_SQLITE_BACKUP_DIR"] = str(self.runtime_dir / "backups")

    def test_empty_id_lists_are_accepted(self) -> None:
        self._set_base_env()
        os.environ["DOCMOLDER_ALLOWED_USER_IDS"] = ""
        os.environ["DOCMOLDER_ADMIN_USER_IDS"] = ""

        settings = Settings()

        self.assertEqual(settings.allowed_user_ids, [])
        self.assertEqual(settings.admin_user_ids, [])

    def test_comma_separated_id_lists_are_accepted(self) -> None:
        self._set_base_env()
        os.environ["DOCMOLDER_ALLOWED_USER_IDS"] = "1, 2,3"
        os.environ["DOCMOLDER_ADMIN_USER_IDS"] = "7"

        settings = Settings()

        self.assertEqual(settings.allowed_user_ids, [1, 2, 3])
        self.assertEqual(settings.admin_user_ids, [7])

    def test_job_history_retention_defaults_to_30_days_and_is_configurable(self) -> None:
        self._set_base_env()

        default_settings = Settings()

        self.assertEqual(default_settings.job_history_retention_days, 30)

        os.environ["DOCMOLDER_JOB_HISTORY_RETENTION_DAYS"] = "14"

        custom_settings = Settings()

        self.assertEqual(custom_settings.job_history_retention_days, 14)

    def test_id_list_parser_accepts_lists_and_rejects_unknown_types(self) -> None:
        self.assertEqual(Settings._parse_id_list([1, "2"], "DOCMOLDER_ALLOWED_USER_IDS"), [1, 2])
        with self.assertRaisesRegex(TypeError, "DOCMOLDER_ALLOWED_USER_IDS"):
            Settings._parse_id_list({"id": 1}, "DOCMOLDER_ALLOWED_USER_IDS")

    def test_load_settings_creates_runtime_directories(self) -> None:
        self._set_base_env()

        settings = load_settings()

        self.assertTrue((settings.runtime_dir / "sessions").is_dir())
        self.assertTrue((settings.runtime_dir / "jobs").is_dir())
        self.assertTrue(settings.database_path.parent.is_dir())
        self.assertTrue(settings.sqlite_backup_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
