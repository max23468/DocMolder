from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.smoke_telegram_desktop import (
    SUPPORTED_PLANS,
    build_assets,
    build_plan,
    cleanup_assets,
    escape_applescript,
)


class SmokeTelegramDesktopScriptTest(unittest.TestCase):
    def test_escape_applescript_escapes_quotes_and_backslashes(self) -> None:
        escaped = escape_applescript('A "quote" and \\\\ slash')

        self.assertEqual(escaped, 'A \\"quote\\" and \\\\\\\\ slash')

    def test_build_assets_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = build_assets(Path(temp_dir))

            self.assertTrue(assets["image_1"].exists())
            self.assertTrue(assets["image_2"].exists())
            self.assertTrue(assets["pdf"].exists())
            self.assertEqual(assets["pdf"].suffix.lower(), ".pdf")

    def test_build_plan_full_includes_followup_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = build_assets(Path(temp_dir))

            steps = build_plan("full", assets)

            self.assertGreaterEqual(len(steps), 8)
            self.assertEqual(steps[0].value, "/reset")
            self.assertIn("Scala di grigi", [step.value for step in steps if step.kind == "text"])
            self.assertIn("/history", [step.value for step in steps if step.kind == "text"])

    def test_supported_plans_are_exposed(self) -> None:
        self.assertIn("full", SUPPORTED_PLANS)
        self.assertIn("wizard-a4", SUPPORTED_PLANS)
        self.assertIn("public-trust", SUPPORTED_PLANS)

    def test_public_trust_plan_covers_public_commands_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = build_assets(Path(temp_dir))

            steps = build_plan("public-trust", assets)

            text_steps = [step.value for step in steps if step.kind == "text"]
            self.assertIn("/start", text_steps)
            self.assertIn("/help", text_steps)
            self.assertIn("/start privacy", text_steps)
            self.assertIn("/status", text_steps)
            self.assertIn("/reset", text_steps)
            self.assertTrue(any(step.kind == "file" and step.value.endswith(".pdf") for step in steps))

    def test_cleanup_assets_removes_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_dir = Path(temp_dir)
            build_assets(asset_dir)

            cleanup_assets(asset_dir)

            self.assertEqual(list(asset_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
