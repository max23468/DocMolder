#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from PIL import Image, ImageDraw
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docmolder.models import CompressionPreset  # noqa: E402
from docmolder.processing import DocumentProcessor  # noqa: E402


def _write_image(path: Path, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for y in range(80, size[1] - 80, 120):
        draw.line((80, y, size[0] - 80, y), fill=(40, 40, 40), width=6)
    image.save(path, quality=88)


def _write_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as handle:
        writer.write(handle)


def _measure(label: str, func) -> dict[str, Any]:
    started_at = perf_counter()
    result = func()
    duration_ms = round((perf_counter() - started_at) * 1000)
    output_paths = [result.output_path, *(output.path for output in result.additional_outputs)]
    return {
        "label": label,
        "duration_ms": duration_ms,
        "processing_mode": result.processing_mode,
        "output_bytes": sum(path.stat().st_size for path in output_paths if path.exists()),
        "message": result.message,
    }


def build_profile(*, image_count: int, image_side: int, pdf_pages: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        runtime_dir = root / "runtime"
        input_dir = runtime_dir / "jobs" / "profile" / "input"
        input_dir.mkdir(parents=True)
        processor = DocumentProcessor(runtime_dir)

        image_paths: list[Path] = []
        for index in range(image_count):
            path = input_dir / f"image_{index + 1}.jpg"
            _write_image(path, (image_side, image_side))
            image_paths.append(path)

        pdf_path = input_dir / "source.pdf"
        _write_pdf(pdf_path, pages=pdf_pages)

        measurements = [
            _measure(
                "images_to_pdf_a4",
                lambda: processor.images_to_pdf(image_paths, "images_a4", use_a4_layout=True),
            ),
            _measure(
                "images_to_pdf_original",
                lambda: processor.images_to_pdf(image_paths, "images_original", use_a4_layout=False),
            ),
            _measure(
                "pdf_grayscale",
                lambda: processor.pdf_to_grayscale(pdf_path, "source_gray"),
            ),
            _measure(
                "pdf_compress_light",
                lambda: processor.compress_pdf(pdf_path, "source_light", CompressionPreset.LIGHT),
            ),
        ]

    return {
        "image_count": image_count,
        "image_side": image_side,
        "pdf_pages": pdf_pages,
        "measurements": measurements,
    }


def main() -> int:
    logging.basicConfig(level=logging.CRITICAL)
    parser = argparse.ArgumentParser(description="Profilo locale leggero dei flussi documentali pesanti.")
    parser.add_argument("--image-count", type=int, default=6)
    parser.add_argument("--image-side", type=int, default=2400)
    parser.add_argument("--pdf-pages", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profile = build_profile(
        image_count=max(1, args.image_count),
        image_side=max(200, args.image_side),
        pdf_pages=max(1, args.pdf_pages),
    )
    if args.json:
        print(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print("# Processing profile")
    print(f"- images: {profile['image_count']} x {profile['image_side']}px")
    print(f"- pdf_pages: {profile['pdf_pages']}")
    for item in profile["measurements"]:
        print(
            f"- {item['label']}: {item['duration_ms']}ms, "
            f"mode={item['processing_mode']}, output_bytes={item['output_bytes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
