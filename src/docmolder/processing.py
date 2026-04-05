from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError, PdfReadError

from docmolder.models import CompressionPreset, SupportedAction

logger = logging.getLogger(__name__)

A4_WIDTH_PX = 1240
A4_HEIGHT_PX = 1754
A4_MARGIN_PX = 90


@dataclass(slots=True)
class ProcessingResult:
    output_path: Path
    output_name: str
    message: str


class ProcessingUserError(Exception):
    pass


class DocumentProcessor:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir

    def create_job_dir(self, user_id: int) -> Path:
        job_dir = self.runtime_dir / "jobs" / f"user_{user_id}_{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def cleanup_job_dir(self, job_dir: Path) -> None:
        shutil.rmtree(job_dir, ignore_errors=True)

    def cleanup_stale_job_dirs(self, max_age_hours: int) -> int:
        jobs_dir = self.runtime_dir / "jobs"
        if not jobs_dir.exists():
            return 0

        threshold = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        removed_count = 0
        for job_dir in jobs_dir.iterdir():
            if not job_dir.is_dir():
                continue
            try:
                modified_at = datetime.fromtimestamp(job_dir.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if modified_at > threshold:
                continue
            try:
                shutil.rmtree(job_dir, ignore_errors=False)
                removed_count += 1
            except FileNotFoundError:
                continue
            except OSError:
                logger.exception("Impossibile ripulire la cartella temporanea %s", job_dir)
        return removed_count

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
                raise ValueError("Livello di compressione mancante.")
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
                    prepared_images.append(self._build_a4_page(corrected))

            first, *rest = prepared_images
            first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=150.0)
        finally:
            for image in prepared_images:
                image.close()

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message="PDF creato con successo in formato A4 con margini a partire dalle immagini ricevute.",
        )

    def merge_pdfs(self, pdf_paths: list[Path], output_stem: str) -> ProcessingResult:
        output_path = pdf_paths[0].parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        try:
            for pdf_path in pdf_paths:
                writer.append(str(pdf_path))
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise ProcessingUserError(
                "Non riesco a unire uno dei PDF ricevuti. "
                "Controlla che i file non siano protetti da password e riprova."
            ) from exc

        with output_path.open("wb") as handle:
            writer.write(handle)

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message="Ho unito i PDF in un unico documento.",
        )

    def pdf_to_grayscale(self, pdf_path: Path, output_stem: str) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        self._validate_pdf_for_processing(pdf_path)
        conversion_mode = "ghostscript" if self._run_ghostscript_grayscale(pdf_path, output_path) else None
        if conversion_mode is None and self._convert_pdf_images_to_grayscale_native(pdf_path, output_path):
            conversion_mode = "native"
        if conversion_mode is None:
            self._render_pdf_as_images(
                pdf_path=pdf_path,
                output_path=output_path,
                dpi=150,
                colorspace=fitz.csGRAY,
                image_format="png",
            )
            conversion_mode = "raster"

        message = "PDF convertito in scala di grigi."
        if conversion_mode == "native":
            message += " Ho preservato la struttura del PDF dove possibile."
        elif conversion_mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per garantire compatibilità."
        return ProcessingResult(output_path=output_path, output_name=output_path.name, message=message)

    def compress_pdf(self, pdf_path: Path, output_stem: str, preset: CompressionPreset) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        self._validate_pdf_for_processing(pdf_path)
        if preset == CompressionPreset.LIGHT:
            self._compress_pdf_lossless(pdf_path, output_path)
            mode = "lossless"
        elif preset == CompressionPreset.MEDIUM:
            if not self._compress_pdf_conservative(
                pdf_path,
                output_path,
                image_quality=70,
                image_dpi_threshold=150,
                image_dpi_target=135,
            ):
                if self._run_ghostscript_compress(pdf_path, output_path, quality_profile="/ebook"):
                    mode = "ghostscript"
                else:
                    self._compress_pdf_lossless(pdf_path, output_path)
                    mode = "lossless"
            else:
                mode = "conservative"
        else:
            if not self._compress_pdf_conservative(
                pdf_path,
                output_path,
                image_quality=50,
                image_dpi_threshold=110,
                image_dpi_target=95,
            ):
                if self._run_ghostscript_compress(pdf_path, output_path, quality_profile="/screen"):
                    mode = "ghostscript"
                else:
                    self._render_pdf_as_images(
                        pdf_path=pdf_path,
                        output_path=output_path,
                        dpi=110,
                        colorspace=fitz.csRGB,
                        image_format="jpeg",
                        jpeg_quality=50,
                    )
                    mode = "raster"
            else:
                mode = "conservative"
        message = f"PDF compresso con livello {preset.value}."
        if mode == "ghostscript":
            message += " Ho mantenuto il PDF nativo con una compressione più fedele."
        elif mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per i casi più difficili."
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
        )

    def rotate_pdf(self, pdf_path: Path, output_stem: str, rotate_degrees: int) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise ProcessingUserError(
                    "Questo PDF sembra protetto da password. "
                    "Per ruotarlo, invia prima una versione non protetta."
                )
            writer = PdfWriter()

            for page in reader.pages:
                page.rotate(rotate_degrees)
                writer.add_page(page)
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise ProcessingUserError(
                "Non riesco a leggere questo PDF per ruotarlo. "
                "Potrebbe essere corrotto o protetto da password."
            ) from exc

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
        document = self._open_pdf_document(pdf_path)
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
        image_dpi_target: int,
    ) -> bool:
        document = self._open_pdf_document(pdf_path)
        try:
            self._subset_fonts_if_possible(document)
            rewrite_images = getattr(document, "rewrite_images", None)
            if callable(rewrite_images):
                rewrite_images(
                    dpi_threshold=image_dpi_threshold,
                    dpi_target=image_dpi_target,
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

        command = self._build_ghostscript_grayscale_command(ghostscript, pdf_path, output_path)
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError:
            logger.exception("Ghostscript non è riuscito a convertire il PDF in scala di grigi.")
            return False

    def _run_ghostscript_compress(self, pdf_path: Path, output_path: Path, quality_profile: str) -> bool:
        ghostscript = shutil.which("gs")
        if ghostscript is None:
            return False

        command = self._build_ghostscript_compress_command(
            ghostscript=ghostscript,
            pdf_path=pdf_path,
            output_path=output_path,
            quality_profile=quality_profile,
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError:
            logger.exception("Ghostscript non è riuscito a comprimere il PDF con profilo %s.", quality_profile)
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
        self,
        ghostscript: str,
        pdf_path: Path,
        output_path: Path,
        quality_profile: str,
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

    def _convert_pdf_images_to_grayscale_native(self, pdf_path: Path, output_path: Path) -> bool:
        document = self._open_pdf_document(pdf_path)
        try:
            self._subset_fonts_if_possible(document)
            rewrite_images = getattr(document, "rewrite_images", None)
            if not callable(rewrite_images):
                return False
            rewrite_images(
                dpi_threshold=300,
                dpi_target=300,
                quality=85,
                lossy=False,
                lossless=True,
                bitonal=True,
                color=True,
                gray=True,
                set_to_gray=True,
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
            logger.exception("Conversione nativa in scala di grigi non riuscita, usero un fallback.")
            return False
        finally:
            document.close()

    def _subset_fonts_if_possible(self, document: fitz.Document) -> None:
        subset_fonts = getattr(document, "subset_fonts", None)
        if callable(subset_fonts):
            try:
                subset_fonts()
            except Exception:
                logger.exception("Subset dei font non riuscito, continuo senza questo passaggio.")

    def _validate_pdf_for_processing(self, pdf_path: Path) -> None:
        document = self._open_pdf_document(pdf_path)
        document.close()

    def _open_pdf_document(self, pdf_path: Path) -> fitz.Document:
        try:
            document = fitz.open(pdf_path)
        except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError) as exc:
            raise ProcessingUserError(
                "Non riesco a leggere questo PDF. "
                "Potrebbe essere corrotto, vuoto o non compatibile."
            ) from exc

        needs_pass = getattr(document, "needs_pass", False)
        if needs_pass:
            document.close()
            raise ProcessingUserError(
                "Questo PDF sembra protetto da password. "
                "Per elaborarlo, invia prima una versione non protetta."
            )
        return document

    def _build_a4_page(self, image: Image.Image) -> Image.Image:
        page = Image.new("RGB", (A4_WIDTH_PX, A4_HEIGHT_PX), "white")
        available_width = A4_WIDTH_PX - (2 * A4_MARGIN_PX)
        available_height = A4_HEIGHT_PX - (2 * A4_MARGIN_PX)

        content = image.copy()
        content.thumbnail((available_width, available_height), Image.Resampling.LANCZOS)

        offset_x = (A4_WIDTH_PX - content.width) // 2
        offset_y = (A4_HEIGHT_PX - content.height) // 2
        page.paste(content, (offset_x, offset_y))
        content.close()
        return page
