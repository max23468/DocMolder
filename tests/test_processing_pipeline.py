from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import CompressionPreset, SupportedAction
from docmolder.processing import A4_MARGIN_WIDE_PX, DocumentProcessor, ProcessingUserError


class DocumentProcessorPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.processor = DocumentProcessor(self.runtime_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_ghostscript_grayscale_command(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        command = self.processor._build_ghostscript_grayscale_command("gs", pdf_path, output_path)

        self.assertIn("-sColorConversionStrategy=Gray", command)
        self.assertIn("-dProcessColorModel=/DeviceGray", command)
        self.assertIn(f"-sOutputFile={output_path}", command)
        self.assertEqual(command[-1], str(pdf_path))

    def test_build_ghostscript_compress_command(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        command = self.processor._build_ghostscript_compress_command(
            ghostscript="gs",
            pdf_path=pdf_path,
            output_path=output_path,
            quality_profile="/ebook",
        )

        self.assertIn("-dPDFSETTINGS=/ebook", command)
        self.assertIn(f"-sOutputFile={output_path}", command)
        self.assertEqual(command[-1], str(pdf_path))

    def test_merge_requires_at_least_two_pdfs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.merge_pdfs([], "merged")

    def test_images_to_pdf_requires_inputs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.images_to_pdf([], "images")

    def test_auto_orient_requires_inputs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.auto_orient_images([], "oriented")

    def test_grayscale_rejects_invalid_pdf(self) -> None:
        invalid_pdf = self.runtime_dir / "invalid.pdf"
        invalid_pdf.write_text("not a real pdf", encoding="utf-8")

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf_to_grayscale(invalid_pdf, "grayscale")

    def test_compress_rejects_password_protected_pdf(self) -> None:
        protected_pdf = self.runtime_dir / "protected.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("secret")
        with protected_pdf.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.compress_pdf(protected_pdf, "compressed", CompressionPreset.MEDIUM)

    def test_auto_crop_scan_borders_removes_uniform_border(self) -> None:
        image = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 40, 340, 260), fill="black")

        cropped = self.processor._auto_crop_scan_borders(image)

        self.assertLess(cropped.width, image.width)
        self.assertLess(cropped.height, image.height)
        self.assertGreaterEqual(cropped.width, 260)
        self.assertGreaterEqual(cropped.height, 200)

    def test_process_images_to_pdf_crop_creates_pdf(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_1" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "scan.jpg"
        image = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((70, 50, 330, 250), fill="black")
        image.save(image_path)

        result = self.processor.process(SupportedAction.IMAGES_TO_PDF_CROP, [image_path], "cropped")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "cropped.pdf")

    def test_images_to_pdf_can_keep_original_image_format(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_2" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        result = self.processor.images_to_pdf([image_path], "original_layout", use_a4_layout=False)

        self.assertTrue(result.output_path.exists())
        self.assertIn("formato originale", result.message)

    def test_images_to_pdf_mentions_selected_a4_margin(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_3" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        result = self.processor.images_to_pdf(
            [image_path],
            "a4_wide",
            use_a4_layout=True,
            a4_margin_px=A4_MARGIN_WIDE_PX,
        )

        self.assertTrue(result.output_path.exists())
        self.assertIn("bordi larghi", result.message)

    def test_auto_rotate_pdf_to_dominant_orientation_rotates_outlier_pages(self) -> None:
        pdf_path = self.runtime_dir / "mostly_portrait.pdf"
        output_path = self.runtime_dir / "mostly_portrait_rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=400, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        rotated_pages = self.processor._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

        self.assertEqual(rotated_pages, 1)
        reader = PdfReader(str(output_path))
        self.assertEqual(int(reader.pages[0].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[1].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[2].rotation or 0) % 360, 90)

    def test_auto_rotate_pdf_to_dominant_orientation_keeps_single_landscape_document(self) -> None:
        pdf_path = self.runtime_dir / "single_landscape.pdf"
        output_path = self.runtime_dir / "single_landscape_rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=400, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        rotated_pages = self.processor._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

        self.assertEqual(rotated_pages, 0)
        self.assertFalse(output_path.exists())

    def test_auto_rotate_pdf_to_dominant_orientation_matches_landscape_majority(self) -> None:
        pdf_path = self.runtime_dir / "mostly_landscape.pdf"
        output_path = self.runtime_dir / "mostly_landscape_rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=400, height=200)
        writer.add_blank_page(width=400, height=200)
        writer.add_blank_page(width=200, height=400)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        rotated_pages = self.processor._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

        self.assertEqual(rotated_pages, 1)
        reader = PdfReader(str(output_path))
        self.assertEqual(int(reader.pages[0].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[1].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[2].rotation or 0) % 360, 90)


if __name__ == "__main__":
    unittest.main()
