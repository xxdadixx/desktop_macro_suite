from __future__ import annotations

import ctypes
from collections.abc import Callable
import threading
from types import TracebackType
from typing import Final, cast, override

from src.core.exceptions import TimerResolutionError
from src.platform.base import HighResolutionTimerProtocol

TIMERR_NOERROR: Final[int] = 0

_winmm = ctypes.WinDLL("winmm")

_winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
_winmm.timeBeginPeriod.restype = ctypes.c_uint

_winmm.timeEndPeriod.argtypes = [ctypes.c_uint]
_winmm.timeEndPeriod.restype = ctypes.c_uint

_time_begin_period: Callable[[int], int] = cast(
    Callable[[int], int], _winmm.timeBeginPeriod
)
_time_end_period: Callable[[int], int] = cast(
    Callable[[int], int], _winmm.timeEndPeriod
)


class Win32TimerManager(HighResolutionTimerProtocol):
    """Manages system-wide timer interrupt resolution using Win32 timeBeginPeriod."""

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._active_resolution_ms: int | None = None

    @property
    def active_resolution_ms(self) -> int | None:
        with self._lock:
            return self._active_resolution_ms

    @override
    def set_minimum_resolution(self, resolution_ms: int = 1) -> None:
        with self._lock:
            if self._active_resolution_ms == resolution_ms:
                return

            if self._active_resolution_ms is not None:
                self.restore_resolution(self._active_resolution_ms)

            status: int = _time_begin_period(resolution_ms)
            if status != TIMERR_NOERROR:
                raise TimerResolutionError(resolution_ms)

            self._active_resolution_ms = resolution_ms

    @override
    def restore_resolution(self, resolution_ms: int = 1) -> None:
        with self._lock:
            if self._active_resolution_ms is None:
                return

            status: int = _time_end_period(resolution_ms)
            if status != TIMERR_NOERROR:
                raise TimerResolutionError(resolution_ms)

            self._active_resolution_ms = None

    @override
    def __enter__(self) -> HighResolutionTimerProtocol:
        self.set_minimum_resolution(1)
        return self

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        with self._lock:
            if self._active_resolution_ms is not None:
                current: int = self._active_resolution_ms
                _ = _time_end_period(current)
                self._active_resolution_ms = None