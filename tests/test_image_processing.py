from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import zipfile

import fitz
from PIL import Image, ImageDraw, ImageOps
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.processing import DocumentProcessor
from docmolder.processing_models import A4_MARGIN_WIDE_PX, ProcessingUserError
from tests.test_processing_support import ProcessingTestCase


class ImageProcessorTest(ProcessingTestCase):
    def test_images_to_pdf_requires_inputs(self) -> None:
        with self.assertRaises(ProcessingUserError):
            self.processor.images.images_to_pdf([], "images")

    def test_auto_crop_scan_borders_removes_uniform_border(self) -> None:
        image = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 40, 340, 260), fill="black")

        cropped = self.processor.images._auto_crop_scan_borders(image)

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

        result = self.processor.images.images_to_pdf([image_path], "cropped", auto_crop=True)

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "cropped.pdf")

    def test_images_to_pdf_can_keep_original_image_format(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_2" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        result = self.processor.images.images_to_pdf([image_path], "original_layout", use_a4_layout=False)

        self.assertTrue(result.output_path.exists())
        self.assertIn("formato originale", result.message)

    def test_images_to_pdf_mentions_selected_a4_margin(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_3" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "photo.jpg"
        Image.new("RGB", (320, 180), "white").save(image_path)

        result = self.processor.images.images_to_pdf(
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

        result = self.processor.images.images_to_pdf([image_path], "gray_direct", grayscale_output=True)

        self.assertTrue(result.output_path.exists())
        self.assertIn("scala di grigi", result.message)

    def test_images_to_pdf_downscales_huge_inputs_before_conversion(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_huge_image" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        image_path = input_dir / "huge.jpg"
        Image.new("RGB", (900, 620), "white").save(image_path)
        processor = DocumentProcessor(self.runtime_dir, image_pdf_max_source_side_px=160)

        result = processor.images.images_to_pdf([image_path], "huge_downscaled", use_a4_layout=False)

        self.assertTrue(result.output_path.exists())
        self.assertIn("Ho ridotto 1 immagine molto grande", result.message)

    def test_images_to_pdf_streams_pages_through_intermediate_pdfs(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_streamed_images" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first_image = input_dir / "first.jpg"
        second_image = input_dir / "second.jpg"
        Image.new("RGB", (320, 180), "white").save(first_image)
        Image.new("RGB", (320, 180), "white").save(second_image)

        result = self.processor.images.images_to_pdf([first_image, second_image], "streamed")

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
        processor.images.image_pdf_max_source_side_px = 160

        with (
            patch.object(ImageOps, "exif_transpose", return_value=prepared),
            patch.object(Image.Image, "copy", side_effect=AssertionError("unexpected full-size copy")),
        ):
            result, was_downscaled = processor.images._prepare_image_for_pdf(
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

        with patch.object(
            self.processor.pdf,
            "pdf_to_grayscale",
            side_effect=AssertionError("unexpected roundtrip"),
        ):
            result = self.processor.images.images_to_pdf([image_path], "gray_process", grayscale_output=True)

        self.assertTrue(result.output_path.exists())
        self.assertEqual(result.output_name, "gray_process.pdf")
        self.assertIn("scala di grigi", result.message)

    def test_auto_orient_images_returns_single_file_and_zip_for_batches(self) -> None:
        input_dir = self.runtime_dir / "jobs" / "job_auto_orient_images" / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        first = input_dir / "first.png"
        second = input_dir / "second.jpg"
        Image.new("RGBA", (80, 60), (255, 255, 255, 255)).save(first)
        Image.new("RGB", (80, 60), "white").save(second)

        single = self.processor.images.auto_orient_images([first], "single_oriented")
        batch = self.processor.images.auto_orient_images([first, second], "batch_oriented")

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

        self.processor.pdf._render_pdf_as_images(
            pdf_path, png_output, dpi=72, colorspace=fitz.csGRAY, image_format="png"
        )
        self.processor.pdf._render_pdf_as_images(
            pdf_path,
            jpeg_output,
            dpi=72,
            colorspace=fitz.csRGB,
            image_format="jpeg",
            jpeg_quality=60,
        )

        self.assertEqual(len(PdfReader(str(png_output)).pages), 1)
        self.assertEqual(len(PdfReader(str(jpeg_output)).pages), 1)

    def test_open_image_rejects_pixel_budget_before_decode(self) -> None:
        image = MagicMock(width=50_000, height=50_000)
        with patch("docmolder.image_processing.Image.open", return_value=image):
            with self.assertRaisesRegex(ProcessingUserError, "budget"):
                self.processor.images._open_image(self.runtime_dir / "huge.png")
        image.close.assert_called_once()
