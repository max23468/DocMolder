from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.processing import DocumentProcessor


class DocumentProcessorCleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        (self.runtime_dir / "jobs").mkdir(parents=True, exist_ok=True)
        self.processor = DocumentProcessor(self.runtime_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cleanup_stale_job_dirs_removes_only_old_directories(self) -> None:
        stale_dir = self.runtime_dir / "jobs" / "stale_job"
        fresh_dir = self.runtime_dir / "jobs" / "fresh_job"
        stale_dir.mkdir()
        fresh_dir.mkdir()

        old_timestamp = (datetime.now() - timedelta(hours=8)).timestamp()
        os.utime(stale_dir, (old_timestamp, old_timestamp))

        removed_count = self.processor.cleanup_stale_job_dirs(max_age_hours=6)

        self.assertEqual(removed_count, 1)
        self.assertFalse(stale_dir.exists())
        self.assertTrue(fresh_dir.exists())


if __name__ == "__main__":
    unittest.main()
