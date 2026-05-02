from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import BotDependencies, _process_job
from docmolder.config import Settings
from docmolder.models import JobStatus, SupportedAction
from docmolder.processing import DocumentProcessor, ProcessingOutput, ProcessingResult, ProcessingUserError
from docmolder.session_store import InMemorySessionStore


class BotProcessingJobTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            session_ttl_minutes=30,
            max_session_files=20,
            max_file_size_mb=20,
            upload_burst_limit=8,
            upload_burst_window_seconds=30,
            max_active_jobs_per_user=2,
            cleanup_interval_minutes=30,
            stale_job_retention_hours=6,
            job_history_retention_days=30,
            admin_slow_job_threshold_ms=30000,
            health_max_queued_jobs=20,
            health_max_running_jobs=5,
            health_max_running_job_age_seconds=3600,
            health_max_runtime_dir_bytes=2_147_483_648,
            health_max_database_bytes=134_217_728,
            health_max_backup_age_seconds=172800,
            health_max_finished_jobs_24h=300,
            health_max_active_users_7d=100,
            health_max_failure_rate_percent=40,
            health_failure_rate_min_finished_jobs=10,
            telegram_brand_sync_enabled=True,
            runtime_dir=self.runtime_dir,
            database_path=self.runtime_dir / "docmolder.db",
            sqlite_backup_dir=self.runtime_dir / "backups",
        )
        self.store = InMemorySessionStore()
        self.processor = DocumentProcessor(self.runtime_dir)
        self.deps = BotDependencies(self.settings, self.store, self.processor)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.application = SimpleNamespace(bot=self.bot, bot_data={"deps": self.deps})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_process_job_cleans_up_only_after_result_is_sent(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="images_to_pdf",
            payload_json='{"files":[]}',
        )
        sent_paths: list[Path] = []

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            output_path = job_dir / "docmolder_pdf.pdf"
            output_path.write_bytes(b"%PDF-1.4 test")
            return ProcessingResult(
                output_path=output_path,
                output_name=output_path.name,
                message="ok",
            )

        async def fake_send_result(
            _bot,
            _chat_id,
            _reply_to_message_id,
            result: ProcessingResult,
            *,
            deps=None,
            source_action: SupportedAction | None = None,
            source_job_id: int | None = None,
        ) -> None:
            self.assertIsNotNone(deps)
            self.assertEqual(source_job_id, job.id)
            self.assertEqual(source_action, SupportedAction.IMAGES_TO_PDF)
            self.assertTrue(result.output_path.exists())
            sent_paths.append(result.output_path)

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", side_effect=fake_send_result),
        ):
            await _process_job(self.application, job.id)

        self.assertEqual(len(sent_paths), 1)
        self.assertFalse(sent_paths[0].exists())

    async def test_process_job_saves_result_pdf_as_new_session(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            output_path = job_dir / "docmolder_pdf.pdf"
            output_path.write_bytes(b"%PDF-1.4 test")
            return ProcessingResult(
                output_path=output_path,
                output_name=output_path.name,
                message="ok",
            )

        sent_message = SimpleNamespace(
            document=SimpleNamespace(file_id="result-file-id", file_name="docmolder_pdf.pdf", mime_type="application/pdf")
        )

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", new=AsyncMock(return_value=sent_message)),
        ):
            await _process_job(self.application, job.id)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.files[0].telegram_file_id, "result-file-id")

    async def test_process_job_sums_multiple_result_outputs_without_result_session(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_split",
            payload_json='{"files":[],"split_output_zip":false}',
        )

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            first_path = job_dir / "page_01.pdf"
            second_path = job_dir / "page_02.pdf"
            first_path.write_bytes(b"x" * 500)
            second_path.write_bytes(b"y" * 700)
            return ProcessingResult(
                output_path=first_path,
                output_name=first_path.name,
                message="ok",
                processing_mode="native",
                additional_outputs=[ProcessingOutput(path=second_path, name=second_path.name)],
            )

        sent_message = SimpleNamespace(
            document=SimpleNamespace(file_id="first-page-id", file_name="page_01.pdf", mime_type="application/pdf")
        )

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", new=AsyncMock(return_value=sent_message)),
        ):
            await _process_job(self.application, job.id)

        stored_job = self.store.get_job(job.id)
        self.assertIsNotNone(stored_job)
        self.assertEqual(stored_job.output_bytes, 1200)
        self.assertIsNone(self.store.get(7))

    async def test_process_job_announces_fallback_risk_for_pdf_grayscale(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            output_path = job_dir / "docmolder_grayscale.pdf"
            output_path.write_bytes(b"%PDF-1.4 test")
            return ProcessingResult(
                output_path=output_path,
                output_name=output_path.name,
                message="ok",
            )

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", new=AsyncMock()),
        ):
            await _process_job(self.application, job.id)

        self.bot.send_message.assert_awaited()
        first_message = self.bot.send_message.await_args_list[0].kwargs["text"]
        self.assertIn("soluzione di ripiego", first_message)

    async def test_process_job_persists_basic_processing_metrics(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            input_dir = job_dir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            (input_dir / "source.pdf").write_bytes(b"x" * 1200)
            output_path = job_dir / "docmolder_grayscale.pdf"
            output_path.write_bytes(b"y" * 800)
            return ProcessingResult(
                output_path=output_path,
                output_name=output_path.name,
                message="ok",
                processing_mode="raster",
            )

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", new=AsyncMock()),
        ):
            await _process_job(self.application, job.id)

        stored_job = self.store.get_job(job.id)
        self.assertIsNotNone(stored_job)
        self.assertEqual(stored_job.processing_mode, "raster")
        self.assertEqual(stored_job.input_bytes, 1200)
        self.assertEqual(stored_job.output_bytes, 800)
        self.assertIsNotNone(stored_job.duration_ms)
        self.assertGreaterEqual(stored_job.duration_ms, 0)

    async def test_process_job_cleans_up_even_after_processing_user_error(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        job_dir = self.runtime_dir / "jobs" / "failed_job"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "partial.tmp").write_text("temp", encoding="utf-8")

        async def fake_run_job_payload(_application, _job, _job_dir: Path) -> ProcessingResult:
            raise ProcessingUserError("Errore controllato")

        with (
            patch.object(self.processor, "create_job_dir", return_value=job_dir),
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
        ):
            await _process_job(self.application, job.id)

        self.assertFalse(job_dir.exists())
        self.assertEqual(self.store.get_job(job.id).status, JobStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
