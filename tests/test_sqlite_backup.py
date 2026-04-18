from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.sqlite_backup import backup_sqlite_database, restore_sqlite_database


class SQLiteBackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "docmolder.db"
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as connection:
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
        with sqlite3.connect(backup_path) as connection:
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

        with sqlite3.connect(self.db_path) as connection:
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
        with sqlite3.connect(self.db_path) as connection:
            values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(values, [("prima",)])
        with sqlite3.connect(previous_backup_path) as connection:
            previous_values = connection.execute("SELECT value FROM demo").fetchall()
        self.assertEqual(previous_values, [("modificata",)])


if __name__ == "__main__":
    unittest.main()
