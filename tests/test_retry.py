from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.retry import run_with_retry


class RetryHelpersTest(unittest.TestCase):
    def test_run_with_retry_retries_retryable_errors(self) -> None:
        attempts = 0
        sleeps: list[float] = []

        def action() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporaneo")
            return "ok"

        result = run_with_retry(
            action,
            max_attempts=3,
            should_retry=lambda exc: isinstance(exc, RuntimeError),
            base_delay=1,
            jitter_max=0,
            sleep_fn=sleeps.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 3)
        self.assertEqual(sleeps, [1, 2])


if __name__ == "__main__":
    unittest.main()
