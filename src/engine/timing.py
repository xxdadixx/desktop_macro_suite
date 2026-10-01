from __future__ import annotations

import asyncio
import time
from typing import Final

from src.core.types import CancellationTokenProtocol, Milliseconds, Nanoseconds

NS_PER_MS: Final[int] = 1_000_000
NS_PER_SECOND: Final[int] = 1_000_000_000
COARSE_SLEEP_THRESHOLD_NS: Final[int] = 3 * NS_PER_MS


class PreciseTimer:
    """High-precision hybrid sleep runner with sub-millisecond spin-lock drift compensation."""

    @staticmethod
    def sleep_ms(
        duration_ms: Milliseconds,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> None:
        """Synchronously blocks execution for the requested milliseconds with sub-millisecond precision."""
        if duration_ms <= 0.0:
            return

        target_duration_ns: Nanoseconds = int(duration_ms * NS_PER_MS)
        start_ns: Nanoseconds = time.perf_counter_ns()
        target_deadline_ns: Nanoseconds = start_ns + target_duration_ns

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            now_ns: Nanoseconds = time.perf_counter_ns()
            remaining_ns: Nanoseconds = target_deadline_ns - now_ns

            if remaining_ns <= 0:
                break

            if remaining_ns > COARSE_SLEEP_THRESHOLD_NS:
                sleep_seconds: float = (remaining_ns - COARSE_SLEEP_THRESHOLD_NS) / NS_PER_SECOND
                time.sleep(sleep_seconds)
            else:
                while time.perf_counter_ns() < target_deadline_ns:
                    if cancellation_token is not None:
                        cancellation_token.raise_if_cancelled()
                break

    @staticmethod
    async def sleep_ms_async(
        duration_ms: Milliseconds,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> None:
        """Asynchronously suspends coroutine execution with coarse cooperative scheduling and fine spin-locking."""
        if duration_ms <= 0.0:
            return

        target_duration_ns: Nanoseconds = int(duration_ms * NS_PER_MS)
        start_ns: Nanoseconds = time.perf_counter_ns()
        target_deadline_ns: Nanoseconds = start_ns + target_duration_ns

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            now_ns: Nanoseconds = time.perf_counter_ns()
            remaining_ns: Nanoseconds = target_deadline_ns - now_ns

            if remaining_ns <= 0:
                break

            if remaining_ns > COARSE_SLEEP_THRESHOLD_NS:
                sleep_seconds: float = (remaining_ns - COARSE_SLEEP_THRESHOLD_NS) / NS_PER_SECOND
                await asyncio.sleep(sleep_seconds)
            else:
                while time.perf_counter_ns() < target_deadline_ns:
                    if cancellation_token is not None:
                        cancellation_token.raise_if_cancelled()
                break