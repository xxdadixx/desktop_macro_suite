from __future__ import annotations

import sys
from typing import override

from src.core.exceptions import PlatformError
from src.platform.base import BasePlatformProvider
from src.platform.win32.capture import Win32GdiCapture
from src.platform.win32.hooks import Win32HookManager
from src.platform.win32.synthesis import Win32InputSynthesizer
from src.platform.win32.timer import Win32TimerManager

__all__ = ["Win32PlatformProvider"]


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