from __future__ import annotations

from pathlib import Path

from docmolder.document_photo_processing import DocumentPhotoProcessor
from docmolder.excel_processing import ExcelProcessor
from docmolder.ghostscript_processing import GhostscriptProcessor
from docmolder.image_processing import ImageProcessor
from docmolder.job_files import cleanup_job_dir, cleanup_stale_job_dirs, create_job_dir
from docmolder.models import CompressionPreset, DocumentPhotoMode, SupportedAction
from docmolder.pdf_processing import PdfProcessor
from docmolder.processing_models import (
    A4_MARGIN_NARROW_PX,
    IMAGE_PDF_DEFAULT_MAX_SOURCE_SIDE,
    ProcessingResult,
)


_IMAGE_PDF_ACTION_OPTIONS: dict[SupportedAction, tuple[bool, bool]] = {
    SupportedAction.IMAGES_TO_PDF: (False, False),
    SupportedAction.IMAGES_TO_PDF_CROP: (True, False),
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE: (False, True),
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: (True, True),
}


class DocumentProcessor:
    """Coordinatore sottile delle capacità documentali."""

    def __init__(
        self,
        runtime_dir: Path,
        ghostscript_timeout_seconds: int = 120,
        image_pdf_max_source_side_px: int = IMAGE_PDF_DEFAULT_MAX_SOURCE_SIDE,
        libreoffice_timeout_seconds: int = 120,
    ) -> None:
        self.runtime_dir = runtime_dir
        self.images = ImageProcessor(image_pdf_max_source_side_px)
        self.ghostscript = GhostscriptProcessor(ghostscript_timeout_seconds)
        self.pdf = PdfProcessor(self.images, self.ghostscript)
        self.document_photos = DocumentPhotoProcessor(self.images)
        self.excel = ExcelProcessor(runtime_dir, libreoffice_timeout_seconds)

    def create_job_dir(self, user_id: int) -> Path:
        return create_job_dir(self.runtime_dir, user_id)

    def cleanup_job_dir(self, job_dir: Path) -> None:
        cleanup_job_dir(job_dir)

    def cleanup_stale_job_dirs(self, max_age_hours: int) -> int:
        return cleanup_stale_job_dirs(self.runtime_dir, max_age_hours)

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
        split_output_zip: bool = True,
        document_photo_mode: DocumentPhotoMode = DocumentPhotoMode.READABLE,
    ) -> ProcessingResult:
        if action in _IMAGE_PDF_ACTION_OPTIONS:
            auto_crop, grayscale_output = _IMAGE_PDF_ACTION_OPTIONS[action]
            return self.images.images_to_pdf(
                input_paths,
                output_stem,
                auto_crop=auto_crop,
                grayscale_output=grayscale_output,
                use_a4_layout=image_pdf_use_a4,
                a4_margin_px=image_pdf_margin_px,
            )
        if action == SupportedAction.DOCUMENT_PHOTO_FIX:
            return self.document_photos.document_photos_to_pdf(
                input_paths,
                output_stem,
                mode=document_photo_mode,
            )
        if action == SupportedAction.PDF_MERGE:
            return self.pdf.merge_pdfs(input_paths, output_stem, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_SPLIT:
            return self.pdf.split_pdf_pages(input_paths[0], output_stem, output_as_zip=split_output_zip)
        if action == SupportedAction.PDF_GRAYSCALE:
            return self.pdf.pdf_to_grayscale(input_paths[0], output_stem, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_CROP:
            return self.pdf.crop_pdf_borders(input_paths[0], output_stem, auto_rotate_pdf=auto_rotate_pdf)
        if action == SupportedAction.PDF_COMPRESS:
            if compression_preset is None:
                raise ValueError("Livello di compressione mancante.")
            return self.pdf.compress_pdf(
                input_paths[0],
                output_stem,
                compression_preset,
                auto_rotate_pdf=auto_rotate_pdf,
            )
        if action == SupportedAction.PDF_ROTATE:
            if rotate_degrees is None:
                raise ValueError("Rotazione mancante.")
            return self.pdf.rotate_pdf(input_paths[0], output_stem, rotate_degrees)
        if action == SupportedAction.PDF_EXTRACT_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.pdf.extract_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_REORDER_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.pdf.reorder_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_DELETE_PAGES:
            if page_selection is None:
                raise ValueError("Selezione pagine mancante.")
            return self.pdf.delete_pdf_pages(input_paths[0], output_stem, page_selection=page_selection)
        if action == SupportedAction.PDF_WATERMARK:
            if watermark_text is None:
                raise ValueError("Testo watermark mancante.")
            return self.pdf.add_text_watermark(input_paths[0], output_stem, watermark_text=watermark_text)
        if action == SupportedAction.EXCEL_UNLOCK_EDITING:
            return self.excel.unlock_editing(input_paths[0], output_stem)
        if action == SupportedAction.AUTO_ORIENT:
            return self.images.auto_orient_images(input_paths, output_stem)
        raise ValueError(f"Azione non supportata: {action}")
