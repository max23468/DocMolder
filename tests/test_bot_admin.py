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

from docmolder.bot_runtime import (
    BotDependencies,
    _build_service_unavailable_message,
    _maybe_notify_admins_about_new_user,
    _retry_after_seconds,
    _telegram_api_call,
)
from docmolder.messages import ADMIN_ONLY_MESSAGE
from docmolder.admin_reporting import (
    _build_admin_health_report,
    _build_admin_maintenance_overview,
    _build_admin_queue_report,
    _build_telegram_metrics_report,
    _extract_metric_entries,
)
from docmolder.bot_admin import (
    handle_admin_callback,
    admin_command,
    handle_access_review_callback,
)
from docmolder.bot_results import (
    _resolve_job_selector,
)
from docmolder.bot_menu import (
    _build_policy_message,
    _handle_start_payload,
    handle_menu_text,
    start_command,
)
from docmolder.bot_sessions import (
    _build_access_status_message,
    status_command,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import FileKind, UserSession
from docmolder.in_memory_session_store import InMemorySessionStore
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
        with patch("docmolder.bot_runtime.asyncio.sleep", new=AsyncMock()) as sleep_mock:
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
