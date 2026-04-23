from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def compute_backoff_delay(
    base_delay: float,
    attempt_index: int,
    *,
    jitter_max: float = 0.25,
) -> float:
    return base_delay * (2**attempt_index) + random.uniform(0, jitter_max)


def run_with_retry(
    action: Callable[[], T],
    *,
    max_attempts: int,
    should_retry: Callable[[Exception], bool],
    on_retry: Callable[[Exception, int, int, float], None] | None = None,
    delay_for_exception: Callable[[Exception, int], float | None] | None = None,
    base_delay: float = 0.5,
    max_delay: float | None = None,
    jitter_max: float = 0.25,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    attempts = max(1, max_attempts)
    last_error: Exception | None = None
    for attempt_index in range(attempts):
        try:
            return action()
        except Exception as exc:
            last_error = exc
            is_last_attempt = attempt_index == attempts - 1
            if is_last_attempt or not should_retry(exc):
                raise
            delay = _compute_retry_delay(
                exc,
                attempt_index,
                delay_for_exception=delay_for_exception,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter_max=jitter_max,
            )
            if on_retry is not None:
                on_retry(exc, attempt_index + 1, attempts, delay)
            sleep_fn(delay)
    assert last_error is not None
    raise last_error


async def run_async_with_retry(
    action: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    should_retry: Callable[[Exception], bool],
    on_retry: Callable[[Exception, int, int, float], None] | None = None,
    delay_for_exception: Callable[[Exception, int], float | None] | None = None,
    base_delay: float = 0.5,
    max_delay: float | None = None,
    jitter_max: float = 0.25,
    sleep_fn: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> T:
    attempts = max(1, max_attempts)
    last_error: Exception | None = None
    for attempt_index in range(attempts):
        try:
            return await action()
        except Exception as exc:
            last_error = exc
            is_last_attempt = attempt_index == attempts - 1
            if is_last_attempt or not should_retry(exc):
                raise
            delay = _compute_retry_delay(
                exc,
                attempt_index,
                delay_for_exception=delay_for_exception,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter_max=jitter_max,
            )
            if on_retry is not None:
                on_retry(exc, attempt_index + 1, attempts, delay)
            await sleep_fn(delay)
    assert last_error is not None
    raise last_error


def _compute_retry_delay(
    exc: Exception,
    attempt_index: int,
    *,
    delay_for_exception: Callable[[Exception, int], float | None] | None,
    base_delay: float,
    max_delay: float | None,
    jitter_max: float,
) -> float:
    override = delay_for_exception(exc, attempt_index) if delay_for_exception is not None else None
    delay = override if override is not None else compute_backoff_delay(base_delay, attempt_index, jitter_max=jitter_max)
    if max_delay is not None:
        return min(delay, max_delay)
    return delay
