"""Fixture condivise dai test delle capacità documentali."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from docmolder.processing import DocumentProcessor


def save_realistic_document_photo(path: Path, *, near_edge: bool = False, low_contrast: bool = False) -> None:
    background_color = (126, 116, 102) if not low_contrast else (112, 108, 102)
    image = Image.new("RGB", (1200, 1600), background_color)
    draw = ImageDraw.Draw(image)
    for x in range(0, image.width, 32):
        delta = (x % 64 - 32) // 5
        draw.line((x, 0, x, image.height), fill=tuple(max(0, min(255, value + delta)) for value in background_color))
    page_points = (
        [(20, 70), (1020, 120), (1110, 1510), (15, 1450)]
        if near_edge
        else [(245, 120), (930, 220), (1015, 1435), (145, 1300)]
    )
    draw.polygon([(x + 30, y + 45) for x, y in page_points], fill=(82, 75, 68))
    page_fill = (248, 247, 239) if not low_contrast else (154, 150, 142)
    page_outline = (224, 222, 210) if not low_contrast else (136, 132, 126)
    ink_color = (20, 20, 20) if not low_contrast else (76, 74, 70)
    draw.polygon(page_points, fill=page_fill, outline=page_outline)
    draw.rectangle((340, 300, 720, 352), outline=ink_color, width=4)
    draw.text((360, 310), "DOCMOLDER TEST INVOICE", fill=ink_color)
    for y in range(440, 940, 75):
        draw.line((300, y, 830, y + 35), fill=ink_color, width=7)
    for x in (310, 520, 730):
        draw.line((x, 1040, x + 80, 1215), fill=ink_color, width=4)
    for y in (1040, 1098, 1156, 1214):
        draw.line((300, y, 850, y + 10), fill=ink_color, width=4)
    image.filter(ImageFilter.GaussianBlur(radius=0.4)).save(path, quality=90)


class ProcessingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.processor = DocumentProcessor(self.runtime_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
