from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFilter
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import DocumentPhotoMode
from tests.test_processing_support import (
    ProcessingTestCase,
    save_realistic_document_photo as _save_realistic_document_photo,
)


class DocumentPhotoProcessorTest(ProcessingTestCase):
    def test_document_photo_fix_handles_realistic_synthetic_phone_photo(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_realistic_document_photo" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "desk_photo.jpg"
        _save_realistic_document_photo(image_path)

        result = self.processor.document_photos.document_photos_to_pdf([image_path], "realistic_document")

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

        result = self.processor.document_photos.document_photos_to_pdf([image_path], "near_edge_document")

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

        result = self.processor.document_photos.document_photos_to_pdf(
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

        result = self.processor.document_photos.document_photos_to_pdf([image_path], "document_photo_fallback")

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.processing_mode, "fallback")
        self.assertIn("fallback conservativo", result.message)
        self.assertIn("bordo leggibile", result.message)

    def test_document_photo_fix_can_keep_color_profile(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_document_photo_color" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        _save_realistic_document_photo(image_path)

        result = self.processor.document_photos.document_photos_to_pdf(
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

        result = self.processor.document_photos.document_photos_to_pdf(
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

        result = self.processor.document_photos.document_photos_to_pdf([image_path], "document_photo_blurry")

        self.assertTrue(result.output_path.exists())
        self.assertIn("poco contrasto", result.message)
        self.assertIn("sfocate", result.message)

    def test_document_photo_fallback_caps_image_before_enhancement(self) -> None:
        image = Image.new("RGB", (3600, 2800), "white")

        with patch.object(self.processor.document_photos, "_detect_document_photo_corners", return_value=None):
            transformed = self.processor.document_photos._transform_document_photo(image)

        self.assertEqual(transformed.mode, "fallback")
        self.assertLessEqual(max(transformed.image.size), 2400 + (2400 // 45 * 2))
