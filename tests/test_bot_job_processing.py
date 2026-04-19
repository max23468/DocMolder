from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telegram.error import TelegramError

from docmolder.bot import (
    BotDependencies,
    SensitiveLogFilter,
    SESSION_EMPTY_MESSAGE,
    _build_admin_report,
    _build_compression_prompt,
    _build_file_too_large_message,
    _build_history_rerun_message,
    _build_image_session_message,
    _build_result_delivery_message,
    _build_user_history_job_detail,
    _build_user_history_summary,
    _build_job_queue_limit_message,
    _normalize_page_selection_text,
    _build_periodic_admin_report,
    _build_processing_started_message,
    _maybe_notify_admins_about_new_user,
    _maybe_send_admin_anomaly_alerts,
    _build_text_request_queued_message,
    _build_session_file_limit_message,
    _build_upload_rate_limit_message,
    _detect_admin_anomaly_alerts,
    _redact_sensitive_text,
    handle_action_callback,
    handle_document,
    handle_history_callback,
    handle_photo,
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
from docmolder.processing import ProcessingUserError
from docmolder.models import CompressionPreset, FileKind, JobStatus, SupportedAction, UserSession
from docmolder.models import AdminActionStat, AdminStats, AdminUserStat
from docmolder.keyboards import build_main_menu_keyboard
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
            source_action: SupportedAction | None = None,
            source_job_id: int | None = None,
        ) -> None:
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

    def test_main_menu_keyboard_exposes_quick_templates(self) -> None:
        keyboard = build_main_menu_keyboard()

        labels = [button.text for row in keyboard.keyboard for button in row]
        self.assertIn("Foto in A4", labels)
        self.assertIn("Scansiona e comprimi", labels)

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

    def test_build_text_request_queued_message_mentions_fallback_for_pdf_grayscale(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_GRAYSCALE, 12, None)

        self.assertIn("fallback", message)
        self.assertIn("Job #12", message)

    def test_build_text_request_queued_message_mentions_longer_processing_for_medium_compression(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_COMPRESS, 13, CompressionPreset.MEDIUM)

        self.assertIn("più tempo", message)
        self.assertIn("fallback", message)

    def test_build_result_delivery_message_suggests_followup_actions_for_pdf(self) -> None:
        result = ProcessingResult(
            output_path=Path("/tmp/output.pdf"),
            output_name="output.pdf",
            message="PDF pronto.",
        )

        message = _build_result_delivery_message(result, SupportedAction.PDF_GRAYSCALE)

        self.assertIn("continuare su questo PDF", message)
        self.assertIn("Comprimi PDF", message)

    def test_build_compression_prompt_mentions_saved_preference(self) -> None:
        self.store.set_user_preference(7, "compression_preset", "medium")

        message = _build_compression_prompt(7, self.deps)

        self.assertIn("Ultima scelta rapida salvata: medium", message)

    def test_image_session_message_includes_structured_recap(self) -> None:
        session = UserSession(
            user_id=7,
            files=[
                build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE),
                build_session_file("img-2", "foto_2.jpg", FileKind.IMAGE),
            ],
        )

        message = _build_image_session_message(session)

        self.assertIn("Sessione corrente:", message)
        self.assertIn("Azioni consigliate", message)

    def test_normalize_page_selection_text_accepts_space_separated_values(self) -> None:
        normalized = _normalize_page_selection_text("3 1 2 4-5")

        self.assertEqual(normalized, "3,1,2,4-5")

    def test_build_processing_started_message_mentions_fallback_for_pdf_grayscale(self) -> None:
        message = _build_processing_started_message(SupportedAction.PDF_GRAYSCALE, 14)

        self.assertIn("ripiego", message)
        self.assertIn("Job #14", message)

    def test_build_admin_report_includes_processing_metrics(self) -> None:
        report = _build_admin_report(
            AdminStats(
                known_users_total=1,
                known_users_last_24h=1,
                known_users_last_7d=1,
                completed_actions_total=3,
                completed_actions_last_24h=3,
                completed_actions_last_7d=3,
                active_sessions=0,
                images_to_pdf_total=1,
                pdf_compress_total=1,
                pdf_grayscale_total=1,
                pdf_merge_total=0,
                pdf_extract_pages_total=0,
                pdf_reorder_pages_total=0,
                pdf_delete_pages_total=0,
                pdf_rotate_total=0,
                pdf_watermark_total=0,
                auto_orient_total=0,
                jobs_queued=0,
                jobs_running=0,
                jobs_failed=0,
                jobs_succeeded=3,
                raster_results_total=1,
                avg_duration_ms=1500,
                avg_input_bytes=4096,
                avg_output_bytes=2048,
            ),
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
        self.assertIn("Impaginazione: A4", detail)
        self.assertIn("Rotazione automatica PDF: attiva", detail)
        self.assertIn("Strategia finale: lossless", detail)
        self.assertIn("Ripeto il job", rerun_message)

    async def test_maybe_send_admin_report_for_period_persists_last_sent(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.store.record_completed_action(7, "pdf_compress")
        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
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
            require_new_users_or_completed_actions=True,
        )
        self.bot.send_message.assert_not_awaited()

    async def test_maybe_send_admin_report_for_period_skips_empty_period(self) -> None:
        self.deps.settings.admin_user_ids = [999]

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_daily_last_sent"))

    async def test_maybe_send_admin_report_for_period_daily_skips_without_new_users_or_operations(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        failed_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_daily_last_sent"))

    async def test_maybe_send_admin_report_for_period_weekly_skips_without_new_users_or_operations(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        failed_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="weekly",
            report_date="2026-04-06",
            should_send=True,
            since_days=7,
            title="Riepilogo admin settimanale DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_weekly_last_sent"))

    def test_build_periodic_admin_report_prefixes_title(self) -> None:
        report = _build_periodic_admin_report(
            self.deps,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
        )

        self.assertTrue(report.startswith("Riepilogo admin giornaliero DocMolder"))
        self.assertIn("Errori più frequenti ultime 24 ore", report)
        self.assertIn("Job completati nelle ultime 24 ore", report)

    async def test_maybe_notify_admins_about_new_user_swallows_telegram_errors_only(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user = SimpleNamespace(id=7, username="mario", first_name="Mario", last_name="Rossi", full_name="Mario Rossi")
        self.bot.send_message.side_effect = TelegramError("admin unavailable")

        await _maybe_notify_admins_about_new_user(user, context)

        self.bot.send_message.assert_awaited_once()

    async def test_maybe_notify_admins_about_new_user_does_not_hide_programming_errors(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user = SimpleNamespace(id=7, username="mario", first_name="Mario", last_name="Rossi", full_name="Mario Rossi")
        self.bot.send_message.side_effect = RuntimeError("unexpected bug")

        with self.assertRaises(RuntimeError):
            await _maybe_notify_admins_about_new_user(user, context)

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

    async def test_pending_reorder_pages_accepts_space_separated_values(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_reorder_pages",
            )
        )
        message = SimpleNamespace(
            text="3 1 2",
            chat_id=99,
            message_id=7011,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"page_selection": "3,1,2"', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

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

    async def test_pending_rotate_text_enqueues_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_rotate",
            )
        )
        message = SimpleNamespace(
            text="giralo a destra",
            chat_id=99,
            message_id=7021,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"rotate_degrees": 90', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))
        message.reply_text.assert_awaited_once()

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

    async def test_text_request_for_image_pdf_marks_pending_layout_choice(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
            )
        )
        message = SimpleNamespace(
            text="PDF da immagini",
            chat_id=99,
            message_id=655,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, "images_pdf_layout:images_to_pdf")
        message.reply_text.assert_awaited_once()
        self.assertIn("formato A4", message.reply_text.await_args.args[0])

    async def test_pending_image_pdf_layout_text_can_ask_for_margin(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
                pending_action="images_pdf_layout:images_to_pdf",
            )
        )
        message = SimpleNamespace(
            text="Si, impagina in A4",
            chat_id=99,
            message_id=656,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, "images_pdf_margin:images_to_pdf")
        message.reply_text.assert_awaited_once()
        self.assertIn("Che bordi vuoi", message.reply_text.await_args.args[0])

    async def test_pending_image_pdf_margin_text_enqueues_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
                pending_action="images_pdf_margin:images_to_pdf",
            )
        )
        message = SimpleNamespace(
            text="bordi stretti",
            chat_id=99,
            message_id=657,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"image_pdf_use_a4": true', queued_job.payload_json)
        self.assertIn('"image_pdf_margin_px": 48', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))
        message.reply_text.assert_awaited_once()

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

    async def test_text_request_accepts_light_typo_for_compression(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Comprmi questo pdf",
            chat_id=99,
            message_id=7891,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"compression_preset": "medium"', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_text_request_can_set_strong_compression_preset(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Comprimi questo pdf in modo forte",
            chat_id=99,
            message_id=7892,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"compression_preset": "strong"', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_text_request_can_extract_pages_naturally(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Estrai pagine 2-3",
            chat_id=99,
            message_id=900,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"page_selection": "2-3"', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_text_request_can_delete_pages_with_conjunctions(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Togli le pagine 2 e 4",
            chat_id=99,
            message_id=9001,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"page_selection": "2,4"', queued_job.payload_json)
        self.assertEqual(queued_job.action, "pdf_delete_pages")
        message.reply_text.assert_awaited_once()

    async def test_text_request_without_page_action_asks_for_clarification(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Pagine 2-4",
            chat_id=99,
            message_id=9002,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        message.reply_text.assert_awaited_once()
        self.assertIn("estrai pagine", message.reply_text.await_args.args[0])
        self.assertIn("elimina pagine", message.reply_text.await_args.args[0])

    async def test_text_request_can_rotate_naturally(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Ruota questo pdf di 90 gradi",
            chat_id=99,
            message_id=901,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"rotate_degrees": 90', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_text_request_can_prompt_for_missing_rotation_degrees(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Ruota questo pdf",
            chat_id=99,
            message_id=9011,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, "pdf_rotate")
        message.reply_text.assert_awaited_once()
        self.assertIn("90", message.reply_text.await_args.args[0])

    async def test_text_request_can_add_watermark_naturally(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Aggiungi watermark BOZZA",
            chat_id=99,
            message_id=902,
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
        message.reply_text.assert_awaited_once()

    async def test_text_request_can_add_filigrana_with_quotes(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text='Metti una filigrana "RISERVATO"',
            chat_id=99,
            message_id=9021,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"watermark_text": "RISERVATO"', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_text_request_with_multiple_pdf_actions_asks_for_clarification(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Comprimi questo pdf in bianco e nero",
            chat_id=99,
            message_id=9022,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        message.reply_text.assert_awaited_once()
        self.assertIn("una cosa per volta", message.reply_text.await_args.args[0].lower())

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

    async def test_template_like_text_guides_user_for_scan_and_compress_flow(self) -> None:
        message = SimpleNamespace(
            text="Scansiona e comprimi",
            chat_id=99,
            message_id=8011,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("ritaglio bordi", message.reply_text.await_args.args[0])

    async def test_template_like_text_guides_user_for_photo_in_a4_flow(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)],
            )
        )
        message = SimpleNamespace(
            text="Foto in A4",
            chat_id=99,
            message_id=8012,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("impaginazione A4", message.reply_text.await_args.args[0])

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
        self.store.set_user_preference(7, "compression_preset", "medium")
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
        self.assertIn("ultime scelte rapide", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])
        self.assertIsNone(self.store.get(7))
        self.assertIsNone(self.store.get_user_preference(7, "compression_preset"))

    def test_detect_admin_anomaly_alerts_reports_failure_rate_and_repeated_action(self) -> None:
        self.deps.settings.admin_alert_window_minutes = 30
        self.deps.settings.admin_alert_min_finished_jobs = 4
        self.deps.settings.admin_alert_failure_rate_percent = 50
        self.deps.settings.admin_alert_repeated_failures_threshold = 3

        for index in range(4):
            job = self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=900 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore di test")

        success_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=999,
            action="images_to_pdf",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(success_job.id, "Ok")

        alerts = _detect_admin_anomaly_alerts(self.deps)

        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["key"], "failure-rate")
        self.assertIn("tasso di fallimento anomalo", alerts[0]["text"])
        self.assertIn("Comprimi PDF: 4", alerts[0]["text"])
        self.assertEqual(alerts[1]["key"], "repeated-failures:pdf_compress")
        self.assertIn("errori ripetuti su Comprimi PDF", alerts[1]["text"])

    async def test_maybe_send_admin_anomaly_alerts_respects_cooldown(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.deps.settings.admin_alert_window_minutes = 30
        self.deps.settings.admin_alert_min_finished_jobs = 3
        self.deps.settings.admin_alert_failure_rate_percent = 60
        self.deps.settings.admin_alert_repeated_failures_threshold = 3
        self.deps.settings.admin_alert_cooldown_minutes = 120

        for index in range(3):
            job = self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=1000 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore di test")

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)
        first_send_count = self.bot.send_message.await_count
        self.assertGreaterEqual(first_send_count, 1)

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)
        self.assertEqual(self.bot.send_message.await_count, first_send_count)

    async def test_pseudo_e2e_photo_to_pdf_followup_flow(self) -> None:
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user = SimpleNamespace(id=7, username=None, first_name="Test", last_name=None)

        with patch("docmolder.bot._schedule_image_session_notification", return_value=None):
            first_photo_message = SimpleNamespace(
                chat_id=99,
                message_id=1100,
                photo=[SimpleNamespace(file_id="img-1", file_size=1000)],
                reply_text=AsyncMock(),
                document=None,
            )
            await handle_photo(
                SimpleNamespace(effective_user=user, effective_message=first_photo_message),
                context,
            )

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(len(saved_session.files), 1)
        self.assertEqual(saved_session.files[0].telegram_file_id, "img-1")

        layout_message = SimpleNamespace(
            text="PDF da immagini",
            chat_id=99,
            message_id=1101,
            reply_text=AsyncMock(),
        )
        await handle_menu_text(SimpleNamespace(effective_user=user, effective_message=layout_message), context)
        self.assertEqual(self.store.get(7).pending_action, "images_pdf_layout:images_to_pdf")

        a4_message = SimpleNamespace(
            text="Si, impagina in A4",
            chat_id=99,
            message_id=1102,
            reply_text=AsyncMock(),
        )
        await handle_menu_text(SimpleNamespace(effective_user=user, effective_message=a4_message), context)
        self.assertEqual(self.store.get(7).pending_action, "images_pdf_margin:images_to_pdf")

        margin_message = SimpleNamespace(
            text="bordi stretti",
            chat_id=99,
            message_id=1103,
            reply_text=AsyncMock(),
        )
        await handle_menu_text(SimpleNamespace(effective_user=user, effective_message=margin_message), context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertIn('"image_pdf_use_a4": true', queued_job.payload_json)
        self.assertIn('"image_pdf_margin_px": 48', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

        async def fake_run_job_payload(_application, _job, job_dir: Path) -> ProcessingResult:
            output_path = job_dir / "docmolder_pdf.pdf"
            output_path.write_bytes(b"%PDF-1.4 test")
            return ProcessingResult(
                output_path=output_path,
                output_name=output_path.name,
                message="PDF creato.",
            )

        with (
            patch("docmolder.bot._run_job_payload", side_effect=fake_run_job_payload),
            patch(
                "docmolder.bot._send_result",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        document=SimpleNamespace(
                            file_id="result-pdf-id",
                            file_name="docmolder_pdf.pdf",
                            mime_type="application/pdf",
                        )
                    )
                ),
            ),
        ):
            await _process_job(self.application, queued_job.id)

        result_session = self.store.get(7)
        self.assertIsNotNone(result_session)
        self.assertEqual(result_session.files[0].telegram_file_id, "result-pdf-id")

        followup_message = SimpleNamespace(
            text="Scala di grigi",
            chat_id=99,
            message_id=1104,
            reply_text=AsyncMock(),
        )
        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=77))) as enqueue_job:
            await handle_menu_text(SimpleNamespace(effective_user=user, effective_message=followup_message), context)

        enqueue_job.assert_awaited_once()
        self.assertEqual(enqueue_job.await_args.kwargs["action"], SupportedAction.PDF_GRAYSCALE)

    async def test_pseudo_e2e_document_upload_to_compress_flow(self) -> None:
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user = SimpleNamespace(id=7, username=None, first_name="Test", last_name=None)
        document_message = SimpleNamespace(
            chat_id=99,
            message_id=1200,
            document=SimpleNamespace(
                file_id="pdf-telegram-id",
                file_name="documento.pdf",
                mime_type="application/pdf",
                file_size=1024,
            ),
            reply_text=AsyncMock(),
        )

        await handle_document(
            SimpleNamespace(effective_user=user, effective_message=document_message),
            context,
        )

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.files[0].telegram_file_id, "pdf-telegram-id")
        document_message.reply_text.assert_awaited_once()
        self.assertIn("File ricevuto", document_message.reply_text.await_args.args[0])

        compress_message = SimpleNamespace(
            text="Comprimi questo pdf",
            chat_id=99,
            message_id=1201,
            reply_text=AsyncMock(),
        )
        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=88))) as enqueue_job:
            await handle_menu_text(SimpleNamespace(effective_user=user, effective_message=compress_message), context)

        enqueue_job.assert_awaited_once()
        self.assertEqual(enqueue_job.await_args.kwargs["action"], SupportedAction.PDF_COMPRESS)
        self.assertEqual(enqueue_job.await_args.kwargs["compression_preset"], CompressionPreset.MEDIUM)


class SensitiveLoggingTest(unittest.TestCase):
    def test_redact_sensitive_text_masks_telegram_bot_token_in_url(self) -> None:
        text = (
            'HTTP Request: POST '
            'https://api.telegram.org/bot123456:ABCdef_GHI-123/getUpdates '
            '"HTTP/1.1 200 OK"'
        )

        redacted = _redact_sensitive_text(text)

        self.assertNotIn("ABCdef_GHI-123", redacted)
        self.assertIn("https://api.telegram.org/bot<redacted>/getUpdates", redacted)

    def test_sensitive_log_filter_redacts_tuple_args(self) -> None:
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Request to %s",
            args=("https://api.telegram.org/bot123456:ABCdef_GHI-123/getUpdates",),
            exc_info=None,
        )

        allowed = SensitiveLogFilter().filter(record)

        self.assertTrue(allowed)
        self.assertEqual(
            record.args,
            ("https://api.telegram.org/bot<redacted>/getUpdates",),
        )


if __name__ == "__main__":
    unittest.main()
