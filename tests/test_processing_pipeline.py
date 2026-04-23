from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
import subprocess
import zipfile

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

    def test_run_ghostscript_grayscale_returns_false_on_timeout(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        with (
            patch("docmolder.processing.shutil.which", return_value="gs"),
            patch("docmolder.processing.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["gs"], timeout=5)),
        ):
            result = self.processor._run_ghostscript_grayscale(pdf_path, output_path)

        self.assertFalse(result)

    def test_run_ghostscript_compress_returns_false_on_timeout(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        with (
            patch("docmolder.processing.shutil.which", return_value="gs"),
            patch("docmolder.processing.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["gs"], timeout=5)),
        ):
            result = self.processor._run_ghostscript_compress(pdf_path, output_path, quality_profile="/ebook")

        self.assertFalse(result)

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

    def test_grayscale_rejects_empty_pdf(self) -> None:
        empty_pdf = self.runtime_dir / "empty.pdf"
        empty_pdf.write_bytes(b"")

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf_to_grayscale(empty_pdf, "grayscale_empty")

    def test_compress_rejects_password_protected_pdf(self) -> None:
        protected_pdf = self.runtime_dir / "protected.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("secret")
        with protected_pdf.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.compress_pdf(protected_pdf, "compressed", CompressionPreset.MEDIUM)

    def test_extract_pdf_pages_creates_subset(self) -> None:
        pdf_path = self.runtime_dir / "source_extract.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=220, height=300)
        writer.add_blank_page(width=240, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.extract_pdf_pages(pdf_path, "extracted", page_selection="1,3")

        self.assertTrue(result.output_path.exists())
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("1, 3", result.message)

    def test_split_pdf_pages_creates_zip_with_one_pdf_per_page(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_split" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = input_dir / "source_split.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=220, height=300)
        writer.add_blank_page(width=240, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.split_pdf_pages(pdf_path, "split_pages")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "split_pages.zip")
        self.assertIn("3 file", result.message)
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
            self.assertEqual(
                names,
                [
                    "split_pages_pagina_01.pdf",
                    "split_pages_pagina_02.pdf",
                    "split_pages_pagina_03.pdf",
                ],
            )
            for name in names:
                with archive.open(name) as pdf_handle:
                    reader = PdfReader(BytesIO(pdf_handle.read()))
                    self.assertEqual(len(reader.pages), 1)

    def test_split_pdf_pages_rejects_single_page_pdf(self) -> None:
        pdf_path = self.runtime_dir / "single_page.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.split_pdf_pages(pdf_path, "single_split")

    def test_split_pdf_pages_can_return_separate_outputs(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_split_files" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = input_dir / "source_split_files.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=220, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.split_pdf_pages(pdf_path, "split_files", output_as_zip=False)

        self.assertEqual(result.output_name, "split_files_pagina_01.pdf")
        self.assertEqual([output.name for output in result.additional_outputs], ["split_files_pagina_02.pdf"])
        self.assertTrue(result.output_path.exists())
        self.assertTrue(result.additional_outputs[0].path.exists())
        self.assertIn("PDF separati", result.message)

    def test_reorder_pdf_pages_requires_full_unique_order(self) -> None:
        pdf_path = self.runtime_dir / "source_reorder.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.reorder_pdf_pages(pdf_path, "reordered", page_selection="3,1")

    def test_reorder_pdf_pages_accepts_space_separated_order(self) -> None:
        pdf_path = self.runtime_dir / "source_reorder_spaces.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.reorder_pdf_pages(pdf_path, "reordered_spaces", page_selection="3 1 2")

        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 3)

    def test_delete_pdf_pages_keeps_remaining_pages(self) -> None:
        pdf_path = self.runtime_dir / "source_delete.pdf"
        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.delete_pdf_pages(pdf_path, "deleted", page_selection="2-3")

        self.assertTrue(result.output_path.exists())
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("2, 3", result.message)

    def test_rotate_pdf_rejects_invalid_degrees(self) -> None:
        pdf_path = self.runtime_dir / "source_rotate.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.rotate_pdf(pdf_path, "rotated_invalid", 45)

    def test_add_text_watermark_creates_output(self) -> None:
        pdf_path = self.runtime_dir / "source_watermark.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.add_text_watermark(pdf_path, "watermarked", watermark_text="BOZZA")

        self.assertTrue(result.output_path.exists())
        self.assertIn("BOZZA", result.message)

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

    def test_images_to_pdf_can_create_grayscale_output_directly(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_4" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        result = self.processor.images_to_pdf([image_path], "gray_direct", grayscale_output=True)

        self.assertTrue(result.output_path.exists())
        self.assertIn("scala di grigi", result.message)

    def test_process_images_to_pdf_grayscale_does_not_roundtrip_through_pdf_grayscale(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_5" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        with patch.object(self.processor, "pdf_to_grayscale", side_effect=AssertionError("unexpected roundtrip")):
            result = self.processor.process(SupportedAction.IMAGES_TO_PDF_GRAYSCALE, [image_path], "gray_process")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "gray_process.pdf")
        self.assertIn("scala di grigi", result.message)

    def test_merge_rejects_corrupt_pdf_among_inputs(self) -> None:
        valid_pdf = self.runtime_dir / "valid.pdf"
        corrupt_pdf = self.runtime_dir / "corrupt.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=400)
        with valid_pdf.open("wb") as handle:
            writer.write(handle)
        corrupt_pdf.write_text("not a pdf", encoding="utf-8")

        with self.assertRaises(ProcessingUserError):
            self.processor.merge_pdfs([valid_pdf, corrupt_pdf], "merged_corrupt")

    def test_compress_light_handles_multipage_pdf(self) -> None:
        multipage_pdf = self.runtime_dir / "multipage.pdf"
        writer = PdfWriter()
        for _ in range(24):
            writer.add_blank_page(width=595, height=842)
        with multipage_pdf.open("wb") as handle:
            writer.write(handle)

        result = self.processor.compress_pdf(multipage_pdf, "multipage_light", CompressionPreset.LIGHT)

        self.assertTrue(result.output_path.exists())
        self.assertIn("livello light", result.message)
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 24)

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

    def test_auto_rotate_pdf_to_dominant_orientation_ignores_square_pages(self) -> None:
        pdf_path = self.runtime_dir / "portrait_with_square.pdf"
        output_path = self.runtime_dir / "portrait_with_square_rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=300, height=300)
        writer.add_blank_page(width=400, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        rotated_pages = self.processor._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

        self.assertEqual(rotated_pages, 1)
        reader = PdfReader(str(output_path))
        self.assertEqual(int(reader.pages[0].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[1].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[2].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[3].rotation or 0) % 360, 90)

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
