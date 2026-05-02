from __future__ import annotations

import sys
import tempfile
import unittest
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telegram.error import RetryAfter

from docmolder.bot import (
    BotDependencies,
    _append_audit_log,
    _build_image_session_intro,
    _build_result_pdf_session,
    _sync_telegram_branding,
    _build_compression_prompt,
    _build_file_too_large_message,
    _build_image_session_message,
    _build_split_output_prompt,
    _build_result_delivery_message,
    _build_user_history_job_detail,
    _build_job_queue_limit_message,
    _normalize_page_selection_text,
    _record_user_choice,
    _build_processing_started_message,
    _maybe_notify_admins_about_new_user,
    _build_text_request_queued_message,
    _build_session_file_limit_message,
    _build_service_status_label,
    _build_upload_rate_limit_message,
    _build_unsupported_document_message,
    _format_bytes,
    _format_duration_ms,
    _format_job_line,
    _get_dynamic_access_status,
    _get_meta_counter,
    _get_service_mode,
    _get_stored_compression_preset,
    _get_stored_image_pdf_layout,
    _get_stored_image_pdf_margin,
    _get_stored_split_output_choice,
    _increment_meta_counter,
    _is_authorized,
    _is_authorized_for_deps,
    _is_replayed_callback,
    _is_service_paused,
    _list_dynamic_access_statuses,
    _load_persisted_upload_history,
    _persist_upload_history,
    _record_callback_metric,
    _record_command_metric,
    _record_image_pdf_choice,
    _record_split_output_choice,
    _record_upload_metric,
    _resolve_compression_preset_for_job,
    _set_dynamic_access_status,
    _set_service_mode,
    _sum_file_sizes,
    _sum_processing_result_sizes,
    handle_document,
    handle_photo,
    _process_job,
    build_application,
    handle_delete_data_callback,
    handle_menu_text,
    start_command,
)
from docmolder.config import Settings
from docmolder.branding import TELEGRAM_NAME, build_telegram_commands
from docmolder.processing import DocumentProcessor
from docmolder.processing import ProcessingOutput
from docmolder.processing import ProcessingResult
from docmolder.models import CompressionPreset, FileKind, SupportedAction, UserSession
from docmolder.keyboards import build_main_menu_keyboard
from docmolder.session_store import InMemorySessionStore
from docmolder.action_catalog import build_session_file


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

    def test_build_application_registers_reduced_command_surface(self) -> None:
        application = build_application(self.settings)

        commands = [next(iter(handler.commands)) for handler in application.handlers[0] if hasattr(handler, "commands")]

        self.assertEqual(commands, ["start", "help", "history", "status", "reset", "admin"])
        self.assertNotIn("ping", commands)

    def test_access_service_mode_metrics_and_preset_helpers(self) -> None:
        restricted_settings = self.settings.model_copy(update={"allowed_user_ids": [1], "admin_user_ids": [99]})
        restricted_deps = BotDependencies(restricted_settings, InMemorySessionStore(), self.processor)

        self.assertFalse(_is_authorized(None, restricted_settings))
        self.assertTrue(_is_authorized(1, restricted_settings))
        self.assertFalse(_is_authorized(7, restricted_settings))
        self.assertFalse(_is_authorized_for_deps(None, restricted_deps))
        self.assertTrue(_is_authorized_for_deps(99, restricted_deps))
        self.assertFalse(_is_authorized_for_deps(7, restricted_deps))

        _set_dynamic_access_status(restricted_deps, 7, " APPROVED ")
        _set_dynamic_access_status(restricted_deps, 8, "blocked")
        restricted_deps.session_store.set_meta("access:not-a-user:status", "pending")
        self.assertEqual(_get_dynamic_access_status(restricted_deps, 7), "approved")
        self.assertTrue(_is_authorized_for_deps(7, restricted_deps))
        self.assertFalse(_is_authorized_for_deps(8, restricted_deps))
        self.assertEqual(_list_dynamic_access_statuses(restricted_deps), [(7, " APPROVED "), (8, "blocked")])

        self.assertEqual(_get_service_mode(self.deps), "normal")
        self.assertEqual(_build_service_status_label(self.deps), "attivo")
        _set_service_mode(self.deps, "maintenance")
        self.assertTrue(_is_service_paused(self.deps))
        self.assertEqual(_build_service_status_label(self.deps), "manutenzione")
        _set_service_mode(self.deps, "unknown")
        self.assertEqual(_get_service_mode(self.deps), "normal")

        self.store.set_meta("counter", "not-a-number")
        self.assertEqual(_get_meta_counter(self.deps, "counter"), 0)
        _increment_meta_counter(self.deps, "counter", amount=3)
        self.assertEqual(_get_meta_counter(self.deps, "counter"), 3)
        _record_command_metric(self.deps, "start")
        _record_callback_metric(self.deps, "compress:medium")
        _record_upload_metric(self.deps, "pdf")
        self.assertEqual(self.store.get_meta("telegram_metric:command:start"), "1")
        self.assertEqual(self.store.get_meta("telegram_metric:callback:compress:medium"), "1")
        self.assertEqual(self.store.get_meta("telegram_metric:upload:pdf"), "1")

        self.store.set_user_preference(7, "compression_preset", "invalid")
        self.assertIsNone(_get_stored_compression_preset(self.deps, 7))
        self.store.set_user_preference(7, "compression_preset", "medium")
        self.assertEqual(_resolve_compression_preset_for_job(self.deps, 7, None), CompressionPreset.MEDIUM)
        self.assertEqual(
            _resolve_compression_preset_for_job(self.deps, 7, CompressionPreset.LIGHT),
            CompressionPreset.LIGHT,
        )

        self.store.set_user_preference(7, "custom:last", "zip")
        self.store.set_user_preference(7, "custom:streak", "bad")
        _record_user_choice(self.deps, 7, "custom", "zip")
        _record_user_choice(self.deps, 7, "custom", "zip")
        self.assertEqual(self.store.get_user_preset(7, "custom"), "zip")

        _record_split_output_choice(self.deps, 7, split_output_zip=False)
        _record_split_output_choice(self.deps, 7, split_output_zip=False)
        self.assertEqual(_get_stored_split_output_choice(self.deps, 7, preset_only=True), "files")
        _record_image_pdf_choice(self.deps, 7, image_pdf_use_a4=True, image_pdf_margin_px=48)
        _record_image_pdf_choice(self.deps, 7, image_pdf_use_a4=True, image_pdf_margin_px=48)
        self.assertEqual(_get_stored_image_pdf_layout(self.deps, 7, preset_only=True), "a4")
        self.assertEqual(_get_stored_image_pdf_margin(self.deps, 7, preset_only=True), "48")

    def test_upload_history_audit_and_format_helpers(self) -> None:
        self.assertEqual(list(_load_persisted_upload_history(7, self.deps)), [])
        self.store.set_meta("upload_burst:7", "{bad-json")
        self.assertEqual(list(_load_persisted_upload_history(7, self.deps)), [])
        self.store.set_meta("upload_burst:7", '{"not":"a-list"}')
        self.assertEqual(list(_load_persisted_upload_history(7, self.deps)), [])

        now = datetime.now(timezone.utc)
        old_timestamp = (now - timedelta(seconds=self.settings.upload_burst_window_seconds + 10)).timestamp()
        recent_timestamp = (now - timedelta(seconds=1)).timestamp()
        self.store.set_meta("upload_burst:7", f'["bad",{old_timestamp},{recent_timestamp}]')
        history = _load_persisted_upload_history(7, self.deps)
        self.assertEqual(len(history), 1)
        _persist_upload_history(8, self.deps, deque([now]))
        self.assertTrue(self.store.get_meta("upload_burst:8").startswith("["))

        self.assertFalse(_is_replayed_callback(self.deps, user_id=7, callback_data="admin:pause", message_id=None))
        self.assertTrue(_is_replayed_callback(self.deps, user_id=7, callback_data="admin:pause", message_id=None))
        _append_audit_log(self.deps, "test_event", actor_user_id=7, outcome="ok", target_user_id=8, detail="detail")
        self.assertEqual(self.store.list_audit_log_entries(limit=1)[0].event_type, "test_event")
        with patch.object(self.store, "append_audit_log_entry", side_effect=RuntimeError("audit failed")), self.assertLogs(
            "docmolder.bot",
            level="ERROR",
        ):
            _append_audit_log(self.deps, "test_event", actor_user_id=7, outcome="failed")

        self.assertEqual(_format_duration_ms(999), "999ms")
        self.assertEqual(_format_duration_ms(1500), "1.5s")
        self.assertEqual(_format_bytes(900), "900 B")
        self.assertEqual(_format_bytes(2048), "2.0 KB")
        self.assertEqual(_format_bytes(2 * 1024 * 1024), "2.0 MB")

        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action=SupportedAction.PDF_COMPRESS.value,
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(job.id, "errore test")
        failed_job = self.store.get_job(job.id)
        self.assertIn("errore test", _format_job_line(failed_job))

        session = UserSession(user_id=7, files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)])
        self.assertEqual(_build_image_session_intro(session), "Immagine ricevuta.")
        result_session = _build_result_pdf_session(7, "file-id", None)
        self.assertEqual(result_session.files[0].file_name, "pdf_file-id")

        first_path = self.runtime_dir / "first.bin"
        second_path = self.runtime_dir / "second.bin"
        missing_path = self.runtime_dir / "missing.bin"
        first_path.write_bytes(b"x" * 10)
        second_path.write_bytes(b"y" * 20)
        self.assertEqual(_sum_file_sizes([first_path, missing_path, second_path]), 30)
        result = ProcessingResult(
            output_path=first_path,
            output_name=first_path.name,
            message="ok",
            additional_outputs=[ProcessingOutput(path=second_path, name=second_path.name)],
        )
        self.assertEqual(_sum_processing_result_sizes(result), 30)

    def test_main_menu_keyboard_exposes_quick_templates(self) -> None:
        keyboard = build_main_menu_keyboard()

        labels = [button.text for row in keyboard.keyboard for button in row]
        self.assertIn("Guida rapida", labels)
        self.assertIn("Crea PDF", labels)
        self.assertIn("Foto in A4", labels)
        self.assertIn("Scansiona e comprimi", labels)

    async def test_sync_telegram_branding_updates_profile_metadata(self) -> None:
        self.bot.set_my_name = AsyncMock()
        self.bot.set_my_description = AsyncMock()
        self.bot.set_my_short_description = AsyncMock()
        self.bot.set_my_commands = AsyncMock()
        self.bot.set_chat_menu_button = AsyncMock()

        await _sync_telegram_branding(self.application, self.settings)

        self.bot.set_my_name.assert_any_await(TELEGRAM_NAME)
        self.bot.set_my_name.assert_any_await(TELEGRAM_NAME, language_code="it")
        self.bot.set_my_commands.assert_any_await(build_telegram_commands())
        self.bot.set_chat_menu_button.assert_awaited_once()

    async def test_sync_telegram_branding_persists_rate_limit_backoff(self) -> None:
        self.bot.set_my_name = AsyncMock(side_effect=RetryAfter(120))
        self.bot.set_my_description = AsyncMock()
        self.bot.set_my_short_description = AsyncMock()
        self.bot.set_my_commands = AsyncMock()
        self.bot.set_chat_menu_button = AsyncMock()

        await _sync_telegram_branding(self.application, self.settings, self.store)
        await _sync_telegram_branding(self.application, self.settings, self.store)

        self.assertIsNotNone(self.store.get_meta("branding_sync:retry_at"))
        self.assertEqual(self.bot.set_my_name.await_count, 1)

    def test_build_text_request_queued_message_mentions_fallback_for_pdf_grayscale(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_GRAYSCALE, 12, None)

        self.assertIn("fallback", message)
        self.assertIn("Job #12", message)

    def test_build_text_request_queued_message_mentions_longer_processing_for_medium_compression(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.PDF_COMPRESS, 13, CompressionPreset.MEDIUM)

        self.assertIn("più tempo", message)
        self.assertIn("fallback", message)

    def test_image_crop_message_distinguishes_source_images_from_pdf_crop(self) -> None:
        message = _build_text_request_queued_message(SupportedAction.IMAGES_TO_PDF_CROP, 14, None)

        self.assertIn("Ritaglio automatico delle immagini", message)
        self.assertIn("Job #14", message)

    def test_build_result_delivery_message_suggests_followup_actions_for_pdf(self) -> None:
        result = ProcessingResult(
            output_path=Path("/tmp/output.pdf"),
            output_name="output.pdf",
            message="PDF pronto.",
        )

        message = _build_result_delivery_message(result, SupportedAction.PDF_GRAYSCALE)

        self.assertIn("continuare su questo PDF", message)
        self.assertIn("Comprimi PDF", message)
        self.assertIn("/history", message)
        self.assertIn("/status", message)

    def test_build_compression_prompt_mentions_saved_preference(self) -> None:
        self.store.set_user_preference(7, "compression_preset", "medium")

        message = _build_compression_prompt(7, self.deps)

        self.assertIn("Ultima scelta rapida salvata: medium", message)

    def test_repeated_user_choice_promotes_lightweight_preset(self) -> None:
        _record_user_choice(self.deps, 7, "compression_preset", "strong")
        self.assertEqual(self.store.get_user_preference(7, "compression_preset"), "strong")
        self.assertIsNone(self.store.get_user_preset(7, "compression_preset"))

        _record_user_choice(self.deps, 7, "compression_preset", "strong")

        self.assertEqual(self.store.get_user_preset(7, "compression_preset"), "strong")

    def test_build_compression_prompt_mentions_promoted_preset(self) -> None:
        self.store.set_user_preset(7, "compression_preset", "strong")

        message = _build_compression_prompt(7, self.deps)

        self.assertIn("Preset leggero pronto: strong", message)

    def test_build_split_output_prompt_mentions_promoted_preset(self) -> None:
        self.store.set_user_preset(7, "split_output", "files")

        message = _build_split_output_prompt(7, self.deps)

        self.assertIn("Preset leggero pronto: PDF separati", message)

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

    def test_build_limit_messages_include_current_values(self) -> None:
        self.assertIn("20 MB", _build_file_too_large_message(20))
        self.assertIn("12 file", _build_session_file_limit_message(12))
        self.assertIn("3 file in 30 secondi", _build_upload_rate_limit_message(3, 30))
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _build_unsupported_document_message(
                SimpleNamespace(
                    file_name="contratto.docx",
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ),
        )
        text_file_message = _build_unsupported_document_message(SimpleNamespace(file_name="note.txt", mime_type=None))
        self.assertIn("esportalo in PDF", text_file_message)
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

    async def test_context_reference_without_active_session_asks_for_safe_next_step(self) -> None:
        message = SimpleNamespace(
            text="Comprimi questo PDF",
            chat_id=99,
            message_id=502,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        self.assertIn("non ho ancora un PDF attivo", message.reply_text.await_args.args[0])

    async def test_start_deep_link_access_is_no_longer_a_shortcut(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=778)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["access"])

        await start_command(update, context)

        self.assertIn("DocMolder", message.reply_text.await_args.args[0])

    async def test_new_user_notification_is_throttled_and_then_summarized(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user_one = SimpleNamespace(id=7, username="uno", first_name="Uno", last_name="Test", full_name="Uno Test")
        user_two = SimpleNamespace(id=8, username="due", first_name="Due", last_name="Test", full_name="Due Test")
        user_three = SimpleNamespace(id=9, username="tre", first_name="Tre", last_name="Test", full_name="Tre Test")

        await _maybe_notify_admins_about_new_user(user_one, context)
        await _maybe_notify_admins_about_new_user(user_two, context)
        self.assertEqual(self.bot.send_message.await_count, 1)

        old_time = "2000-01-01T00:00:00+00:00"
        self.store.set_meta("new_user_notice:999:last_sent_at", old_time)
        await _maybe_notify_admins_about_new_user(user_three, context)

        self.assertEqual(self.bot.send_message.await_count, 2)
        self.assertIn("altri 1 utenti nuovi", self.bot.send_message.await_args_list[-1].kwargs["text"])

    async def test_menu_text_guida_rapida_delegates_to_help(self) -> None:
        message = SimpleNamespace(
            text="Guida rapida",
            chat_id=99,
            message_id=7901,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Ecco come usare", message.reply_text.await_args.args[0])

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
        self.assertIn("Stato accesso DocMolder", message.reply_text.await_args.args[0])
        self.assertIn("Sessione corrente: vuota", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_new_status_button_works_and_refreshes_keyboard(self) -> None:
        message = SimpleNamespace(
            text="Sessione attiva",
            chat_id=99,
            message_id=8021,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Stato accesso DocMolder", message.reply_text.await_args.args[0])
        self.assertIn("Sessione corrente: vuota", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_legacy_reset_button_still_works_and_refreshes_keyboard(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        self.store.set_user_preference(7, "compression_preset", "medium")
        self.store.set_user_preset(7, "compression_preset", "medium")
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

        self.assertEqual(message.reply_text.await_count, 2)
        self.assertIn("Sessione azzerata", message.reply_text.await_args_list[0].args[0])
        self.assertIn("ultime scelte rapide", message.reply_text.await_args_list[0].args[0])
        self.assertIsNotNone(message.reply_text.await_args_list[0].kwargs["reply_markup"])
        self.assertIn("Cancella tutti i miei dati", str(message.reply_text.await_args_list[1].kwargs["reply_markup"]))
        self.assertIsNone(self.store.get(7))
        self.assertIsNone(self.store.get_user_preference(7, "compression_preset"))
        self.assertIsNone(self.store.get_user_preset(7, "compression_preset"))

    async def test_delete_data_callback_requires_confirmation_then_deletes_live_data(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        self.store.set_user_preference(7, "compression_preset", "medium")
        self.store.set_user_preset(7, "compression_preset", "medium")
        self.store.set_meta("access:7:status", "approved")
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=None,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(job.id, "ok")
        query = SimpleNamespace(
            data="delete_data:request",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_delete_data_callback(update, context)

        self.assertIn("Confermi", query.edit_message_text.await_args.args[0])
        self.assertIn("Conferma cancellazione", str(query.edit_message_text.await_args.kwargs["reply_markup"]))

        query.data = "delete_data:confirm"
        await handle_delete_data_callback(update, context)

        self.assertIn("Dati live cancellati", query.edit_message_text.await_args.args[0])
        self.assertIsNone(self.store.get(7))
        self.assertIsNone(self.store.get_user_preference(7, "compression_preset"))
        self.assertIsNone(self.store.get_user_preset(7, "compression_preset"))
        self.assertIsNone(self.store.get_meta("access:7:status"))
        self.assertIsNone(self.store.get_job(job.id))
        self.assertEqual(self.store.list_audit_log_entries(limit=1)[0].event_type, "user_data_deleted")

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

    async def test_document_upload_rejects_unsupported_file_with_next_step(self) -> None:
        context = SimpleNamespace(application=self.application, bot=self.bot)
        user = SimpleNamespace(id=7, username=None, first_name="Test", last_name=None)
        document_message = SimpleNamespace(
            chat_id=99,
            message_id=1199,
            document=SimpleNamespace(
                file_id="docx-telegram-id",
                file_name="contratto.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                file_size=1024,
            ),
            reply_text=AsyncMock(),
        )

        await handle_document(
            SimpleNamespace(effective_user=user, effective_message=document_message),
            context,
        )

        self.assertIsNone(self.store.get(7))
        document_message.reply_text.assert_awaited_once()
        reply_text = document_message.reply_text.await_args.args[0]
        self.assertIn("Non riesco a lavorare questo tipo di file", reply_text)
        self.assertIn("esportalo in PDF", reply_text)
        self.assertIn("application/vnd.openxmlformats-officedocument.wordprocessingml.document", reply_text)

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

if __name__ == "__main__":
    unittest.main()
