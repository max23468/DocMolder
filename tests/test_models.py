from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import CompressionPreset, FileKind, JobPayload, UserSession
from docmolder.action_catalog import build_session_file


class JobPayloadModelTest(unittest.TestCase):
    def test_job_payload_roundtrip_preserves_optional_fields(self) -> None:
        session = UserSession(
            user_id=7,
            files=[
                build_session_file("pdf-1", "Documento.pdf", FileKind.PDF),
            ],
        )

        payload = JobPayload.from_session(
            session,
            compression_preset=CompressionPreset.MEDIUM,
            rotate_degrees=180,
            page_selection="1,3-4",
            watermark_text="BOZZA",
            auto_rotate_pdf=False,
            image_pdf_use_a4=False,
            image_pdf_margin_px=0,
            split_output_zip=False,
        )

        loaded = JobPayload.from_json(payload.to_json())

        self.assertEqual(len(loaded.files), 1)
        self.assertEqual(loaded.files[0].telegram_file_id, "pdf-1")
        self.assertEqual(loaded.files[0].file_name, "Documento.pdf")
        self.assertEqual(loaded.files[0].kind, FileKind.PDF)
        self.assertEqual(loaded.compression_preset, CompressionPreset.MEDIUM)
        self.assertEqual(loaded.rotate_degrees, 180)
        self.assertEqual(loaded.page_selection, "1,3-4")
        self.assertEqual(loaded.watermark_text, "BOZZA")
        self.assertFalse(loaded.auto_rotate_pdf)
        self.assertFalse(loaded.image_pdf_use_a4)
        self.assertEqual(loaded.image_pdf_margin_px, 0)
        self.assertFalse(loaded.split_output_zip)


if __name__ == "__main__":
    unittest.main()
