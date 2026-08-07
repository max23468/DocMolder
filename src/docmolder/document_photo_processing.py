from __future__ import annotations
import logging
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
from docmolder.models import DocumentPhotoMode
import docmolder.processing_models as processing_models

logger = logging.getLogger(__name__)


class DocumentPhotoProcessor:
    def __init__(self, images):
        self.images = images

    def document_photos_to_pdf(
        self, image_paths: list[Path], output_stem: str, *, mode: DocumentPhotoMode = DocumentPhotoMode.READABLE
    ) -> processing_models.ProcessingResult:
        if not image_paths:
            raise processing_models.ProcessingUserError("Non ho ricevuto foto del documento da sistemare.")
        output_path = image_paths[0].parent.parent / f"{output_stem}.pdf"
        prepared_images: list[Image.Image] = []
        perspective_count = 0
        fallback_count = 0
        warnings: set[str] = set()
        try:
            for image_path in image_paths:
                with self.images._open_image(image_path) as image:
                    corrected = ImageOps.exif_transpose(image).convert("RGB")
                    transformed = self._transform_document_photo(corrected, mode=mode)
                    warnings.update(transformed.warnings)
                    if transformed.mode == "perspective":
                        perspective_count += 1
                    else:
                        fallback_count += 1
                    try:
                        prepared_images.append(
                            self.images._build_a4_page(
                                transformed.image, margin_px=processing_models.A4_MARGIN_NARROW_PX
                            )
                        )
                    finally:
                        transformed.image.close()
            first, *rest = prepared_images
            first.save(output_path, "PDF", save_all=True, append_images=rest, resolution=150.0)
        finally:
            for image in prepared_images:
                image.close()
        return processing_models.ProcessingResult(
            output_path=output_path,
            output_name=output_path.name,
            message=self._build_document_photos_to_pdf_message(
                total_images=len(image_paths),
                perspective_count=perspective_count,
                fallback_count=fallback_count,
                warnings=warnings,
                mode=mode,
            ),
            processing_mode="opencv" if perspective_count else "fallback",
        )

    def _transform_document_photo(
        self, image: Image.Image, *, mode: DocumentPhotoMode = DocumentPhotoMode.READABLE
    ) -> processing_models._DocumentPhotoTransform:
        warnings = self._detect_document_photo_quality_warnings(image)
        corners = self._detect_document_photo_corners(image)
        if corners is None:
            fallback_image = self.images._auto_crop_scan_borders(image)
            fallback_image = self._limit_document_photo_output_size(fallback_image)
            warnings.add("contorno_non_sicuro")
            return processing_models._DocumentPhotoTransform(
                image=self._add_document_photo_margin(self._enhance_document_photo(fallback_image, mode=mode)),
                mode="fallback",
                warnings=warnings,
            )
        if self._document_corners_touch_image_edge(corners, image.size):
            warnings.add("foglio_vicino_ai_bordi")
        warped = self._warp_document_photo(image, corners)
        return processing_models._DocumentPhotoTransform(
            image=self._add_document_photo_margin(self._enhance_document_photo(warped, mode=mode)),
            mode="perspective",
            warnings=warnings,
        )

    def _detect_document_photo_quality_warnings(self, image: Image.Image) -> set[str]:
        grayscale = np.asarray(ImageOps.grayscale(image))
        warnings: set[str] = set()
        mean_brightness = float(grayscale.mean())
        contrast = float(grayscale.std())
        blur_score = float(cv2.Laplacian(grayscale, cv2.CV_64F).var())
        if mean_brightness < 55:
            warnings.add("foto_scura")
        elif mean_brightness > 235:
            warnings.add("foto_molto_chiara")
        if contrast < 22:
            warnings.add("contrasto_basso")
        if blur_score < 18:
            warnings.add("foto_sfuocata")
        return warnings

    def _detect_document_photo_corners(self, image: Image.Image) -> np.ndarray | None:
        rgb = np.asarray(image)
        height, width = rgb.shape[:2]
        scale = min(1.0, processing_models.DOCUMENT_PHOTO_DETECTION_MAX_SIDE / max(width, height))
        if scale < 1.0:
            small = cv2.resize(rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        else:
            small = rgb
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        contour_inputs = [self._build_document_edge_mask(blurred), self._build_document_threshold_mask(blurred)]
        min_area = small.shape[0] * small.shape[1] * 0.12
        for mask in contour_inputs:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
                if cv2.contourArea(contour) < min_area:
                    continue
                perimeter = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
                if len(approx) != 4 or not cv2.isContourConvex(approx):
                    continue
                points = approx.reshape(4, 2).astype("float32") / scale
                if self._is_plausible_document_quad(points, image.size):
                    return points
        return None

    def _build_document_edge_mask(self, gray_image: np.ndarray) -> np.ndarray:
        normalized = cv2.equalizeHist(gray_image)
        edges = cv2.Canny(normalized, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        return cv2.dilate(edges, kernel, iterations=2)

    def _build_document_threshold_mask(self, gray_image: np.ndarray) -> np.ndarray:
        threshold = cv2.adaptiveThreshold(gray_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        return cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel, iterations=2)

    def _is_plausible_document_quad(self, points: np.ndarray, image_size: tuple[int, int]) -> bool:
        width, height = image_size
        area = float(cv2.contourArea(points.astype("float32")))
        image_area = float(width * height)
        if area < image_area * 0.12:
            return False
        ordered = self._order_document_points(points)
        top_width = np.linalg.norm(ordered[1] - ordered[0])
        bottom_width = np.linalg.norm(ordered[2] - ordered[3])
        left_height = np.linalg.norm(ordered[3] - ordered[0])
        right_height = np.linalg.norm(ordered[2] - ordered[1])
        max_width = max(top_width, bottom_width)
        max_height = max(left_height, right_height)
        if max_width < 80 or max_height < 80:
            return False
        ratio = max_width / max_height
        return 0.25 <= ratio <= 4.0

    def _document_corners_touch_image_edge(self, points: np.ndarray, image_size: tuple[int, int]) -> bool:
        width, height = image_size
        edge_margin = max(8, min(width, height) * 0.02)
        return bool(
            (points[:, 0] <= edge_margin).any()
            or (points[:, 1] <= edge_margin).any()
            or (points[:, 0] >= width - edge_margin).any()
            or (points[:, 1] >= height - edge_margin).any()
        )

    def _warp_document_photo(self, image: Image.Image, points: np.ndarray) -> Image.Image:
        ordered = self._order_document_points(points)
        width_a = np.linalg.norm(ordered[2] - ordered[3])
        width_b = np.linalg.norm(ordered[1] - ordered[0])
        height_a = np.linalg.norm(ordered[1] - ordered[2])
        height_b = np.linalg.norm(ordered[0] - ordered[3])
        target_width = max(1, int(max(width_a, width_b)))
        target_height = max(1, int(max(height_a, height_b)))
        scale = min(1.0, processing_models.DOCUMENT_PHOTO_OUTPUT_MAX_SIDE / max(target_width, target_height))
        target_width = max(1, int(target_width * scale))
        target_height = max(1, int(target_height * scale))
        destination = np.array(
            [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
            dtype="float32",
        )
        transform = cv2.getPerspectiveTransform(ordered.astype("float32"), destination)
        warped = cv2.warpPerspective(
            np.asarray(image),
            transform,
            (target_width, target_height),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        return Image.fromarray(warped)

    def _limit_document_photo_output_size(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        scale = min(1.0, processing_models.DOCUMENT_PHOTO_OUTPUT_MAX_SIDE / max(width, height))
        if scale >= 1.0:
            return image.copy()
        target_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return image.resize(target_size, Image.Resampling.LANCZOS)

    def _order_document_points(self, points: np.ndarray) -> np.ndarray:
        ordered = np.zeros((4, 2), dtype="float32")
        point_sum = points.sum(axis=1)
        ordered[0] = points[np.argmin(point_sum)]
        ordered[2] = points[np.argmax(point_sum)]
        point_diff = np.diff(points, axis=1)
        ordered[1] = points[np.argmin(point_diff)]
        ordered[3] = points[np.argmax(point_diff)]
        return ordered

    def _enhance_document_photo(
        self, image: Image.Image, *, mode: DocumentPhotoMode = DocumentPhotoMode.READABLE
    ) -> Image.Image:
        if mode == DocumentPhotoMode.COLOR:
            return self._enhance_document_photo_color(image)
        if mode == DocumentPhotoMode.BW:
            return self._enhance_document_photo_bw(image)
        gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        filtered = cv2.bilateralFilter(gray, 7, 25, 25)
        sigma = max(12, min(gray.shape[:2]) // 28)
        background = cv2.GaussianBlur(filtered, (0, 0), sigmaX=sigma, sigmaY=sigma)
        normalized = cv2.divide(filtered, background, scale=255)
        clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
        enhanced = clahe.apply(normalized)
        return ImageOps.autocontrast(Image.fromarray(enhanced), cutoff=1)

    def _enhance_document_photo_color(self, image: Image.Image) -> Image.Image:
        rgb = np.asarray(image.convert("RGB"))
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        lightness, channel_a, channel_b = cv2.split(lab)
        filtered = cv2.bilateralFilter(lightness, 7, 25, 25)
        clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
        enhanced_lightness = clahe.apply(filtered)
        enhanced_lab = cv2.merge((enhanced_lightness, channel_a, channel_b))
        enhanced_rgb = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
        return ImageOps.autocontrast(Image.fromarray(enhanced_rgb), cutoff=1)

    def _enhance_document_photo_bw(self, image: Image.Image) -> Image.Image:
        readable = self._enhance_document_photo(image, mode=DocumentPhotoMode.READABLE)
        gray = np.asarray(readable)
        threshold = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        return Image.fromarray(threshold)

    def _add_document_photo_margin(self, image: Image.Image) -> Image.Image:
        border_px = max(12, min(image.size) // 45)
        return ImageOps.expand(image, border=border_px, fill=255 if image.mode == "L" else "white")

    def _build_document_photos_to_pdf_message(
        self,
        *,
        total_images: int,
        perspective_count: int,
        fallback_count: int,
        warnings: set[str],
        mode: DocumentPhotoMode,
    ) -> str:
        subject_label = "foto del documento" if total_images == 1 else "foto dei documenti"
        message = f"PDF pronto. Ho raddrizzato e pulito {total_images} {subject_label}."
        mode_messages = {
            DocumentPhotoMode.READABLE: "Ho usato il profilo più leggibile.",
            DocumentPhotoMode.COLOR: "Ho mantenuto il colore migliorando il contrasto.",
            DocumentPhotoMode.BW: "Ho creato una versione bianco/nero pulita.",
        }
        message += f" {mode_messages[mode]}"
        if perspective_count:
            message += f" Correzione prospettica applicata a {perspective_count}."
        if fallback_count:
            message += f" Per {fallback_count} ho usato un fallback conservativo: contorno del foglio o prospettiva non erano sicuri."
        warning_messages = {
            "foto_scura": "Alcune foto sembrano scure: se il testo resta poco leggibile, riprova con più luce.",
            "foto_molto_chiara": "Alcune foto sono molto chiare: se il testo perde contrasto, riprova evitando riflessi.",
            "contrasto_basso": "Alcune foto hanno poco contrasto: appoggia il foglio su uno sfondo più diverso dal documento.",
            "foto_sfuocata": "Alcune foto sembrano sfocate: riprova tenendo il telefono fermo e mettendo bene a fuoco il testo.",
            "contorno_non_sicuro": "Non sempre ho visto un bordo leggibile del foglio: lascia spazio attorno al documento e usa uno sfondo uniforme.",
            "foglio_vicino_ai_bordi": "In almeno una foto il foglio è vicino ai bordi: lascia un po' di spazio attorno al documento per un ritaglio migliore.",
        }
        for warning_key, warning_message in warning_messages.items():
            if warning_key in warnings:
                message += f" {warning_message}"
        return message
