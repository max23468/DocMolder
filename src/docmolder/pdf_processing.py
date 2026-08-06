from __future__ import annotations
import logging
import math
import re
import zipfile
from io import BytesIO
from pathlib import Path
import fitz
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError, PdfReadError
from docmolder.models import CompressionPreset
import docmolder.processing_models as processing_models

logger = logging.getLogger(__name__)


class PdfProcessor:
    def __init__(self, images, ghostscript):
        self.images = images
        self.ghostscript = ghostscript

    def merge_pdfs(
        self, pdf_paths: list[Path], output_stem: str, auto_rotate_pdf: bool = True
    ) -> processing_models.ProcessingResult:
        if len(pdf_paths) < 2:
            raise processing_models.ProcessingUserError("Per unire i PDF devo riceverne almeno due.")
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
            raise processing_models.ProcessingUserError(
                "Non riesco a unire uno dei PDF ricevuti. Controlla che i file non siano protetti da password e riprova."
            ) from exc
        with output_path.open("wb") as handle:
            writer.write(handle)
        message = "PDF pronto. Ho unito i file in un unico documento."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode="native",
        )

    def split_pdf_pages(
        self, pdf_path: Path, output_stem: str, *, output_as_zip: bool = True
    ) -> processing_models.ProcessingResult:
        reader = self._build_pdf_reader(pdf_path)
        total_pages = len(reader.pages)
        if total_pages < 2:
            raise processing_models.ProcessingUserError(
                "Questo PDF ha una sola pagina: non ci sono pagine da dividere in più file."
            )
        if total_pages > processing_models.PDF_SPLIT_MAX_PAGES:
            raise processing_models.ProcessingUserError(
                f"Questo PDF ha {total_pages} pagine. La divisione supporta al massimo {processing_models.PDF_SPLIT_MAX_PAGES} pagine per job."
            )
        pages_dir = pdf_path.parent / f"{output_stem}_pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        page_paths: list[Path] = []
        page_digits = max(2, len(str(total_pages)))
        for index, page in enumerate(reader.pages, start=1):
            page_writer = PdfWriter()
            page_writer.add_page(page)
            page_path = pages_dir / f"{output_stem}_pagina_{index:0{page_digits}d}.pdf"
            with page_path.open("wb") as handle:
                page_writer.write(handle)
            page_paths.append(page_path)
        if not output_as_zip:
            first_path, *additional_paths = page_paths
            return processing_models.ProcessingResult(
                output_path=first_path,
                output_name=first_path.name,
                message=f"PDF pronto. Ho diviso il documento in {total_pages} file e te li invio come PDF separati.",
                processing_mode="native",
                additional_outputs=[
                    processing_models.ProcessingOutput(path=page_path, name=page_path.name)
                    for page_path in additional_paths
                ],
            )
        archive_path = pdf_path.parent.parent / f"{output_stem}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for page_path in page_paths:
                archive.write(page_path, arcname=page_path.name)
        return processing_models.ProcessingResult(
            output_path=archive_path,
            output_name=archive_path.name,
            message=f"PDF pronto. Ho diviso il documento in {total_pages} file, uno per pagina, raccolti in un archivio ZIP.",
            processing_mode="native",
        )

    def pdf_to_grayscale(
        self, pdf_path: Path, output_stem: str, auto_rotate_pdf: bool = True
    ) -> processing_models.ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        prepared_path = pdf_path
        rotated_pages = 0
        if auto_rotate_pdf:
            prepared_path, rotated_pages = self._prepare_single_pdf_for_processing(pdf_path)
        self._validate_pdf_for_processing(pdf_path)
        conversion_mode = (
            "ghostscript" if self.ghostscript._run_ghostscript_grayscale(prepared_path, output_path) else None
        )
        if conversion_mode is None and self._convert_pdf_images_to_grayscale_native(prepared_path, output_path):
            conversion_mode = "native"
        if conversion_mode is None:
            self._render_pdf_as_images(
                pdf_path=prepared_path, output_path=output_path, dpi=150, colorspace=fitz.csGRAY, image_format="png"
            )
            conversion_mode = "raster"
        message = "PDF pronto in scala di grigi."
        if conversion_mode == "native":
            message += (
                " Ho convertito soprattutto le immagini interne e preservato la struttura del PDF dove possibile."
            )
        elif conversion_mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per garantire compatibilità. Il risultato potrebbe non mantenere testo ricercabile o struttura interna del PDF."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode=conversion_mode,
        )

    def compress_pdf(
        self, pdf_path: Path, output_stem: str, preset: CompressionPreset, auto_rotate_pdf: bool = True
    ) -> processing_models.ProcessingResult:
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
                prepared_path, output_path, image_quality=70, image_dpi_threshold=150, image_dpi_target=135
            ):
                if self.ghostscript._run_ghostscript_compress(prepared_path, output_path, quality_profile="/ebook"):
                    mode = "ghostscript"
                else:
                    self._compress_pdf_lossless(prepared_path, output_path)
                    mode = "lossless"
            else:
                mode = "conservative"
        elif not self._compress_pdf_conservative(
            prepared_path, output_path, image_quality=50, image_dpi_threshold=110, image_dpi_target=95
        ):
            if self.ghostscript._run_ghostscript_compress(prepared_path, output_path, quality_profile="/screen"):
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
        message += self._build_compression_feedback(pdf_path, output_path)
        if mode == "ghostscript":
            message += " Ho mantenuto il PDF nativo con una compressione più fedele."
        elif mode == "raster":
            message += " Ho usato una soluzione visiva di ripiego per i casi più difficili. Il risultato finale potrebbe non mantenere pienamente testo ricercabile o struttura interna del PDF."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode=mode,
        )

    def crop_pdf_borders(
        self, pdf_path: Path, output_stem: str, auto_rotate_pdf: bool = True
    ) -> processing_models.ProcessingResult:
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        prepared_path = pdf_path
        rotated_pages = 0
        if auto_rotate_pdf:
            prepared_path, rotated_pages = self._prepare_single_pdf_for_processing(pdf_path)
        self._validate_pdf_for_processing(pdf_path)
        cropped_pages = self._crop_pdf_uniform_borders(prepared_path, output_path)
        if cropped_pages:
            message = f"PDF pronto. Ho tagliato i bordi uniformi su {cropped_pages} pagine."
        else:
            message = "PDF pronto. Non ho trovato bordi uniformi abbastanza chiari da tagliare."
        if rotated_pages:
            message += f" Ho anche corretto automaticamente l'orientamento di {rotated_pages} pagine."
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            auto_rotation_applied=rotated_pages > 0,
            processing_mode="native",
        )

    def rotate_pdf(self, pdf_path: Path, output_stem: str, rotate_degrees: int) -> processing_models.ProcessingResult:
        if rotate_degrees not in {90, 180, 270}:
            raise processing_models.ProcessingUserError("Per la rotazione manuale puoi usare solo 90, 180 o 270 gradi.")
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        try:
            reader = self._build_pdf_reader(pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                page.rotate(rotate_degrees)
                writer.add_page(page)
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise processing_models.ProcessingUserError(
                "Non riesco a leggere questo PDF per ruotarlo. Potrebbe essere corrotto o protetto da password."
            ) from exc
        with output_path.open("wb") as handle:
            writer.write(handle)
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho ruotato le pagine di {rotate_degrees} gradi.",
            processing_mode="native",
        )

    def extract_pdf_pages(
        self, pdf_path: Path, output_stem: str, *, page_selection: str
    ) -> processing_models.ProcessingResult:
        page_numbers = self._parse_page_selection(page_selection, pdf_path, mode="subset")
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        reader = self._build_pdf_reader(pdf_path)
        writer = PdfWriter()
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho estratto le pagine {self._format_page_numbers(page_numbers)}.",
            processing_mode="native",
        )

    def reorder_pdf_pages(
        self, pdf_path: Path, output_stem: str, *, page_selection: str
    ) -> processing_models.ProcessingResult:
        reader = self._build_pdf_reader(pdf_path)
        page_numbers = self._parse_page_selection(page_selection, pdf_path, mode="full_reorder")
        if len(page_numbers) != len(reader.pages):
            raise processing_models.ProcessingUserError(
                "Per riordinare le pagine devo ricevere l'ordine completo del PDF, ad esempio 3,1,2 per un PDF di 3 pagine."
            )
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        for page_number in page_numbers:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho riordinato le pagine nel nuovo ordine {self._format_page_numbers(page_numbers)}.",
            processing_mode="native",
        )

    def delete_pdf_pages(
        self, pdf_path: Path, output_stem: str, *, page_selection: str
    ) -> processing_models.ProcessingResult:
        reader = self._build_pdf_reader(pdf_path)
        to_delete = set(self._parse_page_selection(page_selection, pdf_path, mode="subset"))
        remaining_pages = [index + 1 for index in range(len(reader.pages)) if index + 1 not in to_delete]
        if not remaining_pages:
            raise processing_models.ProcessingUserError(
                "Non posso eliminare tutte le pagine del PDF. Deve restarne almeno una."
            )
        output_path = pdf_path.parent.parent / f"{output_stem}.pdf"
        writer = PdfWriter()
        for page_number in remaining_pages:
            writer.add_page(reader.pages[page_number - 1])
        with output_path.open("wb") as handle:
            writer.write(handle)
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=f"PDF pronto. Ho eliminato le pagine {self._format_page_numbers(sorted(to_delete))}.",
            processing_mode="native",
        )

    def add_text_watermark(
        self, pdf_path: Path, output_stem: str, *, watermark_text: str
    ) -> processing_models.ProcessingResult:
        normalized_text = watermark_text.strip()
        if not normalized_text:
            raise processing_models.ProcessingUserError("Il watermark testuale non può essere vuoto.")
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
        return processing_models.ProcessingResult(
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
                pdf_path, suffix=f"_autorotate_{index}"
            )
            prepared_paths.append(prepared_path)
            rotated_pages += rotated_for_file
        return (prepared_paths, rotated_pages)

    def _prepare_single_pdf_for_processing(self, pdf_path: Path, suffix: str = "_autorotate") -> tuple[Path, int]:
        output_path = pdf_path.with_name(f"{pdf_path.stem}{suffix}{pdf_path.suffix}")
        rotated_pages = self._auto_rotate_pdf_to_dominant_orientation(pdf_path, output_path)
        if rotated_pages == 0:
            output_path.unlink(missing_ok=True)
            return (pdf_path, 0)
        return (output_path, rotated_pages)

    def _auto_rotate_pdf_to_dominant_orientation(self, pdf_path: Path, output_path: Path) -> int:
        try:
            reader = self._build_pdf_reader(pdf_path)
            writer = PdfWriter()
            page_orientations = [self._get_displayed_page_orientation(page) for page in reader.pages]
            target_orientation = self._infer_target_page_orientation(page_orientations)
            if target_orientation is None:
                return 0
            rotated_pages = 0
            for page, page_orientation in zip(reader.pages, page_orientations, strict=True):
                if page_orientation not in {"portrait", "landscape"}:
                    writer.add_page(page)
                    continue
                if page_orientation != target_orientation:
                    page.rotate(90)
                    rotated_pages += 1
                writer.add_page(page)
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise processing_models.ProcessingUserError(
                "Non riesco a leggere questo PDF. Potrebbe essere corrotto o protetto da password."
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
        portrait_pages = sum((1 for orientation in page_orientations if orientation == "portrait"))
        landscape_pages = sum((1 for orientation in page_orientations if orientation == "landscape"))
        if portrait_pages == landscape_pages:
            return None
        return "portrait" if portrait_pages > landscape_pages else "landscape"

    def _render_pdf_as_images(
        self,
        pdf_path: Path,
        output_path: Path,
        dpi: int,
        colorspace: fitz.Colorspace,
        image_format: str,
        jpeg_quality: int | None = None,
    ) -> None:
        source = self._open_pdf_document(pdf_path)
        destination = fitz.open()
        try:
            for page in source:
                self._validate_pdf_raster_budget(page, dpi=dpi)
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

    def _crop_pdf_uniform_borders(self, pdf_path: Path, output_path: Path) -> int:
        document = self._open_pdf_document(pdf_path)
        cropped_pages = 0
        try:
            for page in document:
                crop_rect = self._detect_pdf_page_content_rect(page)
                if crop_rect is None:
                    continue
                page.set_cropbox(crop_rect)
                cropped_pages += 1
            document.save(output_path, garbage=4, clean=True, deflate=True, use_objstms=1)
            return cropped_pages
        finally:
            document.close()

    def _normalize_pdf_cropbox_rect(self, page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
        if page.rotation:
            rect = rect * page.derotation_matrix
        bounds = page.cropbox if not page.cropbox.is_empty else page.mediabox
        rect = fitz.Rect(
            max(bounds.x0, rect.x0), max(bounds.y0, rect.y0), min(bounds.x1, rect.x1), min(bounds.y1, rect.y1)
        )
        return rect

    def _detect_pdf_page_content_rect(self, page: fitz.Page) -> fitz.Rect | None:
        page_rect = page.rect
        if page_rect.width < 40 or page_rect.height < 40:
            return None
        zoom = 2
        self._validate_pdf_raster_budget(page, dpi=72 * zoom)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        try:
            background = self.images._estimate_background_color(image)
            diff = ImageChops.difference(image, Image.new("RGB", image.size, background))
            bbox = diff.convert("L").point(lambda value: 255 if value > 18 else 0).getbbox()
        finally:
            image.close()
        if bbox is None:
            return None
        left, top, right, bottom = bbox
        if right - left >= pixmap.width - 8 and bottom - top >= pixmap.height - 8:
            return None
        padding = max(4, min(pixmap.width, pixmap.height) // 150)
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(pixmap.width, right + padding)
        bottom = min(pixmap.height, bottom + padding)
        new_rect = fitz.Rect(
            page_rect.x0 + left / pixmap.width * page_rect.width,
            page_rect.y0 + top / pixmap.height * page_rect.height,
            page_rect.x0 + right / pixmap.width * page_rect.width,
            page_rect.y0 + bottom / pixmap.height * page_rect.height,
        )
        image_rect = self._detect_pdf_image_content_rect(page)
        if image_rect is not None:
            new_rect.include_rect(image_rect)
        new_rect = fitz.Rect(
            max(page_rect.x0, new_rect.x0),
            max(page_rect.y0, new_rect.y0),
            min(page_rect.x1, new_rect.x1),
            min(page_rect.y1, new_rect.y1),
        )
        if new_rect.width < page_rect.width * 0.35 or new_rect.height < page_rect.height * 0.35:
            return None
        if new_rect.width >= page_rect.width - 2 and new_rect.height >= page_rect.height - 2:
            return None
        return self._normalize_pdf_cropbox_rect(page, new_rect)

    def _detect_pdf_image_content_rect(self, page: fitz.Page) -> fitz.Rect | None:
        content_rect: fitz.Rect | None = None
        for image_info in page.get_image_info():
            bbox = image_info.get("bbox")
            if bbox is None:
                continue
            image_rect = fitz.Rect(bbox)
            if image_rect.is_empty or image_rect.width < 2 or image_rect.height < 2:
                continue
            if content_rect is None:
                content_rect = image_rect
            else:
                content_rect.include_rect(image_rect)
        return content_rect

    def _compress_pdf_lossless(self, pdf_path: Path, output_path: Path) -> None:
        document = self._open_pdf_document(pdf_path)
        try:
            self._subset_fonts_if_possible(document)
            document.save(
                output_path, garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True, use_objstms=1
            )
        finally:
            document.close()

    def _compress_pdf_conservative(
        self, pdf_path: Path, output_path: Path, image_quality: int, image_dpi_threshold: int, image_dpi_target: int
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
                output_path, garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True, use_objstms=1
            )
            return True
        except (RuntimeError, ValueError, OSError):
            logger.exception("Compressione conservativa non riuscita, userò un fallback.")
            return False
        finally:
            document.close()

    def _build_compression_feedback(self, input_path: Path, output_path: Path) -> str:
        try:
            input_bytes = input_path.stat().st_size
            output_bytes = output_path.stat().st_size
        except OSError:
            return ""
        if input_bytes <= 0 or output_bytes <= 0:
            return ""
        if output_bytes >= input_bytes:
            return " Il PDF sembra già ottimizzato: questo passaggio non lo rende più leggero dell'originale."
        reduction_percent = round((1 - output_bytes / input_bytes) * 100)
        if reduction_percent < 5:
            return " La riduzione è minima: il PDF era già abbastanza ottimizzato."
        return f" Riduzione stimata: circa {reduction_percent}%."

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
                output_path, garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True, use_objstms=1
            )
            return True
        except (RuntimeError, ValueError, OSError):
            logger.exception("Conversione nativa in scala di grigi non riuscita, userò un fallback.")
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
            raise processing_models.ProcessingUserError(
                "Non riesco a leggere questo PDF. Potrebbe essere corrotto, vuoto o non compatibile."
            ) from exc
        needs_pass = getattr(document, "needs_pass", False)
        if needs_pass:
            document.close()
            raise processing_models.ProcessingUserError(
                "Questo PDF sembra protetto da password. Per elaborarlo, invia prima una versione non protetta."
            )
        if document.page_count > processing_models.PDF_MAX_PAGES:
            document.close()
            raise processing_models.ProcessingUserError(
                f"Questo PDF ha più di {processing_models.PDF_MAX_PAGES} pagine, oltre il budget massimo per un singolo job."
            )
        return document

    def _build_pdf_reader(self, pdf_path: Path) -> PdfReader:
        try:
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted:
                raise processing_models.ProcessingUserError(
                    "Questo PDF sembra protetto da password. Per elaborarlo, invia prima una versione non protetta."
                )
            if len(reader.pages) > processing_models.PDF_MAX_PAGES:
                raise processing_models.ProcessingUserError(
                    f"Questo PDF ha più di {processing_models.PDF_MAX_PAGES} pagine, oltre il budget massimo per un singolo job."
                )
            return reader
        except (PdfReadError, FileNotDecryptedError) as exc:
            raise processing_models.ProcessingUserError(
                "Non riesco a leggere questo PDF. Potrebbe essere corrotto o protetto da password."
            ) from exc

    def _parse_page_selection(self, raw_value: str, pdf_path: Path, *, mode: str) -> list[int]:
        reader = self._build_pdf_reader(pdf_path)
        total_pages = len(reader.pages)
        value = re.sub("(?<=\\d)\\s+(?=\\d)", ",", raw_value.strip())
        value = re.sub("\\s*,\\s*", ",", value)
        if not value:
            raise processing_models.ProcessingUserError(
                "Non ho ricevuto nessuna selezione pagine. Usa un formato come 1,3,5-7."
            )
        page_numbers: list[int] = []
        for raw_token in value.split(","):
            token = raw_token.strip()
            if not token:
                raise processing_models.ProcessingUserError(
                    "La selezione pagine contiene una virgola vuota. Usa un formato come 1,3,5-7."
                )
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                if not start_text.strip().isdigit() or not end_text.strip().isdigit():
                    raise processing_models.ProcessingUserError(
                        "Gli intervalli pagina devono essere numerici, ad esempio 2-5."
                    )
                start = int(start_text.strip())
                end = int(end_text.strip())
                if start <= 0 or end <= 0 or start > end:
                    raise processing_models.ProcessingUserError(
                        "Gli intervalli pagina devono essere validi, ad esempio 2-5."
                    )
                if end > total_pages:
                    raise processing_models.ProcessingUserError(
                        f"Questo PDF ha {total_pages} pagine. Controlla la selezione e riprova."
                    )
                page_numbers.extend(range(start, end + 1))
            else:
                if not token.isdigit():
                    raise processing_models.ProcessingUserError(
                        "La selezione pagine deve usare solo numeri e intervalli, ad esempio 1,3,5-7."
                    )
                page_numbers.append(int(token))
        if any((page_number < 1 or page_number > total_pages for page_number in page_numbers)):
            raise processing_models.ProcessingUserError(
                f"Questo PDF ha {total_pages} pagine. Controlla la selezione e riprova."
            )
        if mode == "full_reorder":
            if len(page_numbers) != total_pages or len(set(page_numbers)) != total_pages:
                raise processing_models.ProcessingUserError(
                    f"Per riordinare le pagine di un PDF da {total_pages} pagine devo ricevere ogni pagina una sola volta."
                )
        return page_numbers

    def _validate_pdf_raster_budget(self, page: fitz.Page, *, dpi: float) -> None:
        width = page.rect.width * dpi / 72
        height = page.rect.height * dpi / 72
        if (
            not math.isfinite(width * height)
            or width <= 0
            or height <= 0
            or (width * height > processing_models.PDF_RASTER_MAX_PIXELS)
        ):
            raise processing_models.ProcessingUserError(
                "Una pagina del PDF è troppo grande per la conversione raster. Riduci il formato pagina e riprova."
            )

    def _format_page_numbers(self, page_numbers: list[int]) -> str:
        if not page_numbers:
            return ""
        if len(page_numbers) == 1:
            return str(page_numbers[0])
        return ", ".join((str(number) for number in page_numbers))
