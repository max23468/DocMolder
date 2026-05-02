from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import (
    BotDependencies,
    _invalid_callback_message,
    handle_action_callback,
    handle_compression_callback,
    handle_rotate_callback,
    handle_images_pdf_layout_callback,
    handle_images_pdf_margin_callback,
    handle_images_pdf_preset_callback,
    handle_document_photo_mode_callback,
    handle_menu_text,
    handle_split_output_callback,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import FileKind, SupportedAction, UserSession
from docmolder.session_store import InMemorySessionStore
from docmolder.action_catalog import build_session_file


class BotGuidedActionsTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_invalid_action_callback_returns_expired_message(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="action:not-real",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=700),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_action_callback(update, context)

        query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

    async def test_action_more_callback_expands_contextual_keyboard(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="action:more",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=700),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_action_callback(update, context)

        labels = [button.text for row in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for button in row]
        self.assertIn("Meno azioni", labels)
        self.assertIn("Aggiungi watermark", labels)

    async def test_invalid_compression_callback_returns_expired_message(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="compress:ultra",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=701),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_compression_callback(update, context)

        query.edit_message_text.assert_awaited_once_with(_invalid_callback_message())

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

    async def test_action_callback_split_prompts_for_output_choice(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        query = SimpleNamespace(
            data="action:pdf_split",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=700),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_action_callback(update, context)

        self.assertEqual(self.store.get(7).pending_action, "pdf_split")
        self.assertIn("ZIP", query.edit_message_text.await_args.args[0])
        self.assertIsNotNone(query.edit_message_text.await_args.kwargs["reply_markup"])

    async def test_split_output_callback_enqueues_separate_pdf_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_split",
            )
        )
        query = SimpleNamespace(
            data="split_output:files",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=701),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_split_output_callback(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, "pdf_split")
        self.assertIn('"split_output_zip": false', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))
        self.assertEqual(self.store.get_user_preference(7, "split_output"), "files")
        self.assertIn("PDF separati", query.edit_message_text.await_args.args[0])

    async def test_split_output_callback_rejects_incompatible_session(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)],
                pending_action="pdf_split",
            )
        )
        query = SimpleNamespace(
            data="split_output:zip",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=702),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_split_output_callback(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        self.assertIn("non è più compatibile", query.edit_message_text.await_args.args[0])

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

    async def test_pending_split_text_enqueues_zip_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="pdf_split",
            )
        )
        message = SimpleNamespace(
            text="zip",
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
        self.assertEqual(queued_job.action, "pdf_split")
        self.assertIn('"split_output_zip": true', queued_job.payload_json)
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

    async def test_document_photo_mode_callback_enqueues_color_profile(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_documento.jpg", FileKind.IMAGE)],
                pending_action="document_photo_mode",
            )
        )
        query = SimpleNamespace(
            data="document_photo_mode:color",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=4573),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_document_photo_mode_callback(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, SupportedAction.DOCUMENT_PHOTO_FIX.value)
        self.assertIn('"document_photo_mode": "color"', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))
        self.assertIn("Mantieni colore", query.edit_message_text.await_args.args[0])

    async def test_document_photo_mode_callback_rejects_incompatible_session(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
                pending_action="document_photo_mode",
            )
        )
        query = SimpleNamespace(
            data="document_photo_mode:color",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=4573),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_document_photo_mode_callback(update, context)

        self.assertEqual(self.store._jobs, {})
        self.assertIn("non è più compatibile", query.edit_message_text.await_args.args[0])

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

    async def test_images_pdf_preset_callback_enqueues_job_with_saved_a4_margin(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_1.jpg", FileKind.IMAGE)],
            )
        )
        query = SimpleNamespace(
            data="images_pdf_preset:a4:narrow:images_to_pdf",
            from_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            message=SimpleNamespace(chat_id=99, message_id=461),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_images_pdf_preset_callback(update, context)

        queued_jobs = list(self.store._jobs.values())
        self.assertEqual(len(queued_jobs), 1)
        self.assertIn('"image_pdf_use_a4": true', queued_jobs[0].payload_json)
        self.assertIn('"image_pdf_margin_px": 48', queued_jobs[0].payload_json)
        query.edit_message_text.assert_awaited_once()
        self.assertIsNone(self.store.get(7))

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


if __name__ == "__main__":
    unittest.main()
