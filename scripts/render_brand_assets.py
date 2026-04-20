#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from docmolder.brand_assets import render_brand_assets


def main() -> None:
    output_dir = PROJECT_ROOT / "assets" / "brand"
    generated = render_brand_assets(output_dir)
    for path in generated:
        print(path.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
