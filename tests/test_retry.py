from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.retry import run_async_with_retry, run_with_retry


class RetryHelpersTest(unittest.IsolatedAsyncioTestCase):
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

    def test_run_with_retry_stops_on_non_retryable_errors(self) -> None:
        sleeps: list[float] = []

        with self.assertRaises(ValueError):
            run_with_retry(
                lambda: (_ for _ in ()).throw(ValueError("definitivo")),
                max_attempts=3,
                should_retry=lambda exc: isinstance(exc, RuntimeError),
                sleep_fn=sleeps.append,
            )

        self.assertEqual(sleeps, [])

    async def test_run_async_with_retry_uses_override_delay_and_max_delay(self) -> None:
        attempts = 0
        sleeps: list[float] = []
        retry_events: list[tuple[str, int, int, float]] = []

        async def action() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporaneo")
            return "ok"

        async def sleep_fn(delay: float) -> None:
            sleeps.append(delay)

        result = await run_async_with_retry(
            action,
            max_attempts=3,
            should_retry=lambda exc: isinstance(exc, RuntimeError),
            delay_for_exception=lambda exc, attempt_index: 10 + attempt_index,
            max_delay=3,
            on_retry=lambda exc, attempt, total, delay: retry_events.append(
                (type(exc).__name__, attempt, total, delay)
            ),
            sleep_fn=sleep_fn,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 3)
        self.assertEqual(sleeps, [3, 3])
        self.assertEqual(retry_events, [("RuntimeError", 1, 3, 3), ("RuntimeError", 2, 3, 3)])


if __name__ == "__main__":
    unittest.main()
