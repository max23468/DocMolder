from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import SupportedAction
from tests.test_processing_support import ProcessingTestCase


class DocumentProcessorCoordinatorTest(ProcessingTestCase):
    def test_process_rejects_unknown_action_and_missing_required_options(self) -> None:
        pdf_path = self.runtime_dir / "source_missing_options.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaisesRegex(ValueError, "Azione non supportata"):
            self.processor.process("unknown", [pdf_path], "unknown")  # type: ignore[arg-type]
        for action, expected_message in [
            (SupportedAction.PDF_EXTRACT_PAGES, "Selezione pagine"),
            (SupportedAction.PDF_REORDER_PAGES, "Selezione pagine"),
            (SupportedAction.PDF_DELETE_PAGES, "Selezione pagine"),
            (SupportedAction.PDF_COMPRESS, "compressione"),
            (SupportedAction.PDF_ROTATE, "Rotazione"),
            (SupportedAction.PDF_WATERMARK, "watermark"),
        ]:
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, expected_message):
                    self.processor.process(action, [pdf_path], "missing_options")

    def test_process_dispatches_merge_split_page_actions_and_auto_orient(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_dispatch" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first_pdf = input_dir / "first.pdf"
        second_pdf = input_dir / "second.pdf"
        for path in [first_pdf, second_pdf]:
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=300)
            writer.add_blank_page(width=220, height=300)
            with path.open("wb") as handle:
                writer.write(handle)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (80, 60), "white").save(image_path)

        merge = self.processor.process(
            SupportedAction.PDF_MERGE, [first_pdf, second_pdf], "merged_dispatch", auto_rotate_pdf=False
        )
        split = self.processor.process(SupportedAction.PDF_SPLIT, [first_pdf], "split_dispatch", split_output_zip=False)
        extract = self.processor.process(
            SupportedAction.PDF_EXTRACT_PAGES, [first_pdf], "extract_dispatch", page_selection="1"
        )
        reorder = self.processor.process(
            SupportedAction.PDF_REORDER_PAGES, [first_pdf], "reorder_dispatch", page_selection="2 1"
        )
        delete = self.processor.process(
            SupportedAction.PDF_DELETE_PAGES, [first_pdf], "delete_dispatch", page_selection="2"
        )
        rotate = self.processor.process(SupportedAction.PDF_ROTATE, [first_pdf], "rotate_dispatch", rotate_degrees=90)
        watermark = self.processor.process(
            SupportedAction.PDF_WATERMARK, [first_pdf], "watermark_dispatch", watermark_text="BOZZA"
        )
        oriented = self.processor.process(SupportedAction.AUTO_ORIENT, [image_path], "oriented_dispatch")

        for result in [merge, split, extract, reorder, delete, rotate, watermark, oriented]:
            self.assertTrue(result.output_path.exists())

    def test_document_photo_fix_creates_pdf_with_perspective_correction(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        image = Image.new("RGB", (600, 800), (70, 75, 82))
        draw = ImageDraw.Draw(image)
        page_points = [(150, 90), (475, 135), (520, 700), (85, 645)]
        draw.polygon(page_points, fill=(245, 245, 238), outline=(230, 230, 220))
        for y in range(190, 560, 70):
            draw.line((150, y, 455, y + 25), fill=(45, 45, 45), width=5)
        image.save(image_path)

        result = self.processor.process(SupportedAction.DOCUMENT_PHOTO_FIX, [image_path], "document_photo")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "document_photo.pdf")
        self.assertEqual(result.processing_mode, "opencv")
        self.assertIn("Correzione prospettica", result.message)
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 1)
