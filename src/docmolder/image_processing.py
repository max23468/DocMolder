from __future__ import annotations
import logging
import zipfile
from pathlib import Path
from PIL import Image, ImageChops, ImageOps
from pypdf import PdfWriter
import docmolder.processing_models as processing_models

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self, image_pdf_max_source_side_px: int):
        self.image_pdf_max_source_side_px = max(800, image_pdf_max_source_side_px)

    def images_to_pdf(
        self,
        image_paths: list[Path],
        output_stem: str,
        auto_crop: bool = False,
        *,
        grayscale_output: bool = False,
        use_a4_layout: bool = True,
        a4_margin_px: int = processing_models.A4_MARGIN_NARROW_PX,
    ) -> processing_models.ProcessingResult:
        if not image_paths:
            raise processing_models.ProcessingUserError("Non ho ricevuto immagini da convertire in PDF.")
        output_path = image_paths[0].parent.parent / f"{output_stem}.pdf"
        page_pdf_paths: list[Path] = []
        downscaled_images = 0
        for index, image_path in enumerate(image_paths, start=1):
            page_pdf_path = output_path.parent / f".{output_stem}_page_{index:04d}.pdf"
            with self._open_image(image_path) as image:
                corrected, was_downscaled = self._prepare_image_for_pdf(
                    image, grayscale_output=grayscale_output, auto_crop=auto_crop
                )
                if was_downscaled:
                    downscaled_images += 1
                try:
                    if use_a4_layout:
                        page_image = self._build_a4_page(corrected, margin_px=a4_margin_px)
                    else:
                        page_image = corrected.copy()
                    try:
                        page_image.save(page_pdf_path, "PDF", resolution=150.0)
                    finally:
                        page_image.close()
                finally:
                    corrected.close()
            page_pdf_paths.append(page_pdf_path)
        if len(page_pdf_paths) == 1:
            page_pdf_paths[0].replace(output_path)
        else:
            writer = PdfWriter()
            for page_pdf_path in page_pdf_paths:
                writer.append(str(page_pdf_path))
            with output_path.open("wb") as handle:
                writer.write(handle)
        message = self._build_images_to_pdf_message(
            auto_crop=auto_crop,
            grayscale_output=grayscale_output,
            use_a4_layout=use_a4_layout,
            a4_margin_px=a4_margin_px,
            downscaled_images=downscaled_images,
        )
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=message,
            processing_mode="native" if grayscale_output else None,
        )

    def auto_orient_images(self, image_paths: list[Path], output_stem: str) -> processing_models.ProcessingResult:
        if not image_paths:
            raise processing_models.ProcessingUserError("Non ho ricevuto immagini da correggere.")
        corrected_paths: list[Path] = []
        for index, image_path in enumerate(image_paths, start=1):
            suffix = image_path.suffix.lower() or ".jpg"
            output_path = image_path.parent / f"{output_stem}_{index}{suffix}"
            with self._open_image(image_path) as image:
                corrected = ImageOps.exif_transpose(image)
                save_image = corrected
                if suffix in {".jpg", ".jpeg"} and corrected.mode not in ("RGB", "L"):
                    save_image = corrected.convert("RGB")
                save_image.save(output_path)
            corrected_paths.append(output_path)
        if len(corrected_paths) == 1:
            single = corrected_paths[0]
            return processing_models.ProcessingResult(
                output_path=single,
                output_name=single.name,
                message="Ho corretto l'orientamento dell'immagine.",
                processing_mode="native",
            )
        archive_path = image_paths[0].parent.parent / f"{output_stem}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in corrected_paths:
                archive.write(path, arcname=path.name)
        return processing_models.ProcessingResult(
            output_path=archive_path,
            output_name=archive_path.name,
            message="Ho corretto l'orientamento delle immagini e creato un archivio ZIP.",
            processing_mode="native",
        )

    def _open_image(self, path: Path) -> Image.Image:
        image = Image.open(path)
        if image.width * image.height > processing_models.IMAGE_MAX_PIXELS:
            image.close()
            raise processing_models.ProcessingUserError(
                f"Questa immagine supera il budget di {processing_models.IMAGE_MAX_PIXELS:,} pixel. Riduci le dimensioni e riprova."
            )
        return image

    def _build_images_to_pdf_message(
        self,
        *,
        auto_crop: bool,
        grayscale_output: bool,
        use_a4_layout: bool,
        a4_margin_px: int,
        downscaled_images: int = 0,
    ) -> str:
        crop_prefix = "dopo il ritaglio automatico dei bordi delle immagini, " if auto_crop else ""
        grayscale_prefix = "in scala di grigi " if grayscale_output else ""
        downscale_note = ""
        if downscaled_images:
            image_label = (
                "1 immagine molto grande" if downscaled_images == 1 else f"{downscaled_images} immagini molto grandi"
            )
            downscale_note = f" Ho ridotto {image_label} prima della conversione."
        if not use_a4_layout:
            return f"PDF creato con successo {crop_prefix}{grayscale_prefix}mantenendo il formato originale delle immagini.{downscale_note}"
        margin_label = self._describe_a4_margin(a4_margin_px)
        return (
            f"PDF creato con successo {crop_prefix}{grayscale_prefix}in formato A4 con {margin_label}.{downscale_note}"
        )

    def _prepare_image_for_pdf(
        self, image: Image.Image, *, grayscale_output: bool, auto_crop: bool
    ) -> tuple[Image.Image, bool]:
        prepared = ImageOps.exif_transpose(image)
        if prepared is image:
            prepared = image.copy()
        else:
            prepared.load()
        was_downscaled = False
        max_side = max(prepared.size)
        if max_side > self.image_pdf_max_source_side_px:
            prepared.thumbnail(
                (self.image_pdf_max_source_side_px, self.image_pdf_max_source_side_px), Image.Resampling.LANCZOS
            )
            was_downscaled = True
        if grayscale_output and prepared.mode != "L":
            converted = ImageOps.grayscale(prepared)
            prepared.close()
            prepared = converted
        elif not grayscale_output and prepared.mode != "RGB":
            converted = prepared.convert("RGB")
            prepared.close()
            prepared = converted
        if auto_crop:
            cropped = self._auto_crop_scan_borders(prepared)
            prepared.close()
            prepared = cropped
        return (prepared, was_downscaled)

    def _describe_a4_margin(self, margin_px: int) -> str:
        if margin_px >= processing_models.A4_MARGIN_WIDE_PX:
            return "bordi larghi"
        if margin_px <= processing_models.A4_MARGIN_NONE_PX:
            return "nessun bordo"
        return "bordi stretti"

    def _build_a4_page(self, image: Image.Image, *, margin_px: int) -> Image.Image:
        page_mode = "L" if image.mode == "L" else "RGB"
        page_background = 255 if page_mode == "L" else "white"
        page = Image.new(page_mode, (processing_models.A4_WIDTH_PX, processing_models.A4_HEIGHT_PX), page_background)
        safe_margin_px = max(
            0, min(margin_px, min(processing_models.A4_WIDTH_PX, processing_models.A4_HEIGHT_PX) // 2 - 1)
        )
        available_width = max(1, processing_models.A4_WIDTH_PX - 2 * safe_margin_px)
        available_height = max(1, processing_models.A4_HEIGHT_PX - 2 * safe_margin_px)
        content = image.copy()
        content.thumbnail((available_width, available_height), Image.Resampling.LANCZOS)
        offset_x = (processing_models.A4_WIDTH_PX - content.width) // 2
        offset_y = (processing_models.A4_HEIGHT_PX - content.height) // 2
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
        if right - left >= width - 8 and bottom - top >= height - 8:
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
        return tuple((channel // len(patches) for channel in channels))
