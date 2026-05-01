from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.main import main


class MainEntrypointTest(unittest.TestCase):
    def test_main_builds_application_and_starts_polling_for_supported_updates(self) -> None:
        settings = MagicMock(name="settings")
        application = MagicMock(name="application")

        with patch("docmolder.main.load_settings", return_value=settings) as load_settings, patch(
            "docmolder.main.build_application", return_value=application
        ) as build_application:
            main()

        load_settings.assert_called_once_with()
        build_application.assert_called_once_with(settings)
        application.run_polling.assert_called_once_with(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    unittest.main()
