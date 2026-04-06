from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import (
    BotDependencies,
    SESSION_EMPTY_MESSAGE,
    _build_admin_report,
    _build_file_too_large_message,
    _build_history_rerun_message,
    _build_user_history_job_detail,
    _build_user_history_summary,
    _build_job_queue_limit_message,
    _build_periodic_admin_report,
    _build_processing_started_message,
    _build_text_request_queued_message,
    _build_session_file_limit_message,
    _build_upload_rate_limit_message,
    handle_action_callback,
    handle_history_callback,
    handle_rotate_callback,
    _maybe_send_admin_report_for_period,
    _process_job,
    history_command,
    handle_images_pdf_layout_callback,
    handle_images_pdf_margin_callback,
    handle_menu_text,
    handle_result_action_callback,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.processing import ProcessingResult
from docmolder.models import CompressionPreset, FileKind, JobStatus, SupportedAction, UserSession
from docmolder.models import AdminActionStat, AdminUserStat
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

        async def fake_send_result(
            _bot,
            _chat_id,
            _reply_to_message_id,
            result: ProcessingResult,
            *,
            source_job_id: int | None = None,
        ) -> None:
            self.assertEqual(source_job_id, job.id)
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

    def test_build_text_request_queued_message_mentions_fallback_for_pdf_grayscale(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_GRAYSCALE, 12, None)

        self.assertIn("fallback", message)
        self.assertIn("Job #12", message)

    def test_build_text_request_queued_message_mentions_longer_processing_for_medium_compression(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_COMPRESS, 13, CompressionPreset.MEDIUM)

        self.assertIn("più tempo", message)
        self.assertIn("fallback", message)

    def test_build_processing_started_message_mentions_fallback_for_pdf_grayscale(self) -> None:
        message = _build_processing_started_message(SupportedAction.PDF_GRAYSCALE, 14)

        self.assertIn("ripiego", message)
        self.assertIn("Job #14", message)

    def test_build_admin_report_includes_processing_metrics(self) -> None:
        report = _build_admin_report(
            {
                "known_users_total": 1,
                "known_users_last_24h": 1,
                "known_users_last_7d": 1,
                "completed_actions_total": 3,
                "completed_actions_last_24h": 3,
                "completed_actions_last_7d": 3,
                "active_sessions": 0,
                "images_to_pdf_total": 1,
                "pdf_compress_total": 1,
                "pdf_grayscale_total": 1,
                "pdf_merge_total": 0,
                "auto_orient_total": 0,
                "jobs_queued": 0,
                "jobs_running": 0,
                "jobs_failed": 0,
                "jobs_succeeded": 3,
                "raster_results_total": 1,
                "avg_duration_ms": 1500,
                "avg_input_bytes": 4096,
                "avg_output_bytes": 2048,
            },
            [AdminUserStat(user_id=7, label="@mario", completed_actions=3)],
            [AdminActionStat(action="pdf_compress", total=2)],
            [],
            [],
        )

        self.assertIn("Metriche tecniche medie", report)
        self.assertIn("1.5s", report)
        self.assertIn("4.0 KB", report)
        self.assertIn("2.0 KB", report)
        self.assertIn("Sintesi qualità", report)
        self.assertIn("100%", report)
        self.assertIn("Errori più frequenti", report)
        self.assertIn("Comprimi PDF: 2", report)

    def test_build_limit_messages_include_current_values(self) -> None:
        self.assertIn("20 MB", _build_file_too_large_message(20))
        self.assertIn("12 file", _build_session_file_limit_message(12))
        self.assertIn("3 file in 30 secondi", _build_upload_rate_limit_message(3, 30))
        self.assertIn("4 job attivi", _build_job_queue_limit_message(4))
        self.assertIn("Watermark", _build_user_history_job_detail(
            self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=123,
                action="pdf_watermark",
                payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"watermark_text":"BOZZA"}',
            )
        ))

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
        self.assertIn("Strategia finale: lossless", detail)
        self.assertIn("Ripeto il job", rerun_message)

    async def test_maybe_send_admin_report_for_period_persists_last_sent(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
        )

        self.bot.send_message.assert_awaited()
        self.assertEqual(self.store.get_meta("admin_report_daily_last_sent"), "2026-04-06")

        self.bot.send_message.reset_mock()
        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
        )
        self.bot.send_message.assert_not_awaited()

    def test_build_periodic_admin_report_prefixes_title(self) -> None:
        report = _build_periodic_admin_report(
            self.deps,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
        )

        self.assertTrue(report.startswith("Riepilogo admin giornaliero DocMolder"))

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
        reply_text.assert_awaited_once()

    async def test_action_callback_extract_pages_sets_pending_action(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="action:pdf_extract_pages",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=700),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_action_callback(update, context)

        self.assertEqual(self.store.get(7).pending_action, "pdf_extract_pages")
        self.assertIn("1,3,5-7", query.edit_message_text.await_args.args[0])

    async def test_pending_extract_pages_text_enqueues_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_extract_pages",
            )
        )
        message = SimpleNamespace(
            text="1,3-4",
            chat_id=99,
            message_id=701,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"page_selection": "1,3-4"', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))
        message.reply_text.assert_awaited_once()

    async def test_pending_watermark_text_enqueues_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_watermark",
            )
        )
        message = SimpleNamespace(
            text="BOZZA",
            chat_id=99,
            message_id=702,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"watermark_text": "BOZZA"', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

    async def test_rotate_callback_enqueues_manual_rotation_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="rotate:180",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=703),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_rotate_callback(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"rotate_degrees": 180', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

    async def test_text_request_for_grayscale_pdf_from_images_prompts_for_layout_choice(self) -> None:
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

        enqueue_job.assert_not_awaited()
        message.reply_text.assert_awaited_once()
        self.assertIn("formato A4", message.reply_text.await_args.args[0])
        self.assertIsNotNone(self.store.get(7))

    async def test_text_request_for_images_pdf_prompts_for_layout_choice(self) -> None:
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
            text="Crea PDF da immagini",
            chat_id=99,
            message_id=457,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock()) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_job.assert_not_awaited()
        message.reply_text.assert_awaited_once()
        self.assertIn("formato A4", message.reply_text.await_args.args[0])
        self.assertIsNotNone(self.store.get(7))

    async def test_layout_callback_a4_prompts_for_margin_choice(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
            )
        )
        query = SimpleNamespace(
            data="images_pdf_layout:a4:images_to_pdf",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=458),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_images_pdf_layout_callback(update, context)

        query.edit_message_text.assert_awaited_once()
        self.assertIn("Che bordi vuoi", query.edit_message_text.await_args.args[0])

    async def test_layout_callback_original_enqueues_job_without_a4(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
            )
        )
        query = SimpleNamespace(
            data="images_pdf_layout:original:images_to_pdf",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=459),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_images_pdf_layout_callback(update, context)

        queued_jobs = list(self.store._jobs.values())
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"image_pdf_use_a4": false', queued_jobs[0].payload_json)
        self.assertIn('"image_pdf_margin_px": 0', queued_jobs[0].payload_json)
        query.edit_message_text.assert_awaited_once()
        self.assertIsNone(self.store.get(7))

    async def test_margin_callback_enqueues_job_with_selected_margin(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
            )
        )
        query = SimpleNamespace(
            data="images_pdf_margin:wide:images_to_pdf",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=460),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_images_pdf_margin_callback(update, context)

        queued_jobs = list(self.store._jobs.values())
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"image_pdf_use_a4": true', queued_jobs[0].payload_json)
        self.assertIn('"image_pdf_margin_px": 120', queued_jobs[0].payload_json)
        query.edit_message_text.assert_awaited_once()
        self.assertIsNone(self.store.get(7))

    async def test_text_request_for_cropped_grayscale_pdf_from_images_prompts_for_layout_choice(self) -> None:
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
            text="Ritaglia i bordi e fammi un pdf in scala di grigi",
            chat_id=99,
            message_id=654,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=10))) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_job.assert_not_awaited()
        message.reply_text.assert_awaited_once()
        self.assertIn("formato A4", message.reply_text.await_args.args[0])
        self.assertIsNotNone(self.store.get(7))

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

    async def test_quick_action_button_guides_user_when_session_is_empty(self) -> None:
        message = SimpleNamespace(
            text="Comprimi PDF",
            chat_id=99,
            message_id=800,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        reply_text = message.reply_text.await_args.args[0]
        self.assertIn("Inviami un PDF", reply_text)

    async def test_quick_action_button_guides_user_when_merge_needs_more_pdfs(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Unisci PDF",
            chat_id=99,
            message_id=801,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        reply_text = message.reply_text.await_args.args[0]
        self.assertIn("almeno due", reply_text)

    async def test_legacy_status_button_still_works_and_refreshes_keyboard(self) -> None:
        message = SimpleNamespace(
            text="Mostra sessione",
            chat_id=99,
            message_id=802,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertEqual(message.reply_text.await_args.args[0], SESSION_EMPTY_MESSAGE)
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_legacy_reset_button_still_works_and_refreshes_keyboard(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Azzera sessione",
            chat_id=99,
            message_id=803,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Sessione azzerata", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])
        self.assertIsNone(self.store.get(7))


if __name__ == "__main__":
    unittest.main()
