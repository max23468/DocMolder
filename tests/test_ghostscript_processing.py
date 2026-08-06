from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.models import CompressionPreset
from tests.test_processing_support import ProcessingTestCase


class GhostscriptProcessorTest(ProcessingTestCase):
    def test_build_ghostscript_grayscale_command(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        command = self.processor.ghostscript._build_ghostscript_grayscale_command("gs", pdf_path, output_path)

        self.assertIn("-sColorConversionStrategy=Gray", command)
        self.assertIn("-dProcessColorModel=/DeviceGray", command)
        self.assertIn(f"-sOutputFile={output_path}", command)
        self.assertEqual(command[-1], str(pdf_path))

    def test_real_ghostscript_grayscale_smoke(self) -> None:
        if shutil.which("gs") is None:
            self.skipTest("Ghostscript non disponibile")
        pdf_path = self.runtime_dir / "ghostscript_source.pdf"
        output_path = self.runtime_dir / "ghostscript_gray.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        self.assertTrue(self.processor.ghostscript._run_ghostscript_grayscale(pdf_path, output_path))
        self.assertEqual(len(PdfReader(str(output_path)).pages), 1)

    def test_build_ghostscript_compress_command(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        command = self.processor.ghostscript._build_ghostscript_compress_command(
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
            patch("docmolder.ghostscript_processing.shutil.which", return_value="gs"),
            patch(
                "docmolder.ghostscript_processing.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["gs"], timeout=5),
            ),
        ):
            result = self.processor.ghostscript._run_ghostscript_grayscale(pdf_path, output_path)

        self.assertFalse(result)

    def test_run_ghostscript_compress_returns_false_on_timeout(self) -> None:
        pdf_path = Path("/tmp/input.pdf")
        output_path = Path("/tmp/output.pdf")

        with (
            patch("docmolder.ghostscript_processing.shutil.which", return_value="gs"),
            patch(
                "docmolder.ghostscript_processing.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["gs"], timeout=5),
            ),
        ):
            result = self.processor.ghostscript._run_ghostscript_compress(
                pdf_path, output_path, quality_profile="/ebook"
            )

        self.assertFalse(result)

    def test_compress_pdf_covers_ghostscript_lossless_and_raster_fallbacks(self) -> None:
        pdf_path = self.runtime_dir / "compress_branch.pdf"
        pdf_path.write_bytes(b"%PDF-branch")
        prepared_path = self.runtime_dir / "compress_prepared.pdf"
        prepared_path.write_bytes(b"%PDF-prepared")

        with (
            patch.object(self.processor.pdf, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 1)),
            patch.object(self.processor.pdf, "_validate_pdf_for_processing"),
            patch.object(self.processor.pdf, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor.ghostscript, "_run_ghostscript_compress", return_value=True),
        ):
            ghostscript = self.processor.pdf.compress_pdf(pdf_path, "compress_ghostscript", CompressionPreset.MEDIUM)

        with (
            patch.object(self.processor.pdf, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor.pdf, "_validate_pdf_for_processing"),
            patch.object(self.processor.pdf, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor.ghostscript, "_run_ghostscript_compress", return_value=False),
            patch.object(self.processor.pdf, "_compress_pdf_lossless") as lossless,
        ):
            lossless_result = self.processor.pdf.compress_pdf(pdf_path, "compress_lossless", CompressionPreset.MEDIUM)

        with (
            patch.object(self.processor.pdf, "_prepare_single_pdf_for_processing", return_value=(prepared_path, 0)),
            patch.object(self.processor.pdf, "_validate_pdf_for_processing"),
            patch.object(self.processor.pdf, "_compress_pdf_conservative", return_value=False),
            patch.object(self.processor.ghostscript, "_run_ghostscript_compress", return_value=False),
            patch.object(self.processor.pdf, "_render_pdf_as_images") as render,
        ):
            raster = self.processor.pdf.compress_pdf(pdf_path, "compress_raster", CompressionPreset.STRONG)

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
            self.processor.pdf._compress_pdf_conservative(
                pdf_path,
                conservative_output,
                image_quality=70,
                image_dpi_threshold=150,
                image_dpi_target=135,
            )
        )
        self.assertTrue(conservative_output.exists())

        grayscale_output = self.runtime_dir / "native_grayscale_output.pdf"
        with self.assertLogs("docmolder.pdf_processing", level="ERROR"):
            self.assertFalse(self.processor.pdf._convert_pdf_images_to_grayscale_native(pdf_path, grayscale_output))

        with (
            patch("docmolder.ghostscript_processing.shutil.which", return_value="gs"),
            patch(
                "docmolder.ghostscript_processing.subprocess.run", return_value=subprocess.CompletedProcess(["gs"], 0)
            ),
        ):
            self.assertTrue(
                self.processor.ghostscript._run_ghostscript_grayscale(pdf_path, self.runtime_dir / "gray_gs.pdf")
            )
            self.assertTrue(
                self.processor.ghostscript._run_ghostscript_compress(
                    pdf_path, self.runtime_dir / "compress_gs.pdf", "/screen"
                )
            )

        with (
            patch("docmolder.ghostscript_processing.shutil.which", return_value="gs"),
            patch(
                "docmolder.ghostscript_processing.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, ["gs"]),
            ),
        ):
            with self.assertLogs("docmolder.ghostscript_processing", level="ERROR"):
                self.assertFalse(
                    self.processor.ghostscript._run_ghostscript_grayscale(
                        pdf_path, self.runtime_dir / "gray_gs_fail.pdf"
                    )
                )
            with self.assertLogs("docmolder.ghostscript_processing", level="ERROR"):
                self.assertFalse(
                    self.processor.ghostscript._run_ghostscript_compress(
                        pdf_path, self.runtime_dir / "compress_gs_fail.pdf", "/screen"
                    )
                )
