from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.errors import AppError, ConfigurationError, TelegramApiError


class ErrorsTest(unittest.TestCase):
    def test_telegram_api_error_keeps_status_code(self) -> None:
        error = TelegramApiError("rate limited", status_code=429)

        self.assertIsInstance(error, AppError)
        self.assertEqual(error.status_code, 429)

    def test_configuration_error_is_app_error(self) -> None:
        self.assertIsInstance(ConfigurationError("missing token"), AppError)
