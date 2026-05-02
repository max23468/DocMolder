from __future__ import annotations

from io import BytesIO
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
import subprocess
import zipfile

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import CompressionPreset, DocumentPhotoMode, SupportedAction
from docmolder.processing import A4_MARGIN_WIDE_PX, DocumentProcessor, ProcessingUserError


def _save_realistic_document_photo(path: Path, *, near_edge: bool = False, low_contrast: bool = False) -> None:
    background_color = (126, 116, 102) if not low_contrast else (112, 108, 102)
    image = Image.new("RGB", (1200, 1600), background_color)
    draw = ImageDraw.Draw(image)

    for x in range(0, image.width, 32):
        texture_delta = (x % 64 - 32) // 5
        texture_color = tuple(min(255, max(0, channel + texture_delta)) for channel in background_color)
        draw.line((x, 0, x, image.height), fill=texture_color, width=1)

    if near_edge:
        page_points = [(20, 70), (1020, 120), (1110, 1510), (15, 1450)]
    else:
        page_points = [(245, 120), (930, 220), (1015, 1435), (145, 1300)]

    shadow_points = [(x + 30, y + 45) for x, y in page_points]
    draw.polygon(shadow_points, fill=(82, 75, 68))

    page_fill = (248, 247, 239) if not low_contrast else (154, 150, 142)
    page_outline = (224, 222, 210) if not low_contrast else (136, 132, 126)
    ink_color = (20, 20, 20) if not low_contrast else (76, 74, 70)
    draw.polygon(page_points, fill=page_fill, outline=page_outline)

    draw.rectangle((340, 300, 720, 352), outline=ink_color, width=4)
    draw.text((360, 310), "DOCMOLDER TEST INVOICE", fill=ink_color)
    for y in range(440, 940, 75):
        draw.line((300, y, 830, y + 35), fill=ink_color, width=7)
    for x in (310, 520, 730):
        draw.line((x, 1040, x + 80, 1215), fill=ink_color, width=4)
    for y in (1040, 1098, 1156, 1214):
        draw.line((300, y, 850, y + 10), fill=ink_color, width=4)

    image = image.filter(ImageFilter.GaussianBlur(radius=0.4))
    image.save(path, quality=90)


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

    def test_process_pdf_crop_trims_uniform_page_border(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_pdf_crop" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = input_dir / "source.pdf"
        document = fitz.open()
        try:
            page = document.new_page(width=400, height=600)
            page.draw_rect(fitz.Rect(90, 120, 310, 480), color=(0, 0, 0), fill=(0.95, 0.95, 0.95), width=2)
            page.insert_text((120, 180), "DocMolder crop test", fontsize=16)
            document.save(pdf_path)
        finally:
            document.close()

        result = self.processor.process(SupportedAction.PDF_CROP, [pdf_path], "cropped_pdf")

        self.assertTrue(result.output_path.exists())
        self.assertIn("tagliato i bordi", result.message)
        cropped = fitz.open(result.output_path)
        try:
            page = cropped[0]
            self.assertLess(page.rect.width, 400)
            self.assertLess(page.rect.height, 600)
        finally:
            cropped.close()

    def test_process_pdf_crop_handles_rotated_pages_in_unrotated_coordinates(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_pdf_rotated_crop" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = input_dir / "source.pdf"
        document = fitz.open()
        try:
            page = document.new_page(width=400, height=600)
            page.draw_rect(fitz.Rect(90, 120, 310, 480), color=(0, 0, 0), fill=(0.95, 0.95, 0.95), width=2)
            page.insert_text((120, 180), "DocMolder rotated crop test", fontsize=16)
            page.set_rotation(90)
            document.save(pdf_path)
        finally:
            document.close()

        result = self.processor.process(SupportedAction.PDF_CROP, [pdf_path], "cropped_rotated_pdf", auto_rotate_pdf=False)

        cropped = fitz.open(result.output_path)
        try:
            page = cropped[0]
            self.assertEqual(page.rotation, 90)
            self.assertLess(page.rect.width, 600)
            self.assertLess(page.rect.height, 400)
            self.assertLess(page.cropbox.width, 400)
            self.assertLess(page.cropbox.height, 600)
        finally:
            cropped.close()

    def test_process_pdf_crop_keeps_photo_document_crop_native(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_pdf_photo_safe_crop" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        _save_realistic_document_photo(image_path)
        pdf_path = input_dir / "source.pdf"
        document = fitz.open()
        try:
            page = document.new_page(width=595.2, height=841.92)
            page.insert_image(fitz.Rect(55, 20, 540, 822), filename=str(image_path))
            document.save(pdf_path)
        finally:
            document.close()

        result = self.processor.process(SupportedAction.PDF_CROP, [pdf_path], "cropped_photo_pdf")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "native")
        self.assertNotIn("prospettici", result.message)
        cropped = fitz.open(result.output_path)
        try:
            page = cropped[0]
            self.assertLess(page.rect.width, 595.2)
            self.assertGreater(page.rect.width, 470)
            self.assertLess(page.rect.height, 841.92)
            self.assertGreater(page.rect.height, 640)
        finally:
            cropped.close()

    def test_process_dispatcher_covers_every_supported_action(self) -> None:
        self.assertEqual(set(self.processor._action_handlers), set(SupportedAction))

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

        merge = self.processor.process(SupportedAction.PDF_MERGE, [first_pdf, second_pdf], "merged_dispatch", auto_rotate_pdf=False)
        split = self.processor.process(SupportedAction.PDF_SPLIT, [first_pdf], "split_dispatch", split_output_zip=False)
        extract = self.processor.process(SupportedAction.PDF_EXTRACT_PAGES, [first_pdf], "extract_dispatch", page_selection="1")
        reorder = self.processor.process(SupportedAction.PDF_REORDER_PAGES, [first_pdf], "reorder_dispatch", page_selection="2 1")
        delete = self.processor.process(SupportedAction.PDF_DELETE_PAGES, [first_pdf], "delete_dispatch", page_selection="2")
        rotate = self.processor.process(SupportedAction.PDF_ROTATE, [first_pdf], "rotate_dispatch", rotate_degrees=90)
        watermark = self.processor.process(SupportedAction.PDF_WATERMARK, [first_pdf], "watermark_dispatch", watermark_text="BOZZA")
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

    def test_document_photo_fix_handles_realistic_synthetic_phone_photo(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_realistic_document_photo" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "desk_photo.jpg"
        _save_realistic_document_photo(image_path)

        result = self.processor.process(SupportedAction.DOCUMENT_PHOTO_FIX, [image_path], "realistic_document")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "opencv")
        self.assertIn("Correzione prospettica applicata a 1", result.message)
        self.assertNotIn("fallback conservativo", result.message)
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 1)

    def test_document_photo_fix_warns_when_realistic_page_is_near_photo_edges(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_realistic_document_near_edge" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "near_edge_photo.jpg"
        _save_realistic_document_photo(image_path, near_edge=True)

        result = self.processor.process(SupportedAction.DOCUMENT_PHOTO_FIX, [image_path], "near_edge_document")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "opencv")
        self.assertIn("Correzione prospettica applicata a 1", result.message)
        self.assertIn("foglio è vicino ai bordi", result.message)

    def test_document_photo_fix_handles_realistic_synthetic_batch(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_realistic_document_batch" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first_image = input_dir / "page_1.jpg"
        second_image = input_dir / "page_2.jpg"
        _save_realistic_document_photo(first_image)
        _save_realistic_document_photo(second_image, near_edge=True)

        result = self.processor.process(
            SupportedAction.DOCUMENT_PHOTO_FIX,
            [first_image, second_image],
            "realistic_document_batch",
        )

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "opencv")
        self.assertIn("2 foto dei documenti", result.message)
        self.assertIn("Correzione prospettica applicata a 2", result.message)
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 2)

    def test_document_photo_fix_uses_conservative_fallback_without_clear_page(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo_fallback" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "unclear.jpg"
        Image.new("RGB", (420, 320), (180, 180, 180)).save(image_path)

        result = self.processor.process(SupportedAction.DOCUMENT_PHOTO_FIX, [image_path], "document_photo_fallback")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "fallback")
        self.assertIn("fallback conservativo", result.message)
        self.assertIn("bordo leggibile", result.message)

    def test_document_photo_fix_can_keep_color_profile(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo_color" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        _save_realistic_document_photo(image_path)

        result = self.processor.document_photos_to_pdf(
            [image_path],
            "document_photo_color",
            mode=DocumentPhotoMode.COLOR,
        )

        self.assertTrue(result.output_path.exists())
        self.assertIn("mantenuto il colore", result.message)

    def test_document_photo_fix_can_use_clean_bw_profile(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo_bw" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        _save_realistic_document_photo(image_path)

        result = self.processor.document_photos_to_pdf(
            [image_path],
            "document_photo_bw",
            mode=DocumentPhotoMode.BW,
        )

        self.assertTrue(result.output_path.exists())
        self.assertIn("bianco/nero pulita", result.message)

    def test_document_photo_fix_warns_about_blurry_low_contrast_photo(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo_blurry" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "blurry.jpg"
        image = Image.new("RGB", (700, 900), (80, 80, 80))
        draw = ImageDraw.Draw(image)
        draw.rectangle((120, 120, 580, 780), fill=(98, 98, 96), outline=(105, 105, 103))
        image.filter(ImageFilter.GaussianBlur(radius=5)).save(image_path)

        result = self.processor.process(SupportedAction.DOCUMENT_PHOTO_FIX, [image_path], "document_photo_blurry")

        self.assertTrue(result.output_path.exists())
        self.assertIn("poco contrasto", result.message)
        self.assertIn("sfocate", result.message)

    def test_document_photo_fallback_caps_image_before_enhancement(self) -> None:
        image = Image.new("RGB", (3600, 2800), "white")

        with patch.object(self.processor, "_detect_document_photo_corners", return_value=None):
            transformed = self.processor._transform_document_photo(image)

        self.assertEqual(transformed.mode, "fallback")
        self.assertLessEqual(max(transformed.image.size), 2400 + (2400 // 45 * 2))

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

    def test_images_to_pdf_downscales_huge_inputs_before_conversion(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_huge_image" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "huge.jpg"
        Image.new("RGB", (900, 620), "white").save(image_path)
        processor = DocumentProcessor(self.runtime_dir, image_pdf_max_source_side_px=160)

        result = processor.images_to_pdf([image_path], "huge_downscaled", use_a4_layout=False)

        self.assertTrue(result.output_path.exists())
        self.assertIn("Ho ridotto 1 immagine molto grande", result.message)

    def test_images_to_pdf_streams_pages_through_intermediate_pdfs(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_streamed_images" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first_image = input_dir / "first.jpg"
        second_image = input_dir / "second.jpg"
        Image.new("RGB", (320, 180), "white").save(first_image)
        Image.new("RGB", (320, 180), "white").save(second_image)

        result = self.processor.images_to_pdf([first_image, second_image], "streamed")

        self.assertTrue(result.output_path.exists())
        self.assertFalse((input_dir / ".streamed_page_0001.pdf").exists())
        self.assertTrue((input_dir.parent / ".streamed_page_0001.pdf").exists())
        self.assertTrue((input_dir.parent / ".streamed_page_0002.pdf").exists())
        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 2)

    def test_prepare_image_downscales_in_place_to_limit_peak_memory(self) -> None:
        source = Image.new("RGB", (20, 20), "white")
        prepared = Image.new("RGB", (900, 620), "white")
        processor = DocumentProcessor(self.runtime_dir, image_pdf_max_source_side_px=160)
        processor.image_pdf_max_source_side_px = 160

        with (
            patch.object(ImageOps, "exif_transpose", return_value=prepared),
            patch.object(Image.Image, "copy", side_effect=AssertionError("unexpected full-size copy")),
        ):
            result, was_downscaled = processor._prepare_image_for_pdf(
                source,
                grayscale_output=False,
                auto_crop=False,
            )

        self.assertIs(result, prepared)
        self.assertTrue(was_downscaled)
        self.assertLessEqual(max(result.size), 160)
        result.close()
        source.close()

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

    def test_compress_pdf_mentions_when_reduction_is_minimal(self) -> None:
        pdf_path = self.runtime_dir / "already_small.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.compress_pdf(pdf_path, "already_small_light", CompressionPreset.LIGHT)

        self.assertTrue(result.output_path.exists())
        self.assertIn("non lo rende più leggero", result.message)

    def test_grayscale_uses_native_and_raster_fallback_messages(self) -> None:
        pdf_path = self.runtime_dir / "grayscale_branch.pdf"
        pdf_path.write_bytes(b"%PDF-branch")
        prepared_path = self.runtime_dir / "grayscale_prepared.pdf"
        prepared_path.write_bytes(b"%PDF-prepared")

        with (
            patch.object(self.processor, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 2)),
            patch.object(self.processor, "_validate_pdf_for_processing"),
            patch.object(self.processor, "_run_ghostscript_grayscale", return_value=False),
            patch.object(self.processor, "_convert_pdf_images_to_grayscale_native", return_value=True),
        ):
            native = self.processor.pdf_to_grayscale(pdf_path, "grayscale_native")

        with (
            patch.object(self.processor, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor, "_validate_pdf_for_processing"),
            patch.object(self.processor, "_run_ghostscript_grayscale", return_value=False),
            patch.object(self.processor, "_convert_pdf_images_to_grayscale_native", return_value=False),
            patch.object(self.processor, "_render_pdf_as_images") as render,
        ):
            raster = self.processor.pdf_to_grayscale(pdf_path, "grayscale_raster")

        self.assertEqual(native.processing_mode, "native")
        self.assertTrue(native.auto_rotation_applied)
        self.assertIn("orientamento di 2 pagine", native.message)
        self.assertEqual(raster.processing_mode, "raster")
        self.assertIn("ripiego", raster.message)
        render.assert_called_once()

    def test_compress_pdf_covers_ghostscript_lossless_and_raster_fallbacks(self) -> None:
        pdf_path = self.runtime_dir / "compress_branch.pdf"
        pdf_path.write_bytes(b"%PDF-branch")
        prepared_path = self.runtime_dir / "compress_prepared.pdf"
        prepared_path.write_bytes(b"%PDF-prepared")

        with (
            patch.object(self.processor, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 1)),
            patch.object(self.processor, "_validate_pdf_for_processing"),
            patch.object(self.processor, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor, "_run_ghostscript_compress", return_value=True),
        ):
            ghostscript = self.processor.compress_pdf(pdf_path, "compress_ghostscript", CompressionPreset.MEDIUM)

        with (
            patch.object(self.processor, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor, "_validate_pdf_for_processing"),
            patch.object(self.processor, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor, "_run_ghostscript_compress", return_value=False),
            patch.object(self.processor, "_compress_pdf_lossless") as lossless,
        ):
            lossless_result = self.processor.compress_pdf(pdf_path, "compress_lossless", CompressionPreset.MEDIUM)

        with (
            patch.object(self.processor, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor, "_validate_pdf_for_processing"),
            patch.object(self.processor, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor, "_run_ghostscript_compress", return_value=False),
            patch.object(self.processor, "_render_pdf_as_images") as render,
        ):
            raster = self.processor.compress_pdf(pdf_path, "compress_raster", CompressionPreset.STRONG)

        self.assertEqual(ghostscript.processing_mode, "ghostscript")
        self.assertTrue(ghostscript.auto_rotation_applied)
        self.assertIn("compressione più fedele", ghostscript.message)
        self.assertEqual(lossless_result.processing_mode, "lossless")
        lossless.assert_called_once()
        self.assertEqual(raster.processing_mode, "raster")
        self.assertIn("ripiego", raster.message)
        render.assert_called_once()

    def test_conservative_pdf_helpers_and_ghostscript_error_branches(self) -> None:
        pdf_path = self.runtime_dir / "conservative_source.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        conservative_output = self.runtime_dir / "conservative_output.pdf"
        self.assertTrue(
            self.processor._compress_pdf_conservative(
                pdf_path,
                conservative_output,
                image_quality=70,
                image_dpi_threshold=150,
                image_dpi_target=135,
            )
        )
        self.assertTrue(conservative_output.exists())

        grayscale_output = self.runtime_dir / "native_grayscale_output.pdf"
        with self.assertLogs("docmolder.processing", level="ERROR"):
            self.assertFalse(self.processor._convert_pdf_images_to_grayscale_native(pdf_path, grayscale_output))

        with (
            patch("docmolder.processing.shutil.which", return_value="gs"),
            patch("docmolder.processing.subprocess.run", return_value=subprocess.CompletedProcess(["gs"], 0)),
        ):
            self.assertTrue(self.processor._run_ghostscript_grayscale(pdf_path, self.runtime_dir / "gray_gs.pdf"))
            self.assertTrue(
                self.processor._run_ghostscript_compress(pdf_path, self.runtime_dir / "compress_gs.pdf", "/screen")
            )

        with (
            patch("docmolder.processing.shutil.which", return_value="gs"),
            patch(
                "docmolder.processing.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, ["gs"]),
            ),
        ):
            with self.assertLogs("docmolder.processing", level="ERROR"):
                self.assertFalse(self.processor._run_ghostscript_grayscale(pdf_path, self.runtime_dir / "gray_gs_fail.pdf"))
            with self.assertLogs("docmolder.processing", level="ERROR"):
                self.assertFalse(
                    self.processor._run_ghostscript_compress(pdf_path, self.runtime_dir / "compress_gs_fail.pdf", "/screen")
                )

    def test_auto_orient_images_returns_single_file_and_zip_for_batches(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_auto_orient_images" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first = input_dir / "first.png"
        second = input_dir / "second.jpg"
        Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(first)
        Image.new("RGB", (80, 60), "white").save(second)

        single = self.processor.auto_orient_images([first], "single_oriented")
        batch = self.processor.auto_orient_images([first, second], "batch_oriented")

        self.assertEqual(single.output_name, "single_oriented_1.png")
        self.assertTrue(single.output_path.exists())
        self.assertEqual(batch.output_name, "batch_oriented.zip")
        with zipfile.ZipFile(batch.output_path) as archive:
            self.assertEqual(archive.namelist(), ["batch_oriented_1.png", "batch_oriented_2.jpg"])

    def test_render_pdf_as_images_supports_png_and_jpeg_outputs(self) -> None:
        pdf_path = self.runtime_dir / "render_source.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=120, height=160)
        with pdf_path.open("wb") as handle:
            writer.write(handle)
        png_output = self.runtime_dir / "render_png.pdf"
        jpeg_output = self.runtime_dir / "render_jpeg.pdf"

        self.processor._render_pdf_as_images(pdf_path, png_output, dpi=72, colorspace=fitz.csGRAY, image_format="png")
        self.processor._render_pdf_as_images(
            pdf_path,
            jpeg_output,
            dpi=72,
            colorspace=fitz.csRGB,
            image_format="jpeg",
            jpeg_quality=60,
        )

        self.assertEqual(len(PdfReader(str(png_output)).pages), 1)
        self.assertEqual(len(PdfReader(str(jpeg_output)).pages), 1)

    def test_processing_helpers_cover_edge_cases_without_external_tools(self) -> None:
        self.assertIn(
            "formato originale",
            self.processor._build_images_to_pdf_message(
                auto_crop=True,
                grayscale_output=True,
                use_a4_layout=False,
                a4_margin_px=0,
                downscaled_images=2,
            ),
        )
        self.assertEqual(self.processor._describe_a4_margin(0), "nessun bordo")
        self.assertEqual(self.processor._format_page_numbers([]), "")
        self.assertEqual(self.processor._format_page_numbers([2]), "2")
        self.assertEqual(self.processor._build_compression_feedback(self.runtime_dir / "missing.pdf", self.runtime_dir / "missing-out.pdf"), "")
        empty = self.runtime_dir / "empty.bin"
        empty.write_bytes(b"")
        nonempty = self.runtime_dir / "nonempty.bin"
        nonempty.write_bytes(b"x")
        self.assertEqual(self.processor._build_compression_feedback(empty, nonempty), "")
        bigger = self.runtime_dir / "bigger.bin"
        bigger.write_bytes(b"x" * 100)
        smaller = self.runtime_dir / "smaller.bin"
        smaller.write_bytes(b"x" * 97)
        self.assertIn("minima", self.processor._build_compression_feedback(bigger, smaller))

        small = Image.new("RGB", (20, 20), "white")
        self.assertEqual(self.processor._auto_crop_scan_borders(small).size, small.size)
        blank = Image.new("RGB", (120, 120), "white")
        self.assertEqual(self.processor._auto_crop_scan_borders(blank).size, blank.size)
        full = Image.new("RGB", (120, 120), "black")
        self.assertEqual(self.processor._auto_crop_scan_borders(full).size, full.size)
        bordered = Image.new("RGB", (180, 180), "white")
        ImageDraw.Draw(bordered).rectangle((45, 45, 135, 135), fill="black")
        self.assertLess(self.processor._auto_crop_scan_borders(bordered).size[0], bordered.size[0])

        rgba = Image.new("RGBA", (4000, 1200), (255, 255, 255, 255))
        prepared, was_downscaled = self.processor._prepare_image_for_pdf(rgba, grayscale_output=False, auto_crop=False)
        try:
            self.assertEqual(prepared.mode, "RGB")
            self.assertTrue(was_downscaled)
            self.assertLessEqual(max(prepared.size), self.processor.image_pdf_max_source_side_px)
        finally:
            prepared.close()

        huge = Image.new("RGB", (3000, 1000), "white")
        limited = self.processor._limit_document_photo_output_size(huge)
        self.assertLessEqual(max(limited.size), 2400)
        same_size = self.processor._limit_document_photo_output_size(blank)
        self.assertEqual(same_size.size, blank.size)
        self.assertIsNone(self.processor._infer_target_page_orientation(["portrait", "landscape"]))

        warnings = self.processor._detect_document_photo_quality_warnings(Image.new("RGB", (200, 200), "black"))
        self.assertIn("foto_scura", warnings)
        bright_warnings = self.processor._detect_document_photo_quality_warnings(Image.new("RGB", (200, 200), "white"))
        self.assertIn("foto_molto_chiara", bright_warnings)

        tiny_quad = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype="float32")
        self.assertFalse(self.processor._is_plausible_document_quad(tiny_quad, (200, 200)))
        edge_quad = np.array([[0, 10], [100, 10], [100, 180], [0, 180]], dtype="float32")
        self.assertTrue(self.processor._document_corners_touch_image_edge(edge_quad, (120, 200)))

        message = self.processor._build_document_photos_to_pdf_message(
            total_images=1,
            perspective_count=0,
            fallback_count=1,
            warnings={"foto_scura", "foto_molto_chiara", "contrasto_basso", "foto_sfuocata", "contorno_non_sicuro"},
            mode=DocumentPhotoMode.READABLE,
        )
        self.assertIn("fallback conservativo", message)
        self.assertIn("molto chiare", message)

    def test_page_selection_parser_reports_user_friendly_errors(self) -> None:
        pdf_path = self.runtime_dir / "selection_source.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        invalid_cases = [
            (" ", "nessuna selezione"),
            ("1,,2", "virgola vuota"),
            ("a-2", "intervalli pagina"),
            ("2-1", "intervalli pagina"),
            ("due", "solo numeri"),
            ("4", "3 pagine"),
            ("1,1,2", "ogni pagina una sola volta"),
        ]
        for raw_value, expected_message in invalid_cases:
            with self.subTest(raw_value=raw_value):
                with self.assertRaisesRegex(ProcessingUserError, expected_message):
                    self.processor._parse_page_selection(raw_value, pdf_path, mode="full_reorder")

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
