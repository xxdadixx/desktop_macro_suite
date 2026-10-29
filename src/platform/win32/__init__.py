from __future__ import annotations

from collections.abc import Callable
import ctypes
import sys
from typing import Final, cast, override

from src.core.exceptions import PlatformError
from src.platform.base import BasePlatformProvider
from src.platform.win32.capture import Win32GdiCapture
from src.platform.win32.hooks import Win32HookManager
from src.platform.win32.synthesis import Win32InputSynthesizer
from src.platform.win32.timer import Win32TimerManager

__all__: Final[list[str]] = ["Win32PlatformProvider"]

_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2: Final[int] = -4
_PROCESS_PER_MONITOR_DPI_AWARE: Final[int] = 2


def _enable_dpi_awareness() -> None:
    """Configures Per-Monitor DPI Awareness V2 to avoid GDI and Input coordinate virtualization."""
    # 1. Windows 10 (1703+) SetProcessDpiAwarenessContext
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context_attr: object = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if callable(set_context_attr):
            set_context_fn: Callable[[ctypes.c_void_p], int] = cast(
                Callable[[ctypes.c_void_p], int], set_context_attr
            )
            _ = set_context_fn(ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
            return
    except (AttributeError, OSError):
        pass

    # 2. Windows 8.1 / early Windows 10 SetProcessDpiAwareness
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_awareness_attr: object = getattr(shcore, "SetProcessDpiAwareness", None)
        if callable(set_awareness_attr):
            set_awareness_fn: Callable[[int], int] = cast(
                Callable[[int], int], set_awareness_attr
            )
            _ = set_awareness_fn(_PROCESS_PER_MONITOR_DPI_AWARE)
            return
    except (AttributeError, OSError):
        pass

    # 3. Windows Vista fallback SetProcessDPIAware
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_dpi_aware_attr: object = getattr(user32, "SetProcessDPIAware", None)
        if callable(set_dpi_aware_attr):
            set_dpi_aware_fn: Callable[[], int] = cast(
                Callable[[], int], set_dpi_aware_attr
            )
            _ = set_dpi_aware_fn()
    except (AttributeError, OSError):
        pass


class Win32PlatformProvider(BasePlatformProvider):
    """Windows Win32 platform implementation providing input, capture, and timing subsystems."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise PlatformError(f"Win32PlatformProvider is not supported on '{sys.platform}'")

        self._timer: Win32TimerManager = Win32TimerManager()
        self._synthesizer: Win32InputSynthesizer = Win32InputSynthesizer()
        self._hook_manager: Win32HookManager = Win32HookManager()
        self._screen_capture: Win32GdiCapture = Win32GdiCapture()
        self._initialized: bool = False

    @property
    @override
    def timer(self) -> Win32TimerManager:
        return self._timer

    @property
    @override
    def synthesizer(self) -> Win32InputSynthesizer:
        return self._synthesizer

    @property
    @override
    def hook_manager(self) -> Win32HookManager:
        return self._hook_manager

    @property
    @override
    def screen_capture(self) -> Win32GdiCapture:
        return self._screen_capture

    @override
    def initialize(self) -> None:
        if self._initialized:
            return

        _enable_dpi_awareness()
        self._timer.set_minimum_resolution(1)
        self._hook_manager.start()
        self._initialized = True

    @override
    def shutdown(self) -> None:
        if not self._initialized:
            return

        if self._hook_manager.is_running():
            self._hook_manager.stop()

        self._timer.restore_resolution(1)
        self._initialized = False