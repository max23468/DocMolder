from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.keyboards import build_actions_keyboard
from docmolder.models import FileKind, SupportedAction, UserSession
from docmolder.services import build_output_stem, build_session_file, get_action_label, infer_exposed_actions


class ServiceHelpersTest(unittest.TestCase):
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
                SupportedAction.PDF_COMPRESS,
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


if __name__ == "__main__":
    unittest.main()
