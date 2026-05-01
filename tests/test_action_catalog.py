from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.keyboards import build_actions_keyboard, build_session_actions_keyboard
from docmolder.models import FileKind, SupportedAction, UserSession
from docmolder.action_catalog import (
    build_next_step_hint,
    build_output_stem,
    build_session_file,
    build_session_recap,
    get_action_label,
    infer_exposed_actions,
    infer_result_followup_actions,
    infer_recommended_actions,
    infer_session_analysis,
)


class ActionCatalogHelpersTest(unittest.TestCase):
    def test_build_output_stem_uses_source_pdf_name_for_single_file(self) -> None:
        session_file = build_session_file("pdf-1", "Documento Finale.pdf", FileKind.PDF)

        stem = build_output_stem(SupportedAction.PDF_GRAYSCALE, [session_file])

        self.assertEqual(stem, "Documento_Finale_grayscale")

    def test_build_output_stem_mentions_file_count_for_multi_file_jobs(self) -> None:
        files = [
            build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF),
            build_session_file("pdf-2", "Allegato.pdf", FileKind.PDF),
            build_session_file("pdf-3", "Appendice.pdf", FileKind.PDF),
        ]

        stem = build_output_stem(SupportedAction.PDF_MERGE, files)

        self.assertEqual(stem, "Contratto_3_files_merged")

    def test_infer_exposed_actions_matches_single_pdf_capabilities(self) -> None:
        session = UserSession(
            user_id=7,
            files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)],
        )

        actions = infer_exposed_actions(session)

        self.assertEqual(
            actions,
            [
                SupportedAction.PDF_GRAYSCALE,
                SupportedAction.PDF_CROP,
                SupportedAction.PDF_COMPRESS,
                SupportedAction.PDF_SPLIT,
                SupportedAction.PDF_EXTRACT_PAGES,
                SupportedAction.PDF_REORDER_PAGES,
                SupportedAction.PDF_DELETE_PAGES,
                SupportedAction.PDF_ROTATE,
                SupportedAction.PDF_WATERMARK,
            ],
        )

    def test_build_actions_keyboard_uses_central_action_labels(self) -> None:
        keyboard = build_actions_keyboard([SupportedAction.PDF_GRAYSCALE, SupportedAction.PDF_WATERMARK])

        self.assertIsNotNone(keyboard)
        labels = [row[0].text for row in keyboard.inline_keyboard]
        self.assertEqual(labels, [get_action_label(SupportedAction.PDF_GRAYSCALE), "Aggiungi watermark"])

    def test_session_actions_keyboard_groups_recommended_and_advanced_actions(self) -> None:
        session = UserSession(
            user_id=7,
            files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)],
        )

        compact_keyboard = build_session_actions_keyboard(session)
        expanded_keyboard = build_session_actions_keyboard(session, expanded=True)

        self.assertIsNotNone(compact_keyboard)
        self.assertIsNotNone(expanded_keyboard)
        compact_labels = [button.text for row in compact_keyboard.inline_keyboard for button in row]
        expanded_labels = [button.text for row in expanded_keyboard.inline_keyboard for button in row]
        self.assertIn("Altre azioni (6)", compact_labels)
        self.assertIn("Meno azioni", expanded_labels)
        self.assertIn("Aggiungi watermark", expanded_labels)
        self.assertNotIn("Aggiungi watermark", compact_labels)

    def test_build_session_recap_highlights_recommended_action_for_multi_pdf_session(self) -> None:
        session = UserSession(
            user_id=9,
            files=[
                build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF),
                build_session_file("pdf-2", "Allegato.pdf", FileKind.PDF),
            ],
        )

        recap = build_session_recap(session)

        self.assertIn("- File: 2 PDF", recap)
        self.assertIn("Azioni consigliate: Unisci PDF", recap)
        self.assertIn("Contratto.pdf, Allegato.pdf", recap)

    def test_session_analysis_distinguishes_recommended_and_advanced_actions(self) -> None:
        session = UserSession(
            user_id=9,
            files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)],
        )

        analysis = infer_session_analysis(session)

        self.assertEqual(analysis.inventory.pdf_count, 1)
        self.assertIn(SupportedAction.PDF_COMPRESS, analysis.recommended_actions)
        self.assertIn(SupportedAction.PDF_WATERMARK, analysis.advanced_actions)
        self.assertEqual(analysis.warnings, ())

    def test_session_analysis_warns_for_pending_detail(self) -> None:
        session = UserSession(
            user_id=9,
            files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)],
            pending_action=SupportedAction.PDF_EXTRACT_PAGES.value,
        )

        analysis = infer_session_analysis(session)

        self.assertTrue(any("aspettando un dettaglio" in warning for warning in analysis.warnings))

    def test_infer_recommended_actions_prefers_merge_for_multi_pdf_session(self) -> None:
        session = UserSession(
            user_id=10,
            files=[
                build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF),
                build_session_file("pdf-2", "Allegato.pdf", FileKind.PDF),
            ],
        )

        recommended = infer_recommended_actions(session)

        self.assertEqual(recommended, [SupportedAction.PDF_MERGE])

    def test_build_next_step_hint_mentions_pending_action(self) -> None:
        session = UserSession(
            user_id=11,
            files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)],
            pending_action=SupportedAction.PDF_WATERMARK.value,
        )

        hint = build_next_step_hint(session)

        self.assertIn("watermark", hint.lower())

    def test_infer_result_followup_actions_skips_source_action(self) -> None:
        actions = infer_result_followup_actions(SupportedAction.PDF_GRAYSCALE)

        self.assertNotIn(SupportedAction.PDF_GRAYSCALE, actions)
        self.assertIn(SupportedAction.PDF_COMPRESS, actions)


if __name__ == "__main__":
    unittest.main()
