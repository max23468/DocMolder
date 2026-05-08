from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.action_catalog import build_session_file
from docmolder.models import DocumentPhotoMode, FileKind, SupportedAction, UserSession
from docmolder.processing import A4_MARGIN_NARROW_PX, A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX, ProcessingUserError
from docmolder.text_requests import (
    _build_quick_action_guidance,
    _normalize_page_selection_text,
    _parse_document_photo_mode_choice,
    _parse_image_pdf_layout_choice,
    _parse_image_pdf_margin_choice,
    _resolve_text_request,
    _validate_page_input_text,
)


class TextRequestParsingTest(unittest.TestCase):
    def test_layout_margin_and_document_photo_choices_accept_natural_text(self) -> None:
        self.assertTrue(_parse_image_pdf_layout_choice("si, impagina in A4"))
        self.assertFalse(_parse_image_pdf_layout_choice("no A4, mantieni formato originale"))
        self.assertIsNone(_parse_image_pdf_layout_choice("decidi tu"))
        self.assertEqual(_parse_image_pdf_margin_choice("senza bordi"), A4_MARGIN_NONE_PX)
        self.assertEqual(_parse_image_pdf_margin_choice("bordi larghi"), A4_MARGIN_WIDE_PX)
        self.assertEqual(_parse_image_pdf_margin_choice("bordi stretti"), A4_MARGIN_NARROW_PX)
        self.assertEqual(_parse_document_photo_mode_choice("mantieni colore"), DocumentPhotoMode.COLOR)
        self.assertEqual(_parse_document_photo_mode_choice("bianco e nero pulito"), DocumentPhotoMode.BW)
        self.assertEqual(_parse_document_photo_mode_choice("bianco/nero pulito"), DocumentPhotoMode.BW)
        self.assertEqual(_parse_document_photo_mode_choice("piu leggibile"), DocumentPhotoMode.READABLE)

    def test_page_selection_normalization_and_validation(self) -> None:
        self.assertEqual(_normalize_page_selection_text("1 3, 5-7"), "1,3,5-7")
        _validate_page_input_text("1,3,5-7")
        with self.assertRaisesRegex(ProcessingUserError, "nessuna selezione"):
            _validate_page_input_text(" ")
        with self.assertRaisesRegex(ProcessingUserError, "numeri"):
            _validate_page_input_text("1; due")

    def test_pdf_text_requests_cover_enqueue_pending_and_clarify_paths(self) -> None:
        session = UserSession(user_id=7, files=[build_session_file("pdf-1", "contratto.pdf", FileKind.PDF)])

        rotate = _resolve_text_request(session, "giralo a sinistra")
        self.assertEqual(rotate.action, SupportedAction.PDF_ROTATE)
        self.assertEqual(rotate.rotate_degrees, 270)

        watermark = _resolve_text_request(session, 'aggiungi watermark "BOZZA"')
        self.assertEqual(watermark.action, SupportedAction.PDF_WATERMARK)
        self.assertEqual(watermark.watermark_text, "BOZZA")

        split_zip = _resolve_text_request(session, "dividi il pdf in zip")
        self.assertEqual(split_zip.action, SupportedAction.PDF_SPLIT)
        self.assertTrue(split_zip.split_output_zip)

        split_pending = _resolve_text_request(session, "dividi il pdf")
        self.assertEqual(split_pending.kind, "pending")
        self.assertEqual(split_pending.action, SupportedAction.PDF_SPLIT)

        page_clarify = _resolve_text_request(session, "pagine 2 4-5")
        self.assertEqual(page_clarify.kind, "clarify")
        self.assertIn("2,4-5", page_clarify.message)

        multi_action = _resolve_text_request(session, "comprimi e converti in bianco e nero")
        self.assertEqual(multi_action.kind, "clarify")
        self.assertIn("una cosa per volta", multi_action.message)

    def test_image_text_requests_cover_supported_transformations(self) -> None:
        session = UserSession(user_id=7, files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)])

        document_photo = _resolve_text_request(session, "raddrizza foto documento a colori")
        self.assertEqual(document_photo.action, SupportedAction.DOCUMENT_PHOTO_FIX)
        self.assertEqual(document_photo.document_photo_mode, DocumentPhotoMode.COLOR)

        crop_grayscale = _resolve_text_request(session, "scannerizza e converti in bianco e nero")
        self.assertEqual(crop_grayscale.action, SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE)

        crop_pdf = _resolve_text_request(session, "ritaglia i bordi e crea pdf")
        self.assertEqual(crop_pdf.action, SupportedAction.IMAGES_TO_PDF_CROP)

        grayscale_pdf = _resolve_text_request(session, "fammi un pdf in scala di grigi")
        self.assertEqual(grayscale_pdf.action, SupportedAction.IMAGES_TO_PDF_GRAYSCALE)

        plain_pdf = _resolve_text_request(session, "mettile in pdf")
        self.assertEqual(plain_pdf.action, SupportedAction.IMAGES_TO_PDF)

    def test_excel_text_request_resolves_unlock_action(self) -> None:
        session = UserSession(user_id=7, files=[build_session_file("excel-1", "budget.xlsx", FileKind.EXCEL)])

        unlocked = _resolve_text_request(session, "togli protezione dai fogli excel")

        self.assertEqual(unlocked.kind, "enqueue")
        self.assertEqual(unlocked.action, SupportedAction.EXCEL_UNLOCK_EDITING)

    def test_quick_action_guidance_handles_empty_and_mismatched_sessions(self) -> None:
        empty_session = UserSession(user_id=7)
        image_session = UserSession(user_id=7, files=[build_session_file("img-1", "foto.jpg", FileKind.IMAGE)])
        pdf_session = UserSession(user_id=7, files=[build_session_file("pdf-1", "doc.pdf", FileKind.PDF)])
        multi_pdf_session = UserSession(
            user_id=7,
            files=[
                build_session_file("pdf-1", "doc-1.pdf", FileKind.PDF),
                build_session_file("pdf-2", "doc-2.pdf", FileKind.PDF),
            ],
        )

        self.assertIn("Inviami una o più immagini", _build_quick_action_guidance(None, "Crea PDF"))
        self.assertIn("foto o scansioni", _build_quick_action_guidance(pdf_session, "Crea PDF"))
        self.assertIn("Inviami un PDF", _build_quick_action_guidance(empty_session, "Comprimi PDF"))
        self.assertIn("prima trasformare", _build_quick_action_guidance(image_session, "Comprimi PDF"))
        self.assertIn("un solo PDF", _build_quick_action_guidance(multi_pdf_session, "Comprimi PDF"))
        self.assertIn("due o più PDF", _build_quick_action_guidance(None, "Unisci PDF"))
        self.assertIn("servono PDF", _build_quick_action_guidance(image_session, "Unisci PDF"))
        self.assertIn("almeno due", _build_quick_action_guidance(pdf_session, "Unisci PDF"))
        self.assertIn("PDF impaginato in A4", _build_quick_action_guidance(None, "foto in a4"))
        self.assertIn("impaginazione A4", _build_quick_action_guidance(image_session, "foto in a4"))
        self.assertIn("non da PDF", _build_quick_action_guidance(pdf_session, "foto in a4"))
        self.assertIn("Inviami una o più foto", _build_quick_action_guidance(None, "scansiona e comprimi"))
        self.assertIn("senza ricaricarlo", _build_quick_action_guidance(image_session, "scansiona e comprimi"))
        self.assertIn("comprimere direttamente", _build_quick_action_guidance(pdf_session, "scansiona e comprimi"))
        self.assertIsNone(_build_quick_action_guidance(pdf_session, "testo libero"))


if __name__ == "__main__":
    unittest.main()
