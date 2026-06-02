from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telegram.error import BadRequest

from docmolder.action_catalog import build_session_file
from docmolder.bot import (
    ADMIN_ONLY_MESSAGE,
    BotDependencies,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    _invalid_callback_message,
    access_review_command,
    admin_command,
    handle_access_review_callback,
    handle_action_callback,
    handle_admin_callback,
    handle_compression_callback,
    handle_delete_data_callback,
    handle_split_output_callback,
    maintenance_overview_command,
    request_access_command,
)
from docmolder.config import Settings
from docmolder.models import FileKind, SupportedAction, UserSession
from docmolder.processing import DocumentProcessor
from docmolder.processing import ProcessingUserError
from docmolder.session_store import InMemorySessionStore


class BotOfflineCoverageTest(unittest.IsolatedAsyncioTestCase):
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

    def _context(self, *, args: list[str] | None = None) -> SimpleNamespace:
        return SimpleNamespace(application=self.application, bot=self.bot, args=args or [])

    def _user(self, user_id: int = 7, *, username: str | None = None, first_name: str = "Test") -> SimpleNamespace:
        return SimpleNamespace(id=user_id, username=username, first_name=first_name, last_name=None)

    def _message(
        self,
        *,
        text: str | None = None,
        message_id: int = 700,
        chat_id: int = 99,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            text=text,
            message_id=message_id,
            chat_id=chat_id,
            reply_text=AsyncMock(),
        )

    def _query(
        self,
        data: str,
        *,
        user_id: int = 7,
        message_id: int = 700,
        chat_id: int = 99,
        username: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            data=data,
            from_user=self._user(user_id, username=username),
            message=SimpleNamespace(chat_id=chat_id, message_id=message_id, reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )

    def _save_pdf_session(self, *, user_id: int = 7, pending_action: str | None = None) -> None:
        self.store.save(
            UserSession(
                user_id=user_id,
                pending_action=pending_action,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )

    def _save_image_session(self, *, user_id: int = 7, pending_action: str | None = None) -> None:
        self.store.save(
            UserSession(
                user_id=user_id,
                pending_action=pending_action,
                files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)],
            )
        )

    async def test_request_access_command_records_new_pending_request(self) -> None:
        self.deps.settings.allowed_user_ids = [999]
        self.deps.settings.admin_user_ids = [42]
        message = self._message()
        update = SimpleNamespace(
            effective_user=self._user(7, username="mario"),
            effective_message=message,
        )

        await request_access_command(update, self._context())

        self.assertEqual(self.store.get_meta("access:7:status"), "pending")
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(self.store.list_audit_log_entries(limit=1)[0].event_type, "request_access")
        self.assertIn("Richiesta accesso inviata", message.reply_text.await_args.args[0])

    async def test_admin_and_maintenance_commands_render_admin_views(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        admin_message = self._message(message_id=701)
        maintenance_message = self._message(message_id=702)
        admin_update = SimpleNamespace(effective_user=self._user(7), effective_message=admin_message)
        maintenance_update = SimpleNamespace(effective_user=self._user(7), effective_message=maintenance_message)

        await admin_command(admin_update, self._context())
        await maintenance_overview_command(maintenance_update, self._context())

        self.assertIsNotNone(admin_message.reply_text.await_args.kwargs["reply_markup"])
        self.assertIsNotNone(maintenance_message.reply_text.await_args.kwargs["reply_markup"])
        self.assertIn("Utenti", admin_message.reply_text.await_args.args[0])
        self.assertIn("Manutenzione operativa", maintenance_message.reply_text.await_args.args[0])

    async def test_access_review_command_reports_usage_and_remaining_status_variants(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        missing_target_message = self._message(text="/approve_user", message_id=703)
        missing_target_update = SimpleNamespace(
            effective_user=self._user(7),
            effective_message=missing_target_message,
        )

        await access_review_command(missing_target_update, self._context())

        self.assertIn("Uso corretto", missing_target_message.reply_text.await_args.args[0])

        cases = [
            ("/reactivate_user 55", ["55"], "approved", "reactivated"),
            ("/suspend_user 56", ["56"], "blocked", "blocked"),
            ("/reject_user 57", ["57"], "rejected", "rejected"),
        ]
        for index, (command_text, args, expected_status, expected_outcome) in enumerate(cases, start=1):
            with self.subTest(command_text=command_text):
                message = self._message(text=command_text, message_id=710 + index)
                update = SimpleNamespace(effective_user=self._user(7), effective_message=message)

                await access_review_command(update, self._context(args=args))

                target_user_id = int(args[0])
                self.assertEqual(self.store.get_meta(f"access:{target_user_id}:status"), expected_status)
                self.assertIn(expected_outcome, message.reply_text.await_args.args[0])

    async def test_admin_callback_covers_remaining_dashboard_actions(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        queued_job = self.store.create_job(
            user_id=11,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_split",
            payload_json='{"files":[]}',
        )
        running_job = self.store.create_job(
            user_id=12,
            chat_id=99,
            reply_to_message_id=124,
            action="pdf_grayscale",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_running(running_job.id)

        cases = [
            ("admin:resume", "Servizio riattivato"),
            ("admin:queue", "Coda operativa"),
            ("admin:health", "Health operativo"),
            ("admin:metrics", "Metriche Telegram"),
            ("admin:maintenance", "Manutenzione operativa"),
            ("admin:running", f"Dettaglio Job #{running_job.id}"),
            ("admin:queued", f"Dettaglio Job #{queued_job.id}"),
            ("admin:overview", "Riepilogo admin DocMolder"),
        ]
        for index, (data, expected_text) in enumerate(cases, start=1):
            with self.subTest(data=data):
                query = self._query(data, message_id=720 + index)

                await handle_admin_callback(SimpleNamespace(callback_query=query), self._context())

                self.assertIn(expected_text, query.edit_message_text.await_args.args[0])

    async def test_admin_callback_ignores_message_not_modified_errors(self) -> None:
        self.deps.settings.admin_user_ids = [7]
        query = self._query("admin:queue", message_id=740)
        query.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))

        await handle_admin_callback(SimpleNamespace(callback_query=query), self._context())

        query.edit_message_text.assert_awaited_once()

    async def test_access_review_callback_covers_reject_and_invalid_paths(self) -> None:
        self.deps.settings.admin_user_ids = [7]

        non_admin_query = self._query("access:approve:55", user_id=8, message_id=750)
        await handle_access_review_callback(SimpleNamespace(callback_query=non_admin_query), self._context())
        non_admin_query.edit_message_text.assert_awaited_once_with(ADMIN_ONLY_MESSAGE)

        invalid_payload_query = self._query("access:approve:not-a-number", message_id=751)
        await handle_access_review_callback(SimpleNamespace(callback_query=invalid_payload_query), self._context())
        invalid_payload_query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

        invalid_action_query = self._query("access:suspend:55", message_id=752)
        await handle_access_review_callback(SimpleNamespace(callback_query=invalid_action_query), self._context())
        invalid_action_query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

        reject_query = self._query("access:reject:55", message_id=753)
        await handle_access_review_callback(SimpleNamespace(callback_query=reject_query), self._context())
        self.assertEqual(self.store.get_meta("access:55:status"), "rejected")
        self.assertIn("rejected", reject_query.edit_message_text.await_args.args[0])

    async def test_delete_data_callback_covers_missing_user_cancel_and_invalid_action(self) -> None:
        missing_user_query = SimpleNamespace(
            data="delete_data:confirm",
            from_user=None,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        await handle_delete_data_callback(SimpleNamespace(callback_query=missing_user_query), self._context())
        missing_user_query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

        cancel_query = self._query("delete_data:cancel", message_id=760)
        await handle_delete_data_callback(SimpleNamespace(callback_query=cancel_query), self._context())
        self.assertIn("annullata", cancel_query.edit_message_text.await_args.args[0])

        invalid_query = self._query("delete_data:unexpected", message_id=761)
        await handle_delete_data_callback(SimpleNamespace(callback_query=invalid_query), self._context())
        invalid_query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

    async def test_action_callback_covers_guard_and_prompt_branches(self) -> None:
        self.deps.settings.allowed_user_ids = [99]
        unauthorized_query = self._query("action:pdf_grayscale", message_id=770)
        await handle_action_callback(SimpleNamespace(callback_query=unauthorized_query), self._context())
        unauthorized_query.edit_message_text.assert_awaited_once_with(UNAUTHORIZED_MESSAGE)

        self.deps.settings.allowed_user_ids = []
        self.store.set_meta("service_mode", "maintenance")
        paused_query = self._query("action:pdf_grayscale", message_id=771)
        await handle_action_callback(SimpleNamespace(callback_query=paused_query), self._context())
        self.assertIn("manutenzione", paused_query.edit_message_text.await_args.args[0].lower())
        self.store.set_meta("service_mode", "normal")

        empty_query = self._query("action:pdf_grayscale", message_id=772)
        await handle_action_callback(SimpleNamespace(callback_query=empty_query), self._context())
        empty_query.edit_message_text.assert_awaited_once_with(SESSION_EMPTY_MESSAGE)

        self._save_pdf_session()
        compress_query = self._query("action:pdf_compress", message_id=773)
        await handle_action_callback(SimpleNamespace(callback_query=compress_query), self._context())
        self.assertIn("compressione", compress_query.edit_message_text.await_args.args[0].lower())

        self._save_pdf_session()
        rotate_query = self._query("action:pdf_rotate", message_id=774)
        await handle_action_callback(SimpleNamespace(callback_query=rotate_query), self._context())
        self.assertIn("Di quanti gradi", rotate_query.edit_message_text.await_args.args[0])

        self._save_image_session()
        document_photo_query = self._query("action:document_photo_fix", message_id=775)
        await handle_action_callback(SimpleNamespace(callback_query=document_photo_query), self._context())
        self.assertEqual(self.store.get(7).pending_action, "document_photo_mode")
        self.assertIn("come vuoi sistemare", document_photo_query.edit_message_text.await_args.args[0].lower())

        self._save_image_session()
        image_pdf_query = self._query("action:images_to_pdf", message_id=776)
        await handle_action_callback(SimpleNamespace(callback_query=image_pdf_query), self._context())
        self.assertIsNotNone(image_pdf_query.edit_message_text.await_args.kwargs["reply_markup"])

        self.deps.settings.max_active_jobs_per_user = 0
        self._save_pdf_session()
        limit_query = self._query("action:pdf_grayscale", message_id=777)
        await handle_action_callback(SimpleNamespace(callback_query=limit_query), self._context())
        self.assertIn("limite", limit_query.edit_message_text.await_args.args[0].lower())

    async def test_compression_callback_covers_guards_limit_and_success(self) -> None:
        self.deps.settings.allowed_user_ids = [99]
        unauthorized_query = self._query("compress:medium", message_id=780)
        await handle_compression_callback(SimpleNamespace(callback_query=unauthorized_query), self._context())
        unauthorized_query.edit_message_text.assert_awaited_once_with(UNAUTHORIZED_MESSAGE)

        self.deps.settings.allowed_user_ids = []
        self.store.set_meta("service_mode", "maintenance")
        paused_query = self._query("compress:medium", message_id=781)
        await handle_compression_callback(SimpleNamespace(callback_query=paused_query), self._context())
        self.assertIn("manutenzione", paused_query.edit_message_text.await_args.args[0].lower())
        self.store.set_meta("service_mode", "normal")

        empty_query = self._query("compress:medium", message_id=782)
        await handle_compression_callback(SimpleNamespace(callback_query=empty_query), self._context())
        empty_query.edit_message_text.assert_awaited_once_with(SESSION_EMPTY_MESSAGE)

        self.deps.settings.max_active_jobs_per_user = 0
        self._save_pdf_session()
        limit_query = self._query("compress:medium", message_id=783)
        await handle_compression_callback(SimpleNamespace(callback_query=limit_query), self._context())
        self.assertIn("limite", limit_query.edit_message_text.await_args.args[0].lower())

        self.deps.settings.max_active_jobs_per_user = 2
        self._save_pdf_session()
        success_query = self._query("compress:medium", message_id=784)
        await handle_compression_callback(SimpleNamespace(callback_query=success_query), self._context())
        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, SupportedAction.PDF_COMPRESS.value)
        self.assertIsNone(self.store.get(7))
        self.assertEqual(self.store.get_user_preference(7, "compression_preset"), "medium")
        self.assertIn("presa in carico", success_query.edit_message_text.await_args.args[0])

    async def test_split_output_callback_covers_guards_invalid_choice_and_processing_error(self) -> None:
        self.deps.settings.allowed_user_ids = [99]
        unauthorized_query = self._query("split_output:zip", message_id=790)
        await handle_split_output_callback(SimpleNamespace(callback_query=unauthorized_query), self._context())
        unauthorized_query.edit_message_text.assert_awaited_once_with(UNAUTHORIZED_MESSAGE)

        self.deps.settings.allowed_user_ids = []
        self.store.set_meta("service_mode", "maintenance")
        paused_query = self._query("split_output:zip", message_id=791)
        await handle_split_output_callback(SimpleNamespace(callback_query=paused_query), self._context())
        self.assertIn("manutenzione", paused_query.edit_message_text.await_args.args[0].lower())
        self.store.set_meta("service_mode", "normal")

        empty_query = self._query("split_output:zip", message_id=792)
        await handle_split_output_callback(SimpleNamespace(callback_query=empty_query), self._context())
        empty_query.edit_message_text.assert_awaited_once_with(SESSION_EMPTY_MESSAGE)

        self.deps.settings.max_active_jobs_per_user = 0
        self._save_pdf_session(pending_action="pdf_split")
        limit_query = self._query("split_output:zip", message_id=793)
        await handle_split_output_callback(SimpleNamespace(callback_query=limit_query), self._context())
        self.assertIn("limite", limit_query.edit_message_text.await_args.args[0].lower())

        self.deps.settings.max_active_jobs_per_user = 2
        self._save_pdf_session(pending_action="pdf_split")
        invalid_choice_query = self._query("split_output:unknown", message_id=794)
        await handle_split_output_callback(SimpleNamespace(callback_query=invalid_choice_query), self._context())
        invalid_choice_query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

        self._save_pdf_session(pending_action="pdf_split")
        processing_error_query = self._query("split_output:zip", message_id=795)
        with patch("docmolder.bot._enqueue_job", new=AsyncMock(side_effect=ProcessingUserError("PDF non valido"))):
            await handle_split_output_callback(SimpleNamespace(callback_query=processing_error_query), self._context())
        self.assertIn("PDF non valido", processing_error_query.edit_message_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
