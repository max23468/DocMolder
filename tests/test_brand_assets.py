from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.brand_assets import render_brand_assets
from docmolder.branding import MAIN_MENU_ROWS, build_telegram_commands


class BrandAssetsTest(unittest.TestCase):
    def test_render_brand_assets_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generated = render_brand_assets(output_dir)

            expected_names = {
                "docmolder-logo-square.png",
                "docmolder-logo-ios-rounded.png",
                "docmolder-logo-telegram-circle.png",
                "docmolder-telegram-profile.png",
                "docmolder-telegram-profile.jpg",
                "docmolder-app-icon.png",
                "docmolder-logo-horizontal.png",
                "docmolder-share-card.png",
            }
            self.assertEqual({path.name for path in generated}, expected_names)
            for path in generated:
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_branding_exports_core_navigation_and_commands(self) -> None:
        self.assertEqual(MAIN_MENU_ROWS[0][0], "Guida rapida")
        self.assertEqual(MAIN_MENU_ROWS[0][1], "Crea PDF")
        commands = build_telegram_commands()
        self.assertEqual(commands[0].command, "start")
        self.assertEqual(commands[1].command, "help")


if __name__ == "__main__":
    unittest.main()
