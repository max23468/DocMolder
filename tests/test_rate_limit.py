from __future__ import annotations

import tempfile
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import BotDependencies, _consume_upload_slot, _has_capacity_for_new_job
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.session_store import InMemorySessionStore


class RateLimitHelpersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        runtime_dir = Path(self.temp_dir.name) / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            session_ttl_minutes=30,
            max_session_files=20,
            max_file_size_mb=20,
            upload_burst_limit=2,
            upload_burst_window_seconds=30,
            max_active_jobs_per_user=2,
            cleanup_interval_minutes=30,
            stale_job_retention_hours=6,
            telegram_brand_sync_enabled=True,
            runtime_dir=runtime_dir,
            database_path=runtime_dir / "docmolder.db",
        )
        self.store = InMemorySessionStore()
        self.deps = BotDependencies(settings=settings, session_store=self.store, processor=DocumentProcessor(runtime_dir))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_consume_upload_slot_blocks_after_burst_limit(self) -> None:
        self.assertTrue(_consume_upload_slot(42, self.deps))
        self.assertTrue(_consume_upload_slot(42, self.deps))
        self.assertFalse(_consume_upload_slot(42, self.deps))

    def test_consume_upload_slot_allows_again_after_window(self) -> None:
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=40)
        self.deps.upload_history[42] = deque([stale_time, stale_time])

        self.assertTrue(_consume_upload_slot(42, self.deps))

    def test_consume_upload_slot_survives_dependency_restart(self) -> None:
        self.assertTrue(_consume_upload_slot(42, self.deps))
        restarted_deps = BotDependencies(
            settings=self.deps.settings,
            session_store=self.store,
            processor=self.deps.processor,
        )

        self.assertTrue(_consume_upload_slot(42, restarted_deps))
        self.assertFalse(_consume_upload_slot(42, restarted_deps))

    def test_consume_upload_slot_ignores_stale_persisted_entries(self) -> None:
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=40)
        self.store.set_meta("upload_burst:42", json.dumps([stale_time.timestamp(), stale_time.timestamp()]))
        restarted_deps = BotDependencies(
            settings=self.deps.settings,
            session_store=self.store,
            processor=self.deps.processor,
        )

        self.assertTrue(_consume_upload_slot(42, restarted_deps))

    def test_has_capacity_for_new_job_reflects_active_jobs(self) -> None:
        self.assertTrue(_has_capacity_for_new_job(7, self.deps))
        self.store.create_job(user_id=7, chat_id=1, reply_to_message_id=None, action="images_to_pdf", payload_json="{}")
        self.store.create_job(user_id=7, chat_id=1, reply_to_message_id=None, action="pdf_merge", payload_json="{}")

        self.assertFalse(_has_capacity_for_new_job(7, self.deps))


if __name__ == "__main__":
    unittest.main()
