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
    handle_menu_text,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import CompressionPreset, DocumentPhotoMode, FileKind, SupportedAction, UserSession
from docmolder.session_store import InMemorySessionStore
from docmolder.action_catalog import build_session_file


class BotTextFlowsTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_text_request_for_pdf_crop_enqueues_crop_job(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="taglia i bordi di questo pdf",
            chat_id=99,
            message_id=1202,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=89))) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_job.assert_awaited_once()
        self.assertEqual(enqueue_job.await_args.kwargs["action"], SupportedAction.PDF_CROP)
        message.reply_text.assert_awaited_once()
        self.assertIn("Taglio bordi PDF", message.reply_text.await_args.args[0])

    async def test_text_request_can_rotate_active_pdf_with_pronoun(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Giralo a destra",
            chat_id=99,
            message_id=7022,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, "pdf_rotate")
        self.assertIn('"rotate_degrees": 90', queued_job.payload_json)
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

    async def test_text_request_for_document_photo_fix_prompts_for_scan_profile(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_documento.jpg", FileKind.IMAGE)],
            )
        )
        message = SimpleNamespace(
            text="Raddrizza foto documento",
            chat_id=99,
            message_id=4571,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        self.assertEqual(self.store.get(7).pending_action, "document_photo_mode")
        message.reply_text.assert_awaited_once()
        self.assertIn("Come vuoi sistemare", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_text_request_for_document_photo_fix_can_enqueue_explicit_bw_profile(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("img-1", "foto_documento.jpg", FileKind.IMAGE)],
            )
        )
        message = SimpleNamespace(
            text="Raddrizza foto documento in bianco e nero",
            chat_id=99,
            message_id=4572,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=33))) as enqueue_job:
            await handle_menu_text(update, context)

        enqueue_call = enqueue_job.await_args.kwargs
        self.assertEqual(enqueue_call["action"], SupportedAction.DOCUMENT_PHOTO_FIX)
        self.assertEqual(enqueue_call["document_photo_mode"], DocumentPhotoMode.BW)
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

    async def test_text_request_uses_saved_compression_preset_when_level_is_missing(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        self.store.set_user_preset(7, "compression_preset", "strong")
        message = SimpleNamespace(
            text="Comprimi questo pdf",
            chat_id=99,
            message_id=7890,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=9))) as enqueue_job:
            await handle_menu_text(update, context)

        self.assertEqual(enqueue_job.await_args.kwargs["compression_preset"], CompressionPreset.STRONG)

    async def test_text_request_explicit_compression_level_overrides_saved_preset(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        self.store.set_user_preset(7, "compression_preset", "strong")
        message = SimpleNamespace(
            text="Comprimi questo pdf in modo leggero",
            chat_id=99,
            message_id=78901,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        with patch("docmolder.bot._enqueue_job", new=AsyncMock(return_value=SimpleNamespace(id=9))) as enqueue_job:
            await handle_menu_text(update, context)

        self.assertEqual(enqueue_job.await_args.kwargs["compression_preset"], CompressionPreset.LIGHT)

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

    async def test_text_request_can_compress_active_pdf_with_pronoun(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "risultato.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Alleggeriscilo forte",
            chat_id=99,
            message_id=7893,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, "pdf_compress")
        self.assertIn('"compression_preset": "strong"', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

    async def test_text_request_for_split_pdf_prompts_for_output_choice(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Dividi questo pdf",
            chat_id=99,
            message_id=899,
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(update, context)

        self.assertEqual(len(self.store._jobs), 0)
        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, "pdf_split")
        message.reply_text.assert_awaited_once()
        self.assertIn("ZIP", message.reply_text.await_args.args[0])
        self.assertIsNotNone(message.reply_text.await_args.kwargs["reply_markup"])

    async def test_text_request_can_split_pdf_without_zip(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Dividi questo pdf senza zip",
            chat_id=99,
            message_id=8991,
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
        self.assertIn('"split_output_zip": false', queued_job.payload_json)
        message.reply_text.assert_awaited_once()

    async def test_contextual_split_conversation_prompts_then_enqueues_output_choice(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "risultato.pdf", FileKind.PDF)],
            )
        )
        first_message = SimpleNamespace(
            text="Dividilo",
            chat_id=99,
            message_id=8993,
            reply_text=AsyncMock(),
        )
        first_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=first_message,
        )
        context = SimpleNamespace(application=self.application, bot=self.bot)

        await handle_menu_text(first_update, context)

        saved_session = self.store.get(7)
        self.assertIsNotNone(saved_session)
        self.assertEqual(saved_session.pending_action, "pdf_split")
        self.assertIn("ZIP", first_message.reply_text.await_args.args[0])

        second_message = SimpleNamespace(
            text="pdf separati",
            chat_id=99,
            message_id=8994,
            reply_text=AsyncMock(),
        )
        second_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=7, username=None, first_name="Test", last_name=None),
            effective_message=second_message,
        )

        await handle_menu_text(second_update, context)

        queued_job = next(iter(self.store._jobs.values()))
        self.assertEqual(queued_job.action, "pdf_split")
        self.assertIn('"split_output_zip": false', queued_job.payload_json)
        self.assertIsNone(self.store.get(7))

    async def test_text_request_respects_negated_zip_with_article(self) -> None:
        self.store.save(
            UserSession(
                user_id=7,
                files=[build_session_file("pdf-1", "documento.pdf", FileKind.PDF)],
            )
        )
        message = SimpleNamespace(
            text="Dividi questo pdf senza lo zip",
            chat_id=99,
            message_id=8992,
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
        self.assertIn('"split_output_zip": false', queued_job.payload_json)

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
