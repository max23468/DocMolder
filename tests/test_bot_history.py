from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import (
    BotDependencies,
    _build_history_rerun_message,
    _build_user_history_job_detail,
    _build_user_history_summary,
    handle_history_callback,
    history_command,
    handle_menu_text,
    handle_result_action_callback,
    start_command,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import FileKind, SupportedAction, UserSession
from docmolder.session_store import InMemorySessionStore
from docmolder.action_catalog import build_session_file


class BotHistoryTest(unittest.IsolatedAsyncioTestCase):
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

    def test_build_user_history_summary_and_detail(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="images_to_pdf",
            payload_json='{"files":[{"telegram_file_id":"img-1","file_name":"foto.jpg","kind":"image"}],"compression_preset":null,"auto_rotate_pdf":true,"image_pdf_use_a4":true}',
        )
        self.store.mark_job_succeeded_with_metrics(
            job.id,
            "PDF creato.",
            processing_mode="lossless",
            input_bytes=1200,
            output_bytes=800,
            duration_ms=950,
        )
        stored_job = self.store.get_job(job.id)

        summary = _build_user_history_summary([stored_job])
        detail = _build_user_history_job_detail(stored_job)
        rerun_message = _build_history_rerun_message(stored_job, 12)

        self.assertIn("Storico ultimi job", summary)
        self.assertIn(f"Job #{job.id}", summary)
        self.assertIn("Dettaglio Job", detail)
        self.assertIn("File sorgente: 1 (foto.jpg)", detail)
        self.assertIn("Nome output base: foto_pdf", detail)
        self.assertIn("Impaginazione: A4", detail)
        self.assertIn("Rotazione automatica PDF: attiva", detail)
        self.assertIn("Strategia finale: lossless", detail)
        self.assertIn("Ripeto il job", rerun_message)

    def test_history_rerun_for_image_crop_points_to_pdf_crop_followup(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action=SupportedAction.IMAGES_TO_PDF_CROP.value,
            payload_json='{"files":[{"telegram_file_id":"img-1","file_name":"foto.jpg","kind":"image"}],"compression_preset":null,"auto_rotate_pdf":true,"image_pdf_use_a4":true}',
        )

        message = _build_history_rerun_message(job, 15)

        self.assertIn("ritaglio sulle immagini sorgenti", message)
        self.assertIn("Taglia bordi PDF", message)
        self.assertIn("taglia i bordi di questo pdf", message)

    async def test_text_request_can_rerun_latest_job_with_context_phrase(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":null}',
        )
        message = SimpleNamespace(
            text="Ripeti l'ultimo job",
            chat_id=99,
            message_id=501,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 1)
        self.assertEqual(queued_jobs[0].rerun_of_job_id, source_job.id)
        self.assertIn("Ripeto il job", message.reply_text.await_args.args[0])

    async def test_rerun_context_phrase_does_not_override_active_session(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"old-pdf","file_name":"vecchio.pdf","kind":"pdf"}]}',
        )
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("new-pdf", "corrente.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Ripeti quello precedente su questo PDF",
            chat_id=99,
            message_id=5011,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 0)
        message.reply_text.assert_awaited_once()
        self.assertNotIn("Ripeto il job", message.reply_text.await_args.args[0])

    async def test_start_deep_link_retry_is_no_longer_a_shortcut(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":null}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=777)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=[f"retry_{source_job.id}"])

        await start_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 0)
        self.assertIn("DocMolder", message.reply_text.await_args.args[0])

    async def test_start_deep_link_retry_latest_is_no_longer_a_shortcut(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=780)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["retry_latest"])

        await start_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 0)
        self.assertIn("DocMolder", message.reply_text.await_args.args[0])

    async def test_start_deep_link_retry_latest_does_not_resolve_user_jobs(self) -> None:
        own_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        other_job = self.store.create_job(
            user_id=8,
            chat_id=99,
            reply_to_message_id=124,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=781)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["retry_latest"])

        await start_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id not in {own_job.id, other_job.id}]
        self.assertEqual(len(queued_jobs), 0)
        self.assertIn("DocMolder", message.reply_text.await_args.args[0])

    async def test_start_deep_link_last_is_no_longer_a_shortcut(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_merge",
            payload_json='{"files":[]}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=779)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["last"])

        await start_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 0)
        self.assertIn("DocMolder", message.reply_text.await_args.args[0])

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

    async def test_result_callback_can_continue_with_compression_without_reupload(self) -> None:
        reply_text = AsyncMock()
        message = SimpleNamespace(
            chat_id=99,
            message_id=322,
            document=SimpleNamespace(file_id="telegram-pdf-id", file_name="docmolder_pdf.pdf", mime_type="application/pdf"),
            reply_text=reply_text,
        )
        query = SimpleNamespace(
            data="result:pdf_compress",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=message,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_result_action_callback(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.files[0].telegram_file_id, "telegram-pdf-id")
        reply_text.assert_awaited_once()
        self.assertIn("compressione PDF", reply_text.await_args.args[0])
        self.assertIsNotNone(reply_text.await_args.kwargs["reply_markup"])

    async def test_result_callback_can_continue_with_watermark_without_reupload(self) -> None:
        reply_text = AsyncMock()
        message = SimpleNamespace(
            chat_id=99,
            message_id=323,
            document=SimpleNamespace(file_id="telegram-pdf-id", file_name="docmolder_pdf.pdf", mime_type="application/pdf"),
            reply_text=reply_text,
        )
        query = SimpleNamespace(
            data="result:pdf_watermark",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=message,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_result_action_callback(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, SupportedAction.PDF_WATERMARK.value)
        reply_text.assert_awaited_once()
        self.assertIn("watermark", reply_text.await_args.args[0].lower())

    async def test_result_callback_can_prompt_for_split_output_without_reupload(self) -> None:
        reply_text = AsyncMock()
        message = SimpleNamespace(
            chat_id=99,
            message_id=324,
            document=SimpleNamespace(file_id="telegram-pdf-id", file_name="docmolder_pdf.pdf", mime_type="application/pdf"),
            reply_text=reply_text,
        )
        query = SimpleNamespace(
            data="result:pdf_split",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=message,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_result_action_callback(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, SupportedAction.PDF_SPLIT.value)
        self.assertEqual(saved_session.files[0].telegram_file_id, "telegram-pdf-id")
        reply_text.assert_awaited_once()
        self.assertIn("ZIP", reply_text.await_args.args[0])
        self.assertIsNotNone(reply_text.await_args.kwargs["reply_markup"])

    async def test_result_callback_requeues_same_job_without_auto_rotation(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium","rotate_degrees":null,"auto_rotate_pdf":true}',
        )
        reply_text = AsyncMock()
        message = SimpleNamespace(
            chat_id=99,
            message_id=444,
            document=SimpleNamespace(file_id="generated-pdf", file_name="docmolder_compressed.pdf", mime_type="application/pdf"),
            reply_text=reply_text,
        )
        query = SimpleNamespace(
            data=f"result:undo_rotate:{source_job.id}",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=message,
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_result_action_callback(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"auto_rotate_pdf": false', queued_jobs[0].payload_json)
        reply_text.assert_awaited_once()

    async def test_history_command_lists_recent_jobs(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium"}',
        )
        self.store.mark_job_succeeded(job.id, "Completato")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await history_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Storico ultimi job", message.reply_text.await_args.args[0])

    async def test_history_callback_details_shows_job_detail(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":null}',
        )
        self.store.mark_job_failed(job.id, "Errore di test")
        reply_text = AsyncMock()
        query = SimpleNamespace(
            data=f"history:details:{job.id}",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(message_id=600, reply_text=reply_text),
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_history_callback(update, context)

        reply_text.assert_awaited_once()
        self.assertIn("Dettaglio Job", reply_text.await_args.args[0])

    async def test_history_callback_rerun_enqueues_same_payload(self) -> None:
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium","auto_rotate_pdf":true}',
        )
        reply_text = AsyncMock()
        query = SimpleNamespace(
            data=f"history:rerun:{job.id}",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=601, reply_text=reply_text),
            answer=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_history_callback(update, context)

        queued_jobs = [queued_job for queued_job in self.store._jobs.values() if queued_job.id != job.id]
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"compression_preset": "medium"', queued_jobs[0].payload_json)
        self.assertEqual(queued_jobs[0].rerun_of_job_id, job.id)
        reply_text.assert_awaited_once()

    def test_build_user_history_summary_groups_rerun_jobs_separately(self) -> None:
        source_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        rerun_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
            rerun_of_job_id=source_job.id,
        )
        self.store.mark_job_succeeded(rerun_job.id, "Completato")

        summary = _build_user_history_summary([rerun_job])

        self.assertIn("Rilanciati:", summary)
        self.assertIn(f"rilancio di #{source_job.id}", summary)

    async def test_menu_text_storico_lavori_delegates_to_history(self) -> None:
        message = SimpleNamespace(
            text="Storico lavori",
            chat_id=99,
            message_id=790,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot.history_command", new=AsyncMock()) as history_mock:
            await handle_menu_text(update, context)

        history_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
