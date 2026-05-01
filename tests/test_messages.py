from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.keyboards import (
    build_admin_dashboard_keyboard,
    build_compression_keyboard,
    build_delete_data_confirmation_keyboard,
    build_delete_data_request_keyboard,
    build_document_photo_mode_keyboard,
    build_history_keyboard,
    build_images_pdf_layout_keyboard,
    build_images_pdf_margin_keyboard,
    build_main_menu_keyboard,
    build_result_pdf_keyboard,
    build_rotate_keyboard,
    build_split_output_keyboard,
)
from docmolder.models import JobStatus, SupportedAction
from docmolder.messages import (
    HELP_MESSAGE,
    PUBLIC_PRIVACY_URL,
    WELCOME_MESSAGE,
    build_pending_action_prompt,
    build_pending_action_queued_message,
    build_processing_started_message,
    build_text_request_queued_message,
)
from docmolder.processing import A4_MARGIN_NARROW_PX


class MessageGoldenTest(unittest.TestCase):
    def test_help_message_lists_reduced_command_surface(self) -> None:
        self.assertIn("/start", HELP_MESSAGE)
        self.assertIn("/help", HELP_MESSAGE)
        self.assertIn("/history", HELP_MESSAGE)
        self.assertIn("/status", HELP_MESSAGE)
        self.assertIn("/reset", HELP_MESSAGE)
        self.assertNotIn("/request_access", HELP_MESSAGE)
        self.assertNotIn("/policy", HELP_MESSAGE)
        self.assertNotIn("/last", HELP_MESSAGE)
        self.assertNotIn("/access", HELP_MESSAGE)
        self.assertNotIn("/admin", HELP_MESSAGE)
        self.assertIn(PUBLIC_PRIVACY_URL, HELP_MESSAGE)
        self.assertIn("non li archivio permanentemente", WELCOME_MESSAGE)
        self.assertIn("best-effort", HELP_MESSAGE)

    def test_static_privacy_page_matches_public_command_surface(self) -> None:
        privacy_page = (Path(__file__).resolve().parents[1] / "deploy/static/docmolder-site/privacy.html").read_text(encoding="utf-8")

        self.assertIn("/start", privacy_page)
        self.assertIn("/help", privacy_page)
        self.assertIn("/history", privacy_page)
        self.assertIn("/status", privacy_page)
        self.assertIn("/reset", privacy_page)
        self.assertIn("30 giorni", privacy_page)
        self.assertIn("cancellare anche tutti i dati live", privacy_page)
        self.assertNotIn("`/policy`", privacy_page)
        self.assertNotIn("`/privacy`", privacy_page)
        self.assertNotIn("`/last`", privacy_page)

    def test_admin_keyboard_keeps_maintenance_shortcut(self) -> None:
        keyboard = build_admin_dashboard_keyboard(service_paused=False)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Manutenzione", labels)
        self.assertIn("admin:maintenance", callbacks)

    def test_admin_keyboard_hides_unavailable_job_status_shortcuts(self) -> None:
        keyboard = build_admin_dashboard_keyboard(
            service_paused=False,
            available_job_statuses={JobStatus.FAILED},
        )

        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Ultimo fallito", labels)
        self.assertIn("Ultimo job", labels)
        self.assertNotIn("In esecuzione", labels)
        self.assertNotIn("Ultimo queued", labels)
        self.assertNotIn("Ultimo riuscito", labels)

    def test_admin_keyboard_hides_job_shortcuts_when_no_jobs_exist(self) -> None:
        keyboard = build_admin_dashboard_keyboard(
            service_paused=False,
            available_job_statuses=set(),
        )

        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertNotIn("Ultimo job", labels)
        self.assertNotIn("Ultimo fallito", labels)

    def test_keyboards_expose_guided_choices_and_presets(self) -> None:
        compression = build_compression_keyboard(preset="medium")
        split = build_split_output_keyboard(preset="zip")
        layout = build_images_pdf_layout_keyboard("images_to_pdf", preset_layout="a4", preset_margin_px=str(A4_MARGIN_NARROW_PX))
        original_layout = build_images_pdf_layout_keyboard("images_to_pdf", preset_layout="original")
        margin = build_images_pdf_margin_keyboard("images_to_pdf")
        document_photo = build_document_photo_mode_keyboard()
        rotate = build_rotate_keyboard()
        history = build_history_keyboard([3])
        result = build_result_pdf_keyboard(
            quick_actions=[SupportedAction.PDF_COMPRESS],
            undo_rotation_job_id=9,
        )
        delete_request = build_delete_data_request_keyboard()
        delete_confirmation = build_delete_data_confirmation_keyboard()
        main_menu = build_main_menu_keyboard()

        labels = [button.text for keyboard in [compression, split, layout, original_layout, margin, document_photo, rotate, history, result, delete_request, delete_confirmation] for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Usa preset: media", labels)
        self.assertIn("Usa preset: ZIP unico", labels)
        self.assertIn("Usa preset: A4 bordi stretti", labels)
        self.assertIn("Usa preset: formato originale", labels)
        self.assertIn("Nessun bordo", labels)
        self.assertIn("Bianco/nero pulito", labels)
        self.assertIn("270°", labels)
        self.assertIn("Rifai #3", labels)
        self.assertIn("Rifai senza rotazione automatica", labels)
        self.assertIn("Cancella tutti i miei dati", labels)
        self.assertIn("Conferma cancellazione", labels)
        self.assertTrue(main_menu.resize_keyboard)

    def test_message_builders_cover_pending_and_processing_variants(self) -> None:
        self.assertIn("ZIP", build_pending_action_prompt(SupportedAction.PDF_SPLIT))
        self.assertIn("90", build_pending_action_prompt(SupportedAction.PDF_ROTATE))
        self.assertIn("pagine", build_pending_action_prompt(SupportedAction.PDF_EXTRACT_PAGES))
        self.assertIn("watermark", build_pending_action_prompt(SupportedAction.PDF_WATERMARK))
        self.assertIn("dettagli", build_pending_action_prompt(SupportedAction.PDF_COMPRESS))
        self.assertIn("ZIP unico", build_pending_action_queued_message(SupportedAction.PDF_SPLIT, 1, "zip"))
        self.assertIn("PDF separati", build_pending_action_queued_message(SupportedAction.PDF_SPLIT, 1, "files"))
        self.assertIn("2-4", build_pending_action_queued_message(SupportedAction.PDF_DELETE_PAGES, 2, "2-4"))
        self.assertIn('"BOZZA"', build_pending_action_queued_message(SupportedAction.PDF_WATERMARK, 3, " BOZZA "))
        self.assertIn("ripiego", build_processing_started_message(SupportedAction.PDF_GRAYSCALE, 4))
        self.assertIn("compressione", build_processing_started_message(SupportedAction.PDF_COMPRESS, 5))
        self.assertIn("Job #6", build_processing_started_message(SupportedAction.PDF_MERGE, 6))

    def test_text_request_queued_messages_cover_high_value_actions(self) -> None:
        cases = [
            SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
            SupportedAction.IMAGES_TO_PDF_CROP,
            SupportedAction.DOCUMENT_PHOTO_FIX,
            SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
            SupportedAction.IMAGES_TO_PDF,
            SupportedAction.PDF_GRAYSCALE,
            SupportedAction.PDF_CROP,
            SupportedAction.PDF_MERGE,
            SupportedAction.PDF_SPLIT,
            SupportedAction.PDF_EXTRACT_PAGES,
            SupportedAction.PDF_REORDER_PAGES,
            SupportedAction.PDF_DELETE_PAGES,
            SupportedAction.PDF_COMPRESS,
            SupportedAction.AUTO_ORIENT,
            SupportedAction.PDF_ROTATE,
            SupportedAction.PDF_WATERMARK,
        ]

        for index, action in enumerate(cases, start=1):
            with self.subTest(action=action):
                message = build_text_request_queued_message(action, index, None)
                self.assertIn(f"Job #{index}", message)
