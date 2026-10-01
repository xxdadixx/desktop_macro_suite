from abc import ABC, abstractmethod
from types import TracebackType
from typing import Protocol, runtime_checkable

from src.core.types import (
    FrameCaptureProtocol,
    InputHookProtocol,
    InputSynthesizerProtocol,
    KeyboardHookCallback,
    MouseHookCallback,
)

@runtime_checkable
class HighResolutionTimerProtocol(Protocol):
    """Controls OS kernel timer interrupt granularity (e.g. 1ms Windows quantum)."""

    def set_minimum_resolution(self, resolution_ms: int = 1) -> None:
        raise NotImplementedError("Protocol implementation required")

    def restore_resolution(self, resolution_ms: int = 1) -> None:
        raise NotImplementedError("Protocol implementation required")

    def __enter__(self) -> "HighResolutionTimerProtocol":
        raise NotImplementedError("Protocol implementation required")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        raise NotImplementedError("Protocol implementation required")


@runtime_checkable
class LowLevelHookManagerProtocol(InputHookProtocol, Protocol):
    """Manages low-level global OS input interceptors."""

    def register_mouse_callback(self, callback: MouseHookCallback) -> None:
        raise NotImplementedError("Protocol implementation required")

    def unregister_mouse_callback(self, callback: MouseHookCallback) -> None:
        raise NotImplementedError("Protocol implementation required")

    def register_keyboard_callback(self, callback: KeyboardHookCallback) -> None:
        raise NotImplementedError("Protocol implementation required")

    def unregister_keyboard_callback(self, callback: KeyboardHookCallback) -> None:
        raise NotImplementedError("Protocol implementation required")


class BasePlatformProvider(ABC):
    """Abstract Factory providing operating system-specific input and display interfaces."""

    @property
    @abstractmethod
    def timer(self) -> HighResolutionTimerProtocol:
        """High-precision multimedia timer manager."""

    @property
    @abstractmethod
    def synthesizer(self) -> InputSynthesizerProtocol:
        """Hardware/virtual event simulator."""

    @property
    @abstractmethod
    def hook_manager(self) -> LowLevelHookManagerProtocol:
        """Low-level OS event hooking service."""

    @property
    @abstractmethod
    def screen_capture(self) -> FrameCaptureProtocol:
        """Zero-copy or hardware-accelerated desktop capture provider."""

    @abstractmethod
    def initialize(self) -> None:
        """Bootstraps native OS dependencies, subsystems, and privilege checks."""

    @abstractmethod
    def shutdown(self) -> None:
        """Releases all unmanaged OS handles, unhooks message pumps, and restores system timers."""

    def __enter__(self) -> "BasePlatformProvider":
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.shutdown()