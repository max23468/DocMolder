from __future__ import annotations

import unittest

from scripts.profile_processing_flows import build_profile


class ProfileProcessingTests(unittest.TestCase):
    def test_build_profile_uses_split_processing_capabilities(self) -> None:
        profile = build_profile(image_count=1, image_side=200, pdf_pages=1)

        self.assertEqual(
            [measurement["label"] for measurement in profile["measurements"]],
            ["images_to_pdf_a4", "images_to_pdf_original", "pdf_grayscale", "pdf_compress_light"],
        )


if __name__ == "__main__":
    unittest.main()
