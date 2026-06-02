from __future__ import annotations

import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.sqlite_backup import backup_sqlite_database, main, restore_sqlite_database


class SQLiteBackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "docmolder.db"
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO demo (value) VALUES (?)", ("prima",))
            connection.commit()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_backup_sqlite_database_creates_verified_backup(self) -> None:
        backup_path = backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=7,
            timestamp=datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(backup_path.exists())
        with closing(sqlite3.connect(backup_path)) as connection:
            values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(values, [("prima",)])

    def test_backup_sqlite_database_prunes_old_backups(self) -> None:
        old_backup = self.backup_dir / "docmolder-20260410-210000.db.backup"
        old_backup.write_bytes(b"old")
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=15)).timestamp()
        os.utime(old_backup, (stale_timestamp, stale_timestamp))

        backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=7,
            timestamp=datetime.now(timezone.utc),
        )

        self.assertFalse(old_backup.exists())

    def test_restore_sqlite_database_replaces_database_and_keeps_previous_copy(self) -> None:
        backup_path = backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=7,
            timestamp=datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
        )

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM demo")
            connection.execute("INSERT INTO demo (value) VALUES (?)", ("modificata",))
            connection.commit()

        previous_backup_path = restore_sqlite_database(
            backup_path,
            self.db_path,
            timestamp=datetime(2026, 4, 18, 21, 5, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(previous_backup_path)
        self.assertTrue(previous_backup_path.exists())
        with closing(sqlite3.connect(self.db_path)) as connection:
            values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(values, [("prima",)])
        with closing(sqlite3.connect(previous_backup_path)) as connection:
            previous_values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(previous_values, [("modificata",)])

    def test_backup_sqlite_database_rejects_missing_database(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Database non trovato"):
            backup_sqlite_database(self.root / "missing.db", self.backup_dir)

    def test_backup_sqlite_database_keeps_old_backups_when_retention_is_negative(self) -> None:
        old_backup = self.backup_dir / "docmolder-20260410-210000.db.backup"
        old_backup.write_bytes(b"old")
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        os.utime(old_backup, (stale_timestamp, stale_timestamp))

        backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=-1,
            timestamp=datetime.now(timezone.utc),
        )

        self.assertTrue(old_backup.exists())

    def test_restore_sqlite_database_can_create_target_without_previous_copy(self) -> None:
        backup_path = backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=7,
            timestamp=datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
        )
        restored_path = self.root / "restored" / "docmolder.db"

        previous_backup_path = restore_sqlite_database(backup_path, restored_path)

        self.assertIsNone(previous_backup_path)
        with closing(sqlite3.connect(restored_path)) as connection:
            values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(values, [("prima",)])

    def test_restore_sqlite_database_rejects_missing_backup(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Backup SQLite non trovato"):
            restore_sqlite_database(self.root / "missing.backup", self.db_path)

    def test_backup_sqlite_database_removes_invalid_backup_when_validation_fails(self) -> None:
        with patch("docmolder.sqlite_backup._validate_sqlite_database", side_effect=RuntimeError("bad backup")):
            with self.assertRaisesRegex(RuntimeError, "bad backup"):
                backup_sqlite_database(self.db_path, self.backup_dir)

    def test_main_prints_backup_path(self) -> None:
        stdout = io.StringIO()
        with patch.object(
            sys,
            "argv",
            [
                "docmolder-sqlite-backup",
                "backup",
                "--db-path",
                str(self.db_path),
                "--backup-dir",
                str(self.backup_dir),
                "--retention-days",
                "7",
            ],
        ):
            with redirect_stdout(stdout):
                main()

        self.assertTrue(Path(stdout.getvalue().strip()).exists())

    def test_main_prints_previous_backup_path_on_restore(self) -> None:
        backup_path = backup_sqlite_database(
            self.db_path,
            self.backup_dir,
            retention_days=7,
            timestamp=datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
        )
        stdout = io.StringIO()

        with patch.object(
            sys,
            "argv",
            [
                "docmolder-sqlite-backup",
                "restore",
                "--backup-path",
                str(backup_path),
                "--db-path",
                str(self.db_path),
            ],
        ):
            with redirect_stdout(stdout):
                main()

        self.assertIn("before-restore", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
