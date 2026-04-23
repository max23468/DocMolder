from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.logging_utils import format_log_context, generate_operation_id


class LoggingUtilsTest(unittest.TestCase):
    def test_format_log_context_is_stable_and_single_line(self) -> None:
        line = format_log_context("job started", job_id=12, note="riga uno\nriga due")

        self.assertEqual(line, "event=job_started job_id=12 note=riga_uno\\nriga_due")

    def test_generate_operation_id_uses_prefix(self) -> None:
        operation_id = generate_operation_id("job")

        self.assertTrue(operation_id.startswith("job-"))
        self.assertGreater(len(operation_id), len("job-"))


if __name__ == "__main__":
    unittest.main()
