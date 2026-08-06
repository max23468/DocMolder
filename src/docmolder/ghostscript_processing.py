from __future__ import annotations
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GhostscriptProcessor:
    def __init__(self, timeout_seconds: int):
        self.ghostscript_timeout_seconds = max(1, timeout_seconds)

    def _run_ghostscript_grayscale(self, pdf_path: Path, output_path: Path) -> bool:
        ghostscript = shutil.which("gs")
        if ghostscript is None:
            return False
        command = self._build_ghostscript_grayscale_command(ghostscript, pdf_path, output_path)
        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True, timeout=self.ghostscript_timeout_seconds
            )
            return True
        except subprocess.CalledProcessError:
            logger.exception("Ghostscript non è riuscito a convertire il PDF in scala di grigi.")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(
                "Ghostscript ha superato il timeout di %s secondi durante la conversione in scala di grigi.",
                self.ghostscript_timeout_seconds,
            )
            return False

    def _run_ghostscript_compress(self, pdf_path: Path, output_path: Path, quality_profile: str) -> bool:
        ghostscript = shutil.which("gs")
        if ghostscript is None:
            return False
        command = self._build_ghostscript_compress_command(
            ghostscript=ghostscript, pdf_path=pdf_path, output_path=output_path, quality_profile=quality_profile
        )
        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True, timeout=self.ghostscript_timeout_seconds
            )
            return True
        except subprocess.CalledProcessError:
            logger.exception("Ghostscript non è riuscito a comprimere il PDF con profilo %s.", quality_profile)
            return False
        except subprocess.TimeoutExpired:
            logger.warning(
                "Ghostscript ha superato il timeout di %s secondi durante la compressione con profilo %s.",
                self.ghostscript_timeout_seconds,
                quality_profile,
            )
            return False

    def _build_ghostscript_grayscale_command(self, ghostscript: str, pdf_path: Path, output_path: Path) -> list[str]:
        return [
            ghostscript,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sColorConversionStrategy=Gray",
            "-dProcessColorModel=/DeviceGray",
            "-dAutoRotatePages=/None",
            f"-sOutputFile={output_path}",
            str(pdf_path),
        ]

    def _build_ghostscript_compress_command(
        self, ghostscript: str, pdf_path: Path, output_path: Path, quality_profile: str
    ) -> list[str]:
        return [
            ghostscript,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            f"-dPDFSETTINGS={quality_profile}",
            "-dAutoRotatePages=/None",
            f"-sOutputFile={output_path}",
            str(pdf_path),
        ]
