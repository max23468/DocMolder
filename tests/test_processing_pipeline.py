from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.processing import DocumentProcessor


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


if __name__ == "__main__":
    unittest.main()
