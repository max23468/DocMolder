from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import BotDependencies, _process_job, handle_menu_text, handle_result_action_callback
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.processing import ProcessingResult
from docmolder.models import FileKind, JobStatus, SupportedAction, UserSession
from docmolder.session_store import InMemorySessionStore
from docmolder.services import build_session_file


class JobProcessingCleanupOrderTest(unittest.IsolatedAsyncioTestCase):
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
            runtime_dir=self.runtime_dir,
            database_path=self.runtime_dir / "docmolder.db",
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

        async def fake_send_result(_bot, _chat_id, _reply_to_message_id, result: ProcessingResult) -> None:
            self.assertTrue(result.output_path.exists())
            sent_paths.append(result.output_path)

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch("docmolder.bot._send_result", side_effect=fake_send_result),
        ):
            await _process_job(self.application, job.id)

        self.assertEqual(len(sent_paths), 1)
        self.assertFalse(sent_paths[0].exists())
        self.assertEqual(self.store.get_job(job.id).status, JobStatus.SUCCEEDED)

    async def test_result_callback_enqueues_grayscale_job_from_sent_pdf(self) -> None:
        reply_text = AsyncMock()
        message = SimpleNamespace(
            chat_id=99,
            message_id=321,
            document=SimpleNamespace(file_id="telegram-pdf-id", file_name="docmolder_pdf.pdf", mime_type="application/pdf"),
            reply_text=reply_text,
        )
        query = SimpleNamespace(
            data="result:pdf_grayscale",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=message,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=5))) as enqueue_job:
            await handle_result_action_callback(update, context)

        enqueue_job.assert_awaited_once()
        enqueue_call = enqueue_job.await_args.kwargs
        self.assertEqual(enqueue_call["action"], SupportedAction.PDF_GRAYSCALE)
        self.assertEqual(enqueue_call["session"].files[0].telegram_file_id, "telegram-pdf-id")
        reply_text.assert_awaited_once()

    async def test_text_request_enqueues_grayscale_pdf_from_images(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[
                    build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE),
                    build_session_file("img-2", "foto_2.jpg", FileKind.IMAGE),
                ],
            )
        )
        message = SimpleNamespace(
            text="Fammi un PDF in scala di grigi",
            chat_id=99,
            message_id=456,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=8))) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_call = enqueue_job.await_args.kwargs
        self.assertEqual(enqueue_call["action"], SupportedAction.IMAGES_TO_PDF_GRAYSCALE)
        message.reply_text.assert_awaited_once()
        self.assertIsNone(self.store.get(7))

    async def test_text_request_enqueues_medium_compression_for_pdf(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Comprimi questo pdf",
            chat_id=99,
            message_id=789,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=9))) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_call = enqueue_job.await_args.kwargs
        self.assertEqual(enqueue_call["action"], SupportedAction.PDF_COMPRESS)
        self.assertEqual(enqueue_call["compression_preset"].value, "medium")
        message.reply_text.assert_awaited_once()
        self.assertIsNone(self.store.get(7))


if __name__ == "__main__":
    unittest.main()
