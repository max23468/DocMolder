from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import SensitiveLogFilter, _redact_sensitive_text


class SensitiveLoggingTest(unittest.TestCase):
    def test_redact_sensitive_text_masks_telegram_bot_token_in_url(self) -> None:
        text = (
            'HTTP Request: POST '
            'https://api.telegram.org/bot123456:ABCdef_GHI-123/getUpdates '
            '"HTTP/1.1 200 OK"'
        )

        redacted = _redact_sensitive_text(text)

        self.assertNotIn("ABCdef_GHI-123", redacted)
        self.assertIn("https://api.telegram.org/bot<redacted>/getUpdates", redacted)

    def test_sensitive_log_filter_redacts_tuple_args(self) -> None:
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Request to %s",
            args=("https://api.telegram.org/bot123456:ABCdef_GHI-123/getUpdates",),
            exc_info=None,
        )

        allowed = SensitiveLogFilter().filter(record)

        self.assertTrue(allowed)
        self.assertEqual(
            record.args,
            ("https://api.telegram.org/bot<redacted>/getUpdates",),
        )


if __name__ == "__main__":
    unittest.main()
