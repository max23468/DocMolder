from __future__ import annotations

import logging
import re
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError, PdfReadError

from docmolder.models import CompressionPreset, SupportedAction

logger = logging.getLogger(__name__)

A4_WIDTH_PX = 1240
A4_HEIGHT_PX = 1754
A4_MARGIN_WIDE_PX = 120
A4_MARGIN_NARROW_PX = 48
A4_MARGIN_NONE_PX = 0


@dataclass(slots=True)
class ProcessingResult:
    output_path: Path
    output_name: str
    message: str
    auto_rotation_applied: bool = False
    processing_mode: str | None = None


class ProcessingUserError(Exception):
    pass


class DocumentProcessor:
    def __init__(self, runtime_dir: Path, ghostscript_timeout_seconds: int = 120) -> None:
        self.runtime_dir = runtime_dir
        self.ghostscript_timeout_seconds = max(1, ghostscript_timeout_seconds)

    def create_job_dir(self, user_id: int) -> Path:
        job_dir = self.runtime_dir / "jobs" / f"user_{user_id}_{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def cleanup_job_dir(self, job_dir: Path) -> None:
        try:
            shutil.rmtree(job_dir)
        except FileNotFoundError:
            return
        except OSError:
            logger.exception("Impossibile ripulire la cartella temporanea del job %s", job_dir)

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
        page_selection: str | None = None,
        watermark_text: str | None = None,
        auto_rotate_pdf: bool = True,
        image_pdf_use_a4: bool = True,
        image_pdf_margin_px: int = A4_MARGIN_NARROW_PX,
    ) -> ProcessingResult:
        if action == SupportedAction.IMAGES_TO_PDF:
            return self.images_to_pdf(
                input_paths,
                output_stem,
                use_a4_layout=image_pdf_use_a4,
                a4_margin_px=image_pdf_margin_px,
            )
        if action == SupportedAction.IMAGES_TO_PDF_CROP:
            return self.images_to_pdf(
                input_paths,
                output_stem,
                auto_crop=True,
                use_a4_layout=image_pdf_use_a4,
                a4_margin_px=image_pdf_margin_px,
            )
        if action == SupportedAction.IMAGES_TO_PDF_GRAYSCALE:
            return self.images_to_pdf(
                input_paths,
                output_stem,
                grayscale_output=True,
                use_a4_layout=image_pdf_use_a4,
                a4_margin_px=image_pdf_margin_px,
            )
        if action == SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE:
            return self.images_to_pdf(
                input_paths,
                output_stem,
                auto_crop=True,
                grayscale_output=True,
                use_a4_layout=image_pdf_use_a4,
                a4_margin_px=image_pdf_margin_px,
            )
        if action == SupportedAction.PDF_MERGE:
            return self.merge_pdfs(input_paths, output_stem, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_EXTRACT_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.extract_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_REORDER_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.reorder_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_DELETE_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.delete_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_GRAYSCALE:
            return self.pdf_to_grayscale(input_paths[0], output_stem, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_COMPRESS:
            if compression_preset is None:
                raise ValueError("Livello di compressione mancante.")
            return self.compress_pdf(input_paths[0], output_stem, compression_preset, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_ROTATE:
            if rotate_degrees is None:
                raise ValueError("Rotazione mancante.")
            return self.rotate_pdf(input_paths[0], output_stem, rotate_degrees)
        if action == SupportedAction.PDF_WATERMARK:
            if watermark_text is None:
                raise ValueError("Testo watermark mancante.")
            return self.add_text_watermark(input_paths[0], output_stem, watermark_text=watermark_text)
        if action == SupportedAction.AUTO_ORIENT:
            return self.auto_orient_images(input_paths, output_stem)
        raise ValueError(f"Azione non supportata: {action}")

    def images_to_pdf(
        self,
        image_paths: list[Path],
        output_stem: str,
        auto_crop: bool = False,
        *,
        grayscale_output: bool = False,
        use_a4_layout: bool = True,
        a4_margin_px: int = A4_MARGIN_NARROW_PX,
    ) -> ProcessingResult:
        if not image_paths:
            raise ProcessingUserError("Non ho ricevuto immagini da convertire in PDF.")
        output_path = image_paths[0].parent.parent / f"{output_stem}.pdf"
        prepared_images: list[Image.Image] = []
        try:
            for image_path in image_paths:
                with Image.open(image_path) as image:
                    corrected = ImageOps.exif_transpose(image)
                    if grayscale_output:
                        if corrected.mode != "L":
                            corrected = ImageOps.grayscale(corrected)
                    elif corrected.mode not in ("RGB", "L"):
                        corrected = corrected.convert("RGB")
                    elif corrected.mode == "L":
                        corrected = corrected.convert("RGB")
                    if auto_crop:
                        corrected = self._auto_crop_scan_borders(corrected)
                    if use_a4_layout:
                        prepared_images.append(self._build_a4_page(corrected, margin_px=a4_margin_px))
                    else:
                        prepared_images.append(corrected.copy())

            first, *rest = prepared_images
            first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=150.0)
        finally:
            for image in prepared_images:
                image.close()

        message = self._build_images_to_pdf_message(
            auto_crop=auto_crop,
            grayscale_output=grayscale_output,
            use_a4_layout=use_a4_layout,
            a4_margin_px=a4_margin_px,
        )

        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            processing_mode="native" if grayscale_output else None,
        )

    def merge_pdfs(self, pdf_paths: list[Path], output_stem: str, auto_rotate_pdf: bool = True) -> ProcessingResult:
        if len(pdf_paths) < 2:
            raise ProcessingUserError("Per unire i PDF devo riceverne almeno due.")
        prepared_paths = pdf_paths
        rotated_pages = 0
        if auto_rotate_pdf:
            prepared_paths, rotated_pages = self._prepare_pdf_inputs_for_processing(pdf_paths)
        output_path = pdf_paths[0].parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        try:
            for pdf_path in prepared_paths:
                writer.append(str(pdf_path))
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise ProcessingUserError(
                "Non riesco a unire uno dei PDF ricevuti. "
                "Controlla che i file non siano protetti da password e riprova."
            ) from exc

        with output_path.open("wb") as handle:
            writer.write(handle)

        message = "PDF pronto. Ho unito i file in un unico documento."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode="native",
        )

    def pdf_to_grayscale(self, pdf_path: Path, output_stem: str, auto_rotate_pdf: bool = True) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        prepared_path = pdf_path
        rotated_pages = 0
        if auto_rotate_pdf:
            prepared_path, rotated_pages = self._prepare_single_pdf_for_processing(pdf_path)
        self._validate_pdf_for_processing(pdf_path)
        conversion_mode = "ghostscript" if self._run_ghostscript_grayscale(prepared_path, output_path) else None
        if conversion_mode is None and self._convert_pdf_images_to_grayscale_native(prepared_path, output_path):
            conversion_mode = "native"
        if conversion_mode is None:
            self._render_pdf_as_images(
                pdf_path=prepared_path,
                output_path=output_path,
                dpi=150,
                colorspace=fitz.csGRAY,
                image_format="png",
            )
            conversion_mode = "raster"

        message = "PDF pronto in scala di grigi."
        if conversion_mode == "native":
            message += " Ho convertito soprattutto le immagini interne e preservato la struttura del PDF dove possibile."
        elif conversion_mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per garantire compatibilità. Il risultato potrebbe non mantenere testo ricercabile o struttura interna del PDF."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode=conversion_mode,
        )

    def compress_pdf(
        self,
        pdf_path: Path,
        output_stem: str,
        preset: CompressionPreset,
        auto_rotate_pdf: bool = True,
    ) -> ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        prepared_path = pdf_path
        rotated_pages = 0
        if auto_rotate_pdf:
            prepared_path, rotated_pages = self._prepare_single_pdf_for_processing(pdf_path)
        self._validate_pdf_for_processing(pdf_path)
        if preset == CompressionPreset.LIGHT:
            self._compress_pdf_lossless(prepared_path, output_path)
            mode = "lossless"
        elif preset == CompressionPreset.MEDIUM:
            if not self._compress_pdf_conservative(
                prepared_path,
                output_path,
                image_quality=70,
                image_dpi_threshold=150,
                image_dpi_target=135,
            ):
                if self._run_ghostscript_compress(prepared_path, output_path, quality_profile="/ebook"):
                    mode = "ghostscript"
                else:
                    self._compress_pdf_lossless(prepared_path, output_path)
                    mode = "lossless"
            else:
                mode = "conservative"
        else:
            if not self._compress_pdf_conservative(
                prepared_path,
                output_path,
                image_quality=50,
                image_dpi_threshold=110,
                image_dpi_target=95,
            ):
                if self._run_ghostscript_compress(prepared_path, output_path, quality_profile="/screen"):
                    mode = "ghostscript"
                else:
                    self._render_pdf_as_images(
                        pdf_path=prepared_path,
                        output_path=output_path,
                        dpi=110,
                        colorspace=fitz.csRGB,
                        image_format="jpeg",
                        jpeg_quality=50,
                    )
                    mode = "raster"
            else:
                mode = "conservative"
        message = f"PDF pronto. Compressione completata con livello {preset.value}."
        if mode == "ghostscript":
            message += " Ho mantenuto il PDF nativo con una compressione più fedele."
        elif mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per i casi più difficili. Il risultato finale potrebbe non mantenere pienamente testo ricercabile o struttura interna del PDF."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode=mode,
        )

    def rotate_pdf(self, pdf_path: Path, output_stem: str, rotate_degrees: int) -> ProcessingResult:
        if rotate_degrees not in {90, 180, 270}:
            raise ProcessingUserError("Per la rotazione manuale puoi usare solo 90, 180 o 270 gradi.")
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
            message=f"PDF pronto. Ho ruotato le pagine di {rotate_degrees} gradi.",
            processing_mode="native",
        )

    def extract_pdf_pages(self, pdf_path: Path, output_stem: str, *, page_selection: str) -> ProcessingResult:
        page_numbers = self._parse_page_selection(page_selection, pdf_path, mode="subset")
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        reader = self._build_pdf_reader(pdf_path)
        writer = PdfWriter()
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho estratto le pagine {self._format_page_numbers(page_numbers)}.",
            processing_mode="native",
        )

    def reorder_pdf_pages(self, pdf_path: Path, output_stem: str, *, page_selection: str) -> ProcessingResult:
        reader = self._build_pdf_reader(pdf_path)
        page_numbers = self._parse_page_selection(page_selection, pdf_path, mode="full_reorder")
        if len(page_numbers) != len(reader.pages):
            raise ProcessingUserError(
                "Per riordinare le pagine devo ricevere l'ordine completo del PDF, ad esempio 3,1,2 per un PDF di 3 pagine."
            )
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho riordinato le pagine nel nuovo ordine {self._format_page_numbers(page_numbers)}.",
            processing_mode="native",
        )

    def delete_pdf_pages(self, pdf_path: Path, output_stem: str, *, page_selection: str) -> ProcessingResult:
        reader = self._build_pdf_reader(pdf_path)
        to_delete = set(self._parse_page_selection(page_selection, pdf_path, mode="subset"))
        remaining_pages = [index + 1 for index in range(len(reader.pages)) if (index + 1) not in to_delete]
        if not remaining_pages:
            raise ProcessingUserError("Non posso eliminare tutte le pagine del PDF. Deve restarne almeno una.")
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        for page_number in remaining_pages:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho eliminato le pagine {self._format_page_numbers(sorted(to_delete))}.",
            processing_mode="native",
        )

    def add_text_watermark(self, pdf_path: Path, output_stem: str, *, watermark_text: str) -> ProcessingResult:
        normalized_text = watermark_text.strip()
        if not normalized_text:
            raise ProcessingUserError("Il watermark testuale non può essere vuoto.")
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        document = self._open_pdf_document(pdf_path)
        try:
            for page in document:
                width = float(page.rect.width)
                height = float(page.rect.height)
                font_size = max(18, min(42, int(min(width, height) * 0.06)))
                rect = fitz.Rect(width * 0.08, height * 0.42, width * 0.92, height * 0.58)
                page.insert_textbox(
                    rect,
                    normalized_text,
                    fontsize=font_size,
                    fontname="helv",
                    color=(0.55, 0.55, 0.55),
                    rotate=0,
                    align=fitz.TEXT_ALIGN_CENTER,
                    overlay=True,
                )
            document.save(output_path, garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True)
        finally:
            document.close()
        return ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f'PDF pronto. Ho aggiunto il watermark testuale "{normalized_text}" al PDF.',
            processing_mode="native",
        )

    def _prepare_pdf_inputs_for_processing(self, pdf_paths: list[Path]) -> tuple[list[Path], int]:
        prepared_paths: list[Path] = []
        rotated_pages = 0
        for index, pdf_path in enumerate(pdf_paths, start=1):
            prepared_path, rotated_for_file = self._prepare_single_pdf_for_processing(
                pdf_path,
                suffix=f"_autorotate_{index}",
            )
            prepared_paths.append(prepared_path)
            rotated_pages += rotated_for_file
        return prepared_paths, rotated_pages

    def _prepare_single_pdf_for_processing(self, pdf_path: Path, suffix: str = "_autorotate") -> tuple[Path, int]:
        output_path = pdf_path.with_name(f"{pdf_path.stem}{suffix}{pdf_path.suffix}")
        rotated_pages = self._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)
        if rotated_pages == 0:
            try:
                output_path.unlink(missing_ok=True)
            except TypeError:
                if output_path.exists():
                    output_path.unlink()
            return pdf_path, 0
        return output_path, rotated_pages

    def _auto_rotate_pdf_to_dominant_orientation(self, pdf_path: Path, output_path: Path) -> int:
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise ProcessingUserError(
                    "Questo PDF sembra protetto da password. "
                    "Per elaborarlo, invia prima una versione non protetta."
                )

            writer = PdfWriter()
            page_orientations = [self._get_displayed_page_orientation(page) for page in reader.pages]
            target_orientation = self._infer_target_page_orientation(page_orientations)
            if target_orientation is None:
                return 0

            rotated_pages = 0
            for page, page_orientation in zip(reader.pages, page_orientations):
                if page_orientation not in {"portrait", "landscape"}:
                    writer.add_page(page)
                    continue
                if page_orientation != target_orientation:
                    page.rotate(90)
                    rotated_pages += 1
                writer.add_page(page)
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise ProcessingUserError(
                "Non riesco a leggere questo PDF. "
                "Potrebbe essere corrotto o protetto da password."
            ) from exc

        if rotated_pages == 0:
            return 0

        with output_path.open("wb") as handle:
            writer.write(handle)
        return rotated_pages

    def _get_displayed_page_orientation(self, page) -> str:
        current_rotation = int(page.rotation or 0) % 360
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        displayed_width = height if current_rotation in {90, 270} else width
        displayed_height = width if current_rotation in {90, 270} else height
        if displayed_width > displayed_height:
            return "landscape"
        if displayed_height > displayed_width:
            return "portrait"
        return "square"

    def _infer_target_page_orientation(self, page_orientations: list[str]) -> str | None:
        portrait_pages = sum(1 for orientation in page_orientations if orientation == "portrait")
        landscape_pages = sum(1 for orientation in page_orientations if orientation == "landscape")
        if portrait_pages == landscape_pages:
            return None
        return "portrait" if portrait_pages > landscape_pages else "landscape"

    def auto_orient_images(self, image_paths: list[Path], output_stem: str) -> ProcessingResult:
        if not image_paths:
            raise ProcessingUserError("Non ho ricevuto immagini da correggere.")
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
                processing_mode="native",
            )

        archive_path = image_paths[0].parent.parent / f"{output_stem}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in corrected_paths:
                archive.write(path, arcname=path.name)

        return ProcessingResult(
            output_path=archive_path,
            output_name=archive_path.name,
            message="Ho corretto l'orientamento delle immagini e creato un archivio ZIP.",
            processing_mode="native",
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
        except (RuntimeError, ValueError, OSError):
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
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.ghostscript_timeout_seconds,
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
            ghostscript=ghostscript,
            pdf_path=pdf_path,
            output_path=output_path,
            quality_profile=quality_profile,
        )
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.ghostscript_timeout_seconds,
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
        except (RuntimeError, ValueError, OSError):
            logger.exception("Conversione nativa in scala di grigi non riuscita, usero un fallback.")
            return False
        finally:
            document.close()

    def _subset_fonts_if_possible(self, document: fitz.Document) -> None:
        subset_fonts = getattr(document, "subset_fonts", None)
        if callable(subset_fonts):
            try:
                subset_fonts()
            except (RuntimeError, ValueError, OSError):
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

    def _build_pdf_reader(self, pdf_path: Path) -> PdfReader:
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise ProcessingUserError(
                    "Questo PDF sembra protetto da password. "
                    "Per elaborarlo, invia prima una versione non protetta."
                )
            return reader
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise ProcessingUserError(
                "Non riesco a leggere questo PDF. "
                "Potrebbe essere corrotto o protetto da password."
            ) from exc

    def _parse_page_selection(self, raw_value: str, pdf_path: Path, *, mode: str) -> list[int]:
        reader = self._build_pdf_reader(pdf_path)
        total_pages = len(reader.pages)
        value = re.sub(r"(?<=\d)\s+(?=\d)", ",", raw_value.strip())
        value = re.sub(r"\s*,\s*", ",", value)
        if not value:
            raise ProcessingUserError("Non ho ricevuto nessuna selezione pagine. Usa un formato come 1,3,5-7.")

        page_numbers: list[int] = []
        for raw_token in value.split(","):
            token = raw_token.strip()
            if not token:
                raise ProcessingUserError("La selezione pagine contiene una virgola vuota. Usa un formato come 1,3,5-7.")
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                if not start_text.strip().isdigit() or not end_text.strip().isdigit():
                    raise ProcessingUserError("Gli intervalli pagina devono essere numerici, ad esempio 2-5.")
                start = int(start_text.strip())
                end = int(end_text.strip())
                if start <= 0 or end <= 0 or start > end:
                    raise ProcessingUserError("Gli intervalli pagina devono essere validi, ad esempio 2-5.")
                page_numbers.extend(range(start, end + 1))
            else:
                if not token.isdigit():
                    raise ProcessingUserError("La selezione pagine deve usare solo numeri e intervalli, ad esempio 1,3,5-7.")
                page_numbers.append(int(token))

        if any(page_number < 1 or page_number > total_pages for page_number in page_numbers):
            raise ProcessingUserError(f"Questo PDF ha {total_pages} pagine. Controlla la selezione e riprova.")

        if mode == "full_reorder":
            if len(page_numbers) != total_pages or len(set(page_numbers)) != total_pages:
                raise ProcessingUserError(
                    f"Per riordinare le pagine di un PDF da {total_pages} pagine devo ricevere ogni pagina una sola volta."
                )

        return page_numbers

    def _format_page_numbers(self, page_numbers: list[int]) -> str:
        if not page_numbers:
            return ""
        if len(page_numbers) == 1:
            return str(page_numbers[0])
        return ", ".join(str(number) for number in page_numbers)

    def _build_images_to_pdf_message(
        self,
        *,
        auto_crop: bool,
        grayscale_output: bool,
        use_a4_layout: bool,
        a4_margin_px: int,
    ) -> str:
        crop_prefix = "dopo il ritaglio automatico dei bordi delle immagini, " if auto_crop else ""
        grayscale_prefix = "in scala di grigi " if grayscale_output else ""
        if not use_a4_layout:
            return f"PDF creato con successo {crop_prefix}{grayscale_prefix}mantenendo il formato originale delle immagini."
        margin_label = self._describe_a4_margin(a4_margin_px)
        return f"PDF creato con successo {crop_prefix}{grayscale_prefix}in formato A4 con {margin_label}."

    def _describe_a4_margin(self, margin_px: int) -> str:
        if margin_px >= A4_MARGIN_WIDE_PX:
            return "bordi larghi"
        if margin_px <= A4_MARGIN_NONE_PX:
            return "nessun bordo"
        return "bordi stretti"

    def _build_a4_page(self, image: Image.Image, *, margin_px: int) -> Image.Image:
        page_mode = "L" if image.mode == "L" else "RGB"
        page_background = 255 if page_mode == "L" else "white"
        page = Image.new(page_mode, (A4_WIDTH_PX, A4_HEIGHT_PX), page_background)
        safe_margin_px = max(0, min(margin_px, min(A4_WIDTH_PX, A4_HEIGHT_PX) // 2 - 1))
        available_width = max(1, A4_WIDTH_PX - (2 * safe_margin_px))
        available_height = max(1, A4_HEIGHT_PX - (2 * safe_margin_px))

        content = image.copy()
        content.thumbnail((available_width, available_height), Image.Resampling.LANCZOS)

        offset_x = (A4_WIDTH_PX - content.width) // 2
        offset_y = (A4_HEIGHT_PX - content.height) // 2
        page.paste(content, (offset_x, offset_y))
        content.close()
        return page

    def _auto_crop_scan_borders(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        if width < 40 or height < 40:
            return image.copy()

        background = self._estimate_background_color(image)
        diff = ImageChops.difference(image, Image.new("RGB", image.size, background))
        grayscale = diff.convert("L")
        bbox = grayscale.point(lambda value: 255 if value > 18 else 0).getbbox()
        if bbox is None:
            return image.copy()

        left, top, right, bottom = bbox
        if (right - left) >= width - 8 and (bottom - top) >= height - 8:
            return image.copy()

        padding = max(6, min(width, height) // 100)
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(width, right + padding)
        bottom = min(height, bottom + padding)

        if right - left < width * 0.35 or bottom - top < height * 0.35:
            return image.copy()

        return image.crop((left, top, right, bottom))

    def _estimate_background_color(self, image: Image.Image) -> tuple[int, int, int]:
        width, height = image.size
        patch_size = max(4, min(width, height) // 20)
        patches = [
            image.crop((0, 0, patch_size, patch_size)),
            image.crop((width - patch_size, 0, width, patch_size)),
            image.crop((0, height - patch_size, patch_size, height)),
            image.crop((width - patch_size, height - patch_size, width, height)),
        ]
        channels = [0, 0, 0]
        for patch in patches:
            red, green, blue = patch.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
            channels[0] += int(red)
            channels[1] += int(green)
            channels[2] += int(blue)
        return tuple(channel // len(patches) for channel in channels)
