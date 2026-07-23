from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telegram.error import TelegramError
from telegram.error import NetworkError, RetryAfter

from docmolder.bot import (
    BotDependencies,
    ADMIN_ONLY_MESSAGE,
    _build_access_status_message,
    _build_admin_health_report,
    _build_admin_maintenance_overview,
    _build_admin_queue_report,
    _build_policy_message,
    _build_service_unavailable_message,
    _build_telegram_metrics_report,
    _extract_metric_entries,
    _resolve_job_selector,
    _resolve_user_job_selector,
    _retry_after_seconds,
    _telegram_api_call,
    _handle_start_payload,
    _maybe_notify_admins_about_new_user,
    handle_admin_callback,
    access_command,
    access_review_command,
    admin_command,
    handle_access_review_callback,
    handle_menu_text,
    health_command,
    job_command,
    metrics_command,
    pause_command,
    policy_command,
    queue_command,
    request_access_command,
    retry_command,
    resume_command,
    start_command,
    status_command,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import FileKind, UserSession
from docmolder.session_store import InMemorySessionStore
from docmolder.action_catalog import build_session_file


class BotAdminTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_pause_and_resume_commands_toggle_service_mode(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await pause_command(update, context)
        self.assertEqual(self.store.get_meta("service_mode"), "maintenance")

        await resume_command(update, context)
        self.assertEqual(self.store.get_meta("service_mode"), "normal")
        self.assertEqual(
            [entry.outcome for entry in self.store.list_audit_log_entries(limit=2)],
            ["normal", "maintenance"],
        )
        self.assertEqual(message.reply_text.await_count, 2)

    async def test_maintenance_mode_blocks_regular_user_text_requests(self) -> None:
        self.store.set_meta("service_mode", "maintenance")
        message = SimpleNamespace(text="ciao", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username=None, first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        message.reply_text.assert_awaited_once_with(_build_service_unavailable_message())

    async def test_admin_callback_pause_updates_dashboard(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        query = SimpleNamespace(
            data="admin:pause",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            message=SimpleNamespace(message_id=54),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)

        self.assertEqual(self.store.get_meta("service_mode"), "maintenance")
        query.edit_message_text.assert_awaited_once()
        self.assertIn("modalità manutenzione", query.edit_message_text.await_args.args[0])

    async def test_admin_command_rejects_non_admin_user(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username=None, first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await admin_command(update, context)

        message.reply_text.assert_awaited_once_with(ADMIN_ONLY_MESSAGE)

    async def test_admin_callback_rejects_non_admin_user(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        query = SimpleNamespace(
            data="admin:queue",
            from_user=SimpleNamespace(id=55, username=None, first_name="Mario", last_name=None),
            message=SimpleNamespace(message_id=54),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)

        query.edit_message_text.assert_awaited_once_with(ADMIN_ONLY_MESSAGE)

    async def test_admin_callback_replay_is_blocked(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        query = SimpleNamespace(
            data="admin:pause",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            message=SimpleNamespace(message_id=55),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)
        await handle_admin_callback(update, context)

        self.assertIn("Azione già ricevuta", query.edit_message_text.await_args_list[-1].args[0])

    async def test_queue_and_health_commands_return_live_reports(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        queued_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(queued_job.id)
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await queue_command(update, context)
        await health_command(update, context)

        self.assertIn("Coda operativa", message.reply_text.await_args_list[0].args[0])
        self.assertIn("Health operativo", message.reply_text.await_args_list[1].args[0])

    async def test_unauthorized_user_attempt_creates_pending_access_request(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        self.deps.settings.admin_user_ids = [999]
        self.bot.send_message = AsyncMock()
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await start_command(update, context)

        self.assertEqual(self.store.get_meta("access:55:status"), "pending")
        self.bot.send_message.assert_awaited_once()
        self.assertIn("richiesta all'admin", message.reply_text.await_args.args[0])

    async def test_unauthorized_text_attempt_creates_pending_access_request(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        self.deps.settings.admin_user_ids = [999]
        self.bot.send_message = AsyncMock()
        message = SimpleNamespace(text="Ciao", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(self.store.get_meta("access:55:status"), "pending")
        self.bot.send_message.assert_awaited_once()
        self.assertIn("richiesta all'admin", message.reply_text.await_args.args[0])

    async def test_request_access_command_does_not_duplicate_pending_request(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        self.deps.settings.admin_user_ids = [999]
        self.bot.send_message = AsyncMock()
        self.store.set_meta("access:55:status", "pending")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await request_access_command(update, context)

        self.assertEqual(self.store.get_meta("access:55:status"), "pending")
        self.bot.send_message.assert_not_awaited()
        self.assertEqual(self.store.list_audit_log_entries(limit=10), [])
        self.assertIn("già in attesa di approvazione", message.reply_text.await_args.args[0])

    async def test_access_review_command_approves_dynamic_user(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        self.deps.settings.admin_user_ids = [7]
        message = SimpleNamespace(text="/approve_user 55", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["55"])

        await access_review_command(update, context)

        self.assertEqual(self.store.get_meta("access:55:status"), "approved")
        self.assertIn("approved", message.reply_text.await_args.args[0])
        self.assertEqual(self.store.list_audit_log_entries(limit=1)[0].event_type, "access_review")

    async def test_access_review_callback_approves_pending_user(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        query = SimpleNamespace(
            data="access:approve:55",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_access_review_callback(update, context)

        self.assertEqual(self.store.get_meta("access:55:status"), "approved")
        self.assertIn("approved", query.edit_message_text.await_args.args[0])

    def test_policy_and_maintenance_overview_include_operational_data(self) -> None:
        self.settings.sqlite_backup_dir = self.runtime_dir / "backups"
        self.settings.sqlite_backup_dir.mkdir(parents=True, exist_ok=True)
        self.store.set_meta("access:55:status", "pending")

        policy = _build_policy_message(self.deps)
        maintenance = _build_admin_maintenance_overview(self.deps)

        self.assertIn("Policy sintetica", policy)
        self.assertIn("file massimo", policy)
        self.assertIn("cancellare tutti i dati live", policy)
        self.assertIn("docmolder.duckdns.org/privacy.html", policy)
        self.assertIn("Manutenzione operativa", maintenance)
        self.assertIn("Richieste accesso pending", maintenance)
        self.assertIn("Soglie crescita prudente", maintenance)
        self.assertIn("Ultimo pruning job", maintenance)

    async def test_telegram_api_call_retries_rate_limit_and_network_errors(self) -> None:
        mocked_call = AsyncMock(side_effect=[RetryAfter(1), NetworkError("temp"), "ok"])
        with patch("docmolder.bot.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await _telegram_api_call("sendMessage", mocked_call)

        self.assertEqual(result, "ok")
        self.assertEqual(mocked_call.await_count, 3)
        self.assertEqual(sleep_mock.await_count, 2)

    def test_retry_after_seconds_handles_int_and_timedelta(self) -> None:
        # PTB >=22.2: RetryAfter.retry_after può essere timedelta (PTB_TIMEDELTA=1),
        # dove int(exc.retry_after) crasherebbe con TypeError.
        self.assertEqual(_retry_after_seconds(RetryAfter(5), 1), 5)
        self.assertEqual(_retry_after_seconds(RetryAfter(timedelta(seconds=7)), 1), 7)
        self.assertEqual(_retry_after_seconds(object(), 3), 3)
        self.assertEqual(_retry_after_seconds(RetryAfter(timedelta(milliseconds=400)), 1), 1)

    def test_admin_reports_include_new_operational_sections(self) -> None:
        queue_report = _build_admin_queue_report(self.deps)
        health_report = _build_admin_health_report(self.deps)
        access_report = _build_access_status_message(self.deps, 7)
        metrics_report = _build_telegram_metrics_report(self.deps)

        self.assertIn("Service mode", queue_report)
        self.assertIn("Coda in memoria", queue_report)
        self.assertIn("Ultimi job falliti", queue_report)
        self.assertIn("Errori ricorrenti recenti", queue_report)
        self.assertIn("Database SQLite", health_report)
        self.assertIn("Utenti attivi 24h/7g", health_report)
        self.assertIn("Failure rate 24h", health_report)
        self.assertIn("file)", health_report)
        self.assertIn("Worker job", health_report)
        self.assertIn("Stato accesso DocMolder", access_report)
        self.assertIn("/history", access_report)
        self.assertIn("/start privacy", access_report)
        self.assertIn("Metriche Telegram", metrics_report)

    async def test_start_privacy_payload_returns_public_policy(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(application=self.application, bot=self.bot)

        handled = await _handle_start_payload("privacy", self.deps, 7, message, context)

        self.assertTrue(handled)
        self.assertIn("Policy sintetica", message.reply_text.await_args.args[0])
        self.assertIn("docmolder.duckdns.org/privacy.html", message.reply_text.await_args.args[0])

    async def test_status_command_returns_access_summary(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_watermark",
            )
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await status_command(update, context)

        self.assertIn("Accesso account: consentito", message.reply_text.await_args.args[0])
        self.assertIn("Input atteso: Watermark testuale", message.reply_text.await_args.args[0])
        self.assertIn("/history", message.reply_text.await_args.args[0])

    async def test_access_command_returns_access_summary_without_active_session(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await access_command(update, context)

        self.assertIn("Stato accesso DocMolder", message.reply_text.await_args.args[0])
        self.assertIn("Accesso account: consentito", message.reply_text.await_args.args[0])

    async def test_policy_command_remains_available_to_restricted_user(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await policy_command(update, context)

        self.assertIn(55, self.store._known_user_ids)
        self.assertIn("Policy sintetica", message.reply_text.await_args.args[0])
        self.assertIn("privacy.html", message.reply_text.await_args.args[0])

    async def test_request_access_command_reports_active_access_without_admin_ping(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.bot.send_message = AsyncMock()
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await request_access_command(update, context)

        self.bot.send_message.assert_not_awaited()
        self.assertIn("già attivo", message.reply_text.await_args.args[0])

    async def test_request_access_command_reports_blocked_access_without_admin_ping(self) -> None:
        self.deps.settings.allowed_user_ids = [7]
        self.deps.settings.admin_user_ids = [999]
        self.bot.send_message = AsyncMock()
        self.store.set_meta("access:55:status", "blocked")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=55, username="mario", first_name="Mario", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await request_access_command(update, context)

        self.bot.send_message.assert_not_awaited()
        self.assertIn("accesso è sospeso", message.reply_text.await_args.args[0])

    async def test_metrics_command_returns_telegram_metrics_report(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        self.store.set_meta("telegram_metric:command:start", "4")
        self.store.set_meta("telegram_metric:upload:photo", "2")
        self.store.set_meta("telegram_metric:callback:history:rerun", "3")
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await metrics_command(update, context)

        self.assertIn("Metriche Telegram", message.reply_text.await_args.args[0])
        self.assertIn("/start: 4", message.reply_text.await_args.args[0])
        self.assertIn("foto: 2", message.reply_text.await_args.args[0])
        self.assertIn("history:rerun: 3", message.reply_text.await_args.args[0])

    async def test_job_command_shows_job_detail_for_admin(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium"}',
        )
        self.store.mark_job_succeeded(job.id, "Completato")
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=400)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=[str(job.id)])

        await job_command(update, context)

        self.assertIn("Dettaglio Job", message.reply_text.await_args.args[0])
        self.assertIn("Compressione: medium", message.reply_text.await_args.args[0])

    async def test_job_command_accepts_failed_selector(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium"}',
        )
        self.store.mark_job_failed(job.id, "Errore di test")
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=402)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["failed"])

        await job_command(update, context)

        self.assertIn(f"Dettaglio Job #{job.id}", message.reply_text.await_args.args[0])

    async def test_job_command_accepts_succeeded_selector(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":null}',
        )
        self.store.mark_job_succeeded(job.id, "Completato")
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=404)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=["succeeded"])

        await job_command(update, context)

        self.assertIn(f"Dettaglio Job #{job.id}", message.reply_text.await_args.args[0])

    async def test_retry_command_requeues_existing_job_for_admin(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        source_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":null}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=401)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=[str(source_job.id)])

        await retry_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 1)
        self.assertEqual(queued_jobs[0].rerun_of_job_id, source_job.id)
        self.assertEqual(self.store.list_audit_log_entries(limit=1)[0].event_type, "admin_retry_job")
        self.assertIn("Ripeto il job", message.reply_text.await_args.args[0])

    async def test_retry_command_can_disable_auto_rotation(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        source_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[{"telegram_file_id":"pdf-1","file_name":"documento.pdf","kind":"pdf"}],"compression_preset":"medium","auto_rotate_pdf":true}',
        )
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=403)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=[str(source_job.id), "--no-auto-rotate"])

        await retry_command(update, context)

        queued_jobs = [job for job in self.store._jobs.values() if job.id != source_job.id]
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"auto_rotate_pdf": false', queued_jobs[0].payload_json)
        self.assertIn("senza rotazione automatica", message.reply_text.await_args.args[0])

    def test_resolve_job_selector_supports_latest_failed_and_running(self) -> None:
        latest_job = self.store.create_job(
            user_id=1,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        failed_job = self.store.create_job(
            user_id=1,
            chat_id=99,
            reply_to_message_id=124,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "boom")
        running_job = self.store.create_job(
            user_id=1,
            chat_id=99,
            reply_to_message_id=125,
            action="pdf_merge",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(running_job.id)
        succeeded_job = self.store.create_job(
            user_id=1,
            chat_id=99,
            reply_to_message_id=126,
            action="pdf_delete_pages",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(succeeded_job.id, "ok")

        self.assertEqual(_resolve_job_selector(self.deps, "latest").id, succeeded_job.id)
        self.assertEqual(_resolve_job_selector(self.deps, "failed").id, failed_job.id)
        self.assertEqual(_resolve_job_selector(self.deps, "running").id, running_job.id)
        self.assertEqual(_resolve_job_selector(self.deps, "queued").id, latest_job.id)
        self.assertEqual(_resolve_job_selector(self.deps, "succeeded").id, succeeded_job.id)
        self.assertEqual(_resolve_job_selector(self.deps, str(latest_job.id)).id, latest_job.id)

    def test_resolve_user_job_selector_scopes_latest_to_user(self) -> None:
        own_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.create_job(
            user_id=8,
            chat_id=99,
            reply_to_message_id=124,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )

        self.assertEqual(_resolve_user_job_selector(self.deps, 7, "latest").id, own_job.id)

    def test_resolve_user_job_selector_rejects_other_user_job_id(self) -> None:
        other_job = self.store.create_job(
            user_id=8,
            chat_id=99,
            reply_to_message_id=124,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )

        self.assertIsNone(_resolve_user_job_selector(self.deps, 7, str(other_job.id)))

    def test_resolve_user_job_selector_finds_status_beyond_recent_page(self) -> None:
        failed_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "boom")
        for index in range(60):
            self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=200 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )

        self.assertEqual(_resolve_user_job_selector(self.deps, 7, "failed").id, failed_job.id)

    def test_extract_metric_entries_sorts_by_count_desc(self) -> None:
        entries = _extract_metric_entries(
            {
                "telegram_metric:callback:b": "2",
                "telegram_metric:callback:a": "5",
                "telegram_metric:callback:c": "1",
            },
            "telegram_metric:callback:",
        )

        self.assertEqual(entries, [("a", 5), ("b", 2), ("c", 1)])

    async def test_admin_callback_failed_shows_latest_failed_job(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        failed_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")
        query = SimpleNamespace(
            data="admin:failed",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            message=SimpleNamespace(message_id=90),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)

        self.assertIn(f"Dettaglio Job #{failed_job.id}", query.edit_message_text.await_args.args[0])

    async def test_admin_callback_succeeded_shows_latest_succeeded_job(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        succeeded_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(succeeded_job.id, "ok")
        query = SimpleNamespace(
            data="admin:succeeded",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            message=SimpleNamespace(message_id=91),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)

        self.assertIn(f"Dettaglio Job #{succeeded_job.id}", query.edit_message_text.await_args.args[0])

    async def test_admin_callback_latest_shows_latest_job(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        latest_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_delete_pages",
            payload_json='{"files":[]}',
        )
        query = SimpleNamespace(
            data="admin:latest",
            from_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            message=SimpleNamespace(message_id=92),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_admin_callback(update, context)

        self.assertIn(f"Dettaglio Job #{latest_job.id}", query.edit_message_text.await_args.args[0])

    async def test_retry_command_help_mentions_supported_selectors(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        message = SimpleNamespace(reply_text=AsyncMock(), message_id=405)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Admin", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot, args=[])

        await retry_command(update, context)

        self.assertIn("latest|failed|running|queued|succeeded", message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
