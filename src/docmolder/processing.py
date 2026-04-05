from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from docmolder.models import CompressionPreset, SupportedAction

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessingResult:
    output_path: Path
    output_name: str
    message: str


class DocumentProcessor:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir

    def create_job_dir(self, user_id: int) -> Path:
        job_dir = self.runtime_dir / "jobs" / f"user_{user_id}_{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def cleanup_job_dir(self, job_dir: Path) -> None:
        shutil.rmtree(job_dir, ignore_errors=True)

    def process(
        self,
        action: SupportedAction,
        input_paths: list[Path],
        output_stem: str,
        compression_preset: CompressionPreset | None = None,
        rotate_degrees: int | None = None,
    ) -> ProcessingResult:
        if action == SupportedAction.IMAGES_TO_PDF:
            return self.images_to_pdf(input_paths, output_stem)
        if action == SupportedAction.PDF_MERGE:
            return self.merge_pdfs(input_paths, output_stem)
        if action == SupportedAction.PDF_GRAYSCALE:
            return self.pdf_to_grayscale(input_paths[0], output_stem)
        if action == SupportedAction.PDF_COMPRESS:
            if compression_preset is None:
                raise ValueError("Preset di compressione mancante.")
            return self.compress_pdf(input_paths[0], output_stem, compression_preset)
        if action == SupportedAction.PDF_ROTATE:
            if rotate_degrees is None:
                raise ValueError("Rotazione mancante.")
            return self.rotate_pdf(input_paths[0], output_stem, rotate_degrees)
        if action == SupportedAction.AUTO_ORIENT:
            return self.auto_orient_images(input_paths, output_stem)
        raise ValueError(f"Azione non supportata: {action}")

    def images_to_pdf(self, image_paths: list[Path], output_stem: str) -> ProcessingResult:
        output_path = image_paths[0].parent.parent / f"{output_stem}.pdf"
        prepared_images: list[Image.Image] = []
        try:
            for image_path in image_paths:
                with Image.open(image_path) as image:
                    corrected = ImageOps.exif_transpose(image)
                    if corrected.mode not in ("RGB", "L"):
                        corrected = corrected.convert("RGB")
                    elif corrected.mode == "L":
                        corrected = corrected.convert("RGB")
                    prepared_images.append(corrected.copy())

            first, *rest = prepared_images
            first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=150.0)
        finally:
            for image in prepared_images:
                image.close()

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message="PDF creato con successo a partire dalle immagini ricevute.",
        )

    def merge_pdfs(self, pdf_paths: list[Path], output_stem: str) -> ProcessingResult:
        output_path = pdf_paths[0].parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        for pdf_path in pdf_paths:
            writer.append(str(pdf_path))

        with output_path.open("wb") as handle:
            writer.write(handle)

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message="Ho unito i PDF in un unico documento.",
        )

    def pdf_to_grayscale(self, pdf_path: Path, output_stem: str) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        if not self._run_ghostscript_grayscale(pdf_path, output_path):
            self._render_pdf_as_images(
                pdf_path=pdf_path,
                output_path=output_path,
                dpi=150,
                colorspace=fitz.csGRAY,
                image_format="png",
            )
        message = "PDF convertito in scala di grigi."
        if shutil.which("gs") is None:
            message += " Ho usato il fallback visivo per garantire compatibilita."
        return ProcessingResult(output_path=output_path, output_name=output_path.name, message=message)

    def compress_pdf(self, pdf_path: Path, output_stem: str, preset: CompressionPreset) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        if preset == CompressionPreset.LIGHT:
            self._compress_pdf_lossless(pdf_path, output_path)
        elif preset == CompressionPreset.MEDIUM:
            if not self._compress_pdf_conservative(pdf_path, output_path, image_quality=70, image_dpi_threshold=150):
                self._compress_pdf_lossless(pdf_path, output_path)
        else:
            if not self._compress_pdf_conservative(pdf_path, output_path, image_quality=50, image_dpi_threshold=110):
                self._render_pdf_as_images(
                    pdf_path=pdf_path,
                    output_path=output_path,
                    dpi=110,
                    colorspace=fitz.csRGB,
                    image_format="jpeg",
                    jpeg_quality=50,
                )
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF compresso con preset {preset.value}.",
        )

    def rotate_pdf(self, pdf_path: Path, output_stem: str, rotate_degrees: int) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()

        for page in reader.pages:
            page.rotate(rotate_degrees)
            writer.add_page(page)

        with output_path.open("wb") as handle:
            writer.write(handle)

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"Ho ruotato le pagine di {rotate_degrees} gradi.",
        )

    def auto_orient_images(self, image_paths: list[Path], output_stem: str) -> ProcessingResult:
        corrected_paths: list[Path] = []
        for index, image_path in enumerate(image_paths, start=1):
            suffix = image_path.suffix.lower() or ".jpg"
            output_path = image_path.parent / f"{output_stem}_{index}{suffix}"
            with Image.open(image_path) as image:
                corrected = ImageOps.exif_transpose(image)
                save_image = corrected
                if suffix in {".jpg", ".jpeg"} and corrected.mode not in ("RGB", "L"):
                    save_image = corrected.convert("RGB")
                save_image.save(output_path)
            corrected_paths.append(output_path)

        if len(corrected_paths) == 1:
            single = corrected_paths[0]
            return ProcessingResult(
                output_path=single,
                output_name=single.name,
                message="Ho corretto l'orientamento dell'immagine.",
            )

        archive_path = image_paths[0].parent.parent / f"{output_stem}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in corrected_paths:
                archive.write(path, arcname=path.name)

        return ProcessingResult(
            output_path=archive_path,
            output_name=archive_path.name,
            message="Ho corretto l'orientamento delle immagini e creato un archivio ZIP.",
        )

    def _render_pdf_as_images(
        self,
        pdf_path: Path,
        output_path: Path,
        dpi: int,
        colorspace: fitz.Colorspace,
        image_format: str,
        jpeg_quality: int | None = None,
    ) -> None:
        source = fitz.open(pdf_path)
        destination = fitz.open()
        try:
            for page in source:
                pixmap = page.get_pixmap(dpi=dpi, colorspace=colorspace, alpha=False)
                image_bytes = pixmap.tobytes("png" if image_format == "png" else "ppm")
                with Image.open(BytesIO(image_bytes)) as image:
                    if image_format == "jpeg":
                        if image.mode != "RGB":
                            image = image.convert("RGB")
                        buffer = BytesIO()
                        image.save(buffer, format="JPEG", quality=jpeg_quality or 75, optimize=True)
                        image_stream = buffer.getvalue()
                    else:
                        buffer = BytesIO()
                        image.save(buffer, format="PNG", optimize=True)
                        image_stream = buffer.getvalue()

                rect = fitz.Rect(0, 0, pixmap.width, pixmap.height)
                out_page = destination.new_page(width=rect.width, height=rect.height)
                out_page.insert_image(rect, stream=image_stream)

            destination.save(output_path, garbage=4, deflate=True)
        finally:
            destination.close()
            source.close()

    def _compress_pdf_lossless(self, pdf_path: Path, output_path: Path) -> None:
        document = fitz.open(pdf_path)
        try:
            self._subset_fonts_if_possible(document)
            document.save(
                output_path,
                garbage=4,
                clean=True,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                use_objstms=1,
            )
        finally:
            document.close()

    def _compress_pdf_conservative(
        self,
        pdf_path: Path,
        output_path: Path,
        image_quality: int,
        image_dpi_threshold: int,
    ) -> bool:
        document = fitz.open(pdf_path)
        try:
            self._subset_fonts_if_possible(document)
            rewrite_images = getattr(document, "rewrite_images", None)
            if callable(rewrite_images):
                rewrite_images(
                    dpi_threshold=image_dpi_threshold,
                    dpi_target=image_dpi_threshold,
                    quality=image_quality,
                    lossy=True,
                    lossless=True,
                    bitonal=True,
                    color=True,
                    gray=True,
                    set_to_gray=False,
                )
            document.save(
                output_path,
                garbage=4,
                clean=True,
                deflate=True,
                deflate_images=True,
                deflate_fonts=True,
                use_objstms=1,
            )
            return True
        except Exception:
            logger.exception("Compressione conservativa non riuscita, usero un fallback.")
            return False
        finally:
            document.close()

    def _run_ghostscript_grayscale(self, pdf_path: Path, output_path: Path) -> bool:
        ghostscript = shutil.which("gs")
        if ghostscript is None:
            return False

        command = [
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
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError:
            logger.exception("Ghostscript non e riuscito a convertire il PDF in scala di grigi.")
            return False

    def _subset_fonts_if_possible(self, document: fitz.Document) -> None:
        subset_fonts = getattr(document, "subset_fonts", None)
        if callable(subset_fonts):
            try:
                subset_fonts()
            except Exception:
                logger.exception("Subset dei font non riuscito, continuo senza questo passaggio.")
