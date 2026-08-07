from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image

A4_WIDTH_PX = 1240
A4_HEIGHT_PX = 1754
A4_MARGIN_WIDE_PX = 120
A4_MARGIN_NARROW_PX = 48
A4_MARGIN_NONE_PX = 0
DOCUMENT_PHOTO_DETECTION_MAX_SIDE = 1800
DOCUMENT_PHOTO_OUTPUT_MAX_SIDE = 2400
IMAGE_PDF_DEFAULT_MAX_SOURCE_SIDE = 3200
IMAGE_MAX_PIXELS = 40000000
PDF_MAX_PAGES = 200
PDF_SPLIT_MAX_PAGES = 50
PDF_RASTER_MAX_PIXELS = 40000000


@dataclass(slots=True)
class ProcessingOutput:
    path: Path
    name: str


@dataclass(slots=True)
class ProcessingResult:
    output_path: Path
    output_name: str
    message: str
    auto_rotation_applied: bool = False
    processing_mode: str | None = None
    additional_outputs: list[ProcessingOutput] = field(default_factory=list)


@dataclass(slots=True)
class _DocumentPhotoTransform:
    image: Image.Image
    mode: str
    warnings: set[str] = field(default_factory=set)


class ProcessingUserError(Exception):
    pass
