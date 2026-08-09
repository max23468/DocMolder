from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

import fitz
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import CompressionPreset
from docmolder.processing_models import ProcessingUserError
from tests.test_processing_support import (
    ProcessingTestCase,
    save_realistic_document_photo as _save_realistic_document_photo,
)


class PdfProcessorTest(ProcessingTestCase):
    def test_merge_requires_at_least_two_pdfs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.merge_pdfs([], "merged")

    def test_auto_orient_requires_inputs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.images.auto_orient_images([], "oriented")

    def test_grayscale_rejects_invalid_pdf(self) -> None:
        invalid_pdf = self.runtime_dir / "invalid.pdf"
        invalid_pdf.write_text("not a real pdf", encoding="utf-8")

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.pdf_to_grayscale(invalid_pdf, "grayscale")

    def test_grayscale_rejects_empty_pdf(self) -> None:
        empty_pdf = self.runtime_dir / "empty.pdf"
        empty_pdf.write_bytes(b"")

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.pdf_to_grayscale(empty_pdf, "grayscale_empty")

    def test_compress_rejects_password_protected_pdf(self) -> None:
        protected_pdf = self.runtime_dir / "protected.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("secret")
        with protected_pdf.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.compress_pdf(protected_pdf, "compressed", CompressionPreset.MEDIUM)

    def test_extract_pdf_pages_creates_subset(self) -> None:
        pdf_path = self.runtime_dir / "source_extract.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=220, height=300)
        writer.add_blank_page(width=240, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.extract_pdf_pages(pdf_path, "extracted", page_selection="1,3")

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

        result = self.processor.pdf.split_pdf_pages(pdf_path, "split_pages")

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
            self.processor.pdf.split_pdf_pages(pdf_path, "single_split")

    def test_split_pdf_pages_rejects_excessive_output_count(self) -> None:
        pdf_path = self.runtime_dir / "too_many_pages.pdf"
        writer = PdfWriter()
        for _ in range(51):
            writer.add_blank_page(width=200, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaisesRegex(ProcessingUserError, "50"):
            self.processor.pdf.split_pdf_pages(pdf_path, "too_many")

    def test_split_pdf_pages_can_return_separate_outputs(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_split_files" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = input_dir / "source_split_files.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=220, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.split_pdf_pages(pdf_path, "split_files", output_as_zip=False)

        self.assertEqual(result.output_name, "split_files_pagina_01.pdf")
        self.assertEqual([output.name for output in result.additional_outputs], ["split_files_pagina_02.pdf"])
        self.assertTrue(result.output_path.exists())
        self.assertTrue(result.additional_outputs[0].path.exists())
        self.assertIn("PDF separati", result.message)

    def test_split_pdf_pages_supports_custom_groups_and_fixed_chunks(self) -> None:
        pdf_path = self.runtime_dir / "source_grouped.pdf"
        writer = PdfWriter()
        for _ in range(6):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        grouped = self.processor.pdf.split_pdf_pages(pdf_path, "grouped", page_groups="1-2 | 3-6")
        chunked = self.processor.pdf.split_pdf_pages(pdf_path, "chunked", chunk_size=2)

        with zipfile.ZipFile(grouped.output_path) as archive:
            page_counts = [len(PdfReader(BytesIO(archive.read(name))).pages) for name in archive.namelist()]
        with zipfile.ZipFile(chunked.output_path) as archive:
            chunk_counts = [len(PdfReader(BytesIO(archive.read(name))).pages) for name in archive.namelist()]
        self.assertEqual(page_counts, [2, 4])
        self.assertEqual(chunk_counts, [2, 2, 2])

    def test_split_pdf_pages_rejects_custom_groups_that_omit_pages(self) -> None:
        pdf_path = self.runtime_dir / "source_invalid_groups.pdf"
        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaisesRegex(ProcessingUserError, "tutte le 4 pagine"):
            self.processor.pdf.split_pdf_pages(pdf_path, "invalid_groups", page_groups="1-2 | 4")

    def test_reorder_pdf_pages_requires_full_unique_order(self) -> None:
        pdf_path = self.runtime_dir / "source_reorder.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.reorder_pdf_pages(pdf_path, "reordered", page_selection="3,1")

    def test_reorder_pdf_pages_accepts_space_separated_order(self) -> None:
        pdf_path = self.runtime_dir / "source_reorder_spaces.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.reorder_pdf_pages(pdf_path, "reordered_spaces", page_selection="3 1 2")

        reader = PdfReader(str(result.output_path))
        self.assertEqual(len(reader.pages), 3)

    def test_delete_pdf_pages_keeps_remaining_pages(self) -> None:
        pdf_path = self.runtime_dir / "source_delete.pdf"
        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.delete_pdf_pages(pdf_path, "deleted", page_selection="2-3")

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
            self.processor.pdf.rotate_pdf(pdf_path, "rotated_invalid", 45)

    def test_add_text_watermark_creates_output(self) -> None:
        pdf_path = self.runtime_dir / "source_watermark.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.add_text_watermark(pdf_path, "watermarked", watermark_text="BOZZA")

        self.assertTrue(result.output_path.exists())
        self.assertIn("BOZZA", result.message)

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

        result = self.processor.pdf.crop_pdf_borders(pdf_path, "cropped_pdf")

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

        result = self.processor.pdf.crop_pdf_borders(pdf_path, "cropped_rotated_pdf", auto_rotate_pdf=False)

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

        result = self.processor.pdf.crop_pdf_borders(pdf_path, "cropped_photo_pdf")

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

    def test_merge_rejects_corrupt_pdf_among_inputs(self) -> None:
        valid_pdf = self.runtime_dir / "valid.pdf"
        corrupt_pdf = self.runtime_dir / "corrupt.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=400)
        with valid_pdf.open("wb") as handle:
            writer.write(handle)
        corrupt_pdf.write_text("not a pdf", encoding="utf-8")

        with self.assertRaises(ProcessingUserError):
            self.processor.pdf.merge_pdfs([valid_pdf, corrupt_pdf], "merged_corrupt")

    def test_compress_light_handles_multipage_pdf(self) -> None:
        multipage_pdf = self.runtime_dir / "multipage.pdf"
        writer = PdfWriter()
        for _ in range(24):
            writer.add_blank_page(width=595, height=842)
        with multipage_pdf.open("wb") as handle:
            writer.write(handle)

        result = self.processor.pdf.compress_pdf(multipage_pdf, "multipage_light", CompressionPreset.LIGHT)

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

        result = self.processor.pdf.compress_pdf(pdf_path, "already_small_light", CompressionPreset.LIGHT)

        self.assertTrue(result.output_path.exists())
        self.assertIn("non lo rende più leggero", result.message)

    def test_grayscale_uses_native_and_raster_fallback_messages(self) -> None:
        pdf_path = self.runtime_dir / "grayscale_branch.pdf"
        pdf_path.write_bytes(b"%PDF-branch")
        prepared_path = self.runtime_dir / "grayscale_prepared.pdf"
        prepared_path.write_bytes(b"%PDF-prepared")

        with (
            patch.object(self.processor.pdf, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 2)),
            patch.object(self.processor.pdf, "_validate_pdf_for_processing"),
            patch.object(self.processor.ghostscript, "_run_ghostscript_grayscale", return_value=False),
            patch.object(self.processor.pdf, "_convert_pdf_images_to_grayscale_native", return_value=True),
        ):
            native = self.processor.pdf.pdf_to_grayscale(pdf_path, "grayscale_native")

        with (
            patch.object(self.processor.pdf, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor.pdf, "_validate_pdf_for_processing"),
            patch.object(self.processor.ghostscript, "_run_ghostscript_grayscale", return_value=False),
            patch.object(self.processor.pdf, "_convert_pdf_images_to_grayscale_native", return_value=False),
            patch.object(self.processor.pdf, "_render_pdf_as_images") as render,
        ):
            raster = self.processor.pdf.pdf_to_grayscale(pdf_path, "grayscale_raster")

        self.assertEqual(native.processing_mode, "native")
        self.assertTrue(native.auto_rotation_applied)
        self.assertIn("orientamento di 2 pagine", native.message)
        self.assertEqual(raster.processing_mode, "raster")
        self.assertIn("ripiego", raster.message)
        render.assert_called_once()

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
            ("1-1000000000", "3 pagine"),
            ("1,1,2", "ogni pagina una sola volta"),
        ]
        for raw_value, expected_message in invalid_cases:
            with self.subTest(raw_value=raw_value):
                with self.assertRaisesRegex(ProcessingUserError, expected_message):
                    self.processor.pdf._parse_page_selection(raw_value, pdf_path, mode="full_reorder")

    def test_auto_rotate_pdf_to_dominant_orientation_rotates_outlier_pages(self) -> None:
        pdf_path = self.runtime_dir / "mostly_portrait.pdf"
        output_path = self.runtime_dir / "mostly_portrait_rotated.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=200, height=400)
        writer.add_blank_page(width=400, height=200)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        rotated_pages = self.processor.pdf._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

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

        rotated_pages = self.processor.pdf._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

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

        rotated_pages = self.processor.pdf._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

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

        rotated_pages = self.processor.pdf._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)

        self.assertEqual(rotated_pages, 1)
        reader = PdfReader(str(output_path))
        self.assertEqual(int(reader.pages[0].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[1].rotation or 0) % 360, 0)
        self.assertEqual(int(reader.pages[2].rotation or 0) % 360, 90)
