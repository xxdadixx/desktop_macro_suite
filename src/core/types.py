from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias, runtime_checkable

import numpy as np

from .enums import ButtonState, KeyState, MouseButton

ImageBuffer: TypeAlias = np.ndarray[tuple[int, ...], np.dtype[np.uint8]]
Nanoseconds: TypeAlias = int
Microseconds: TypeAlias = float
Milliseconds: TypeAlias = float


@dataclass(frozen=True, slots=True)
class Point2D:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class NormalizedPoint2D:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Size2D:
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Rect2D:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    found: bool
    confidence: float
    bounding_box: Rect2D
    center: Point2D


@dataclass(frozen=True, slots=True)
class RawMouseEvent:
    x: int
    y: int
    button: MouseButton | None
    state: ButtonState | None
    wheel_delta: int
    timestamp_ns: Nanoseconds


@dataclass(frozen=True, slots=True)
class RawKeyboardEvent:
    vk_code: int
    scan_code: int
    state: KeyState
    is_extended: bool
    timestamp_ns: Nanoseconds


MouseHookCallback: TypeAlias = Callable[[RawMouseEvent], None]
KeyboardHookCallback: TypeAlias = Callable[[RawKeyboardEvent], None]
ExecutionTelemetryCallback: TypeAlias = Callable[[str, Milliseconds], None]


@runtime_checkable
class CancellationTokenProtocol(Protocol):
    def is_cancelled(self) -> bool:
        raise NotImplementedError("Protocol implementation required")

    def raise_if_cancelled(self) -> None:
        raise NotImplementedError("Protocol implementation required")


@runtime_checkable
class InputSynthesizerProtocol(Protocol):
    def send_mouse_move(self, x: int, y: int) -> None:
        raise NotImplementedError("Protocol implementation required")

    def send_mouse_button(self, button: MouseButton, state: ButtonState) -> None:
        raise NotImplementedError("Protocol implementation required")

    def send_mouse_scroll(self, delta: int) -> None:
        raise NotImplementedError("Protocol implementation required")

    def send_keyboard_key(self, vk_code: int, scan_code: int, state: KeyState) -> None:
        raise NotImplementedError("Protocol implementation required")


@runtime_checkable
class InputHookProtocol(Protocol):
    def start(self) -> None:
        raise NotImplementedError("Protocol implementation required")

    def stop(self) -> None:
        raise NotImplementedError("Protocol implementation required")

    def is_running(self) -> bool:
        raise NotImplementedError("Protocol implementation required")


@runtime_checkable
class FrameCaptureProtocol(Protocol):
    def capture(self, region: Rect2D | None = None) -> ImageBuffer:
        raise NotImplementedError("Protocol implementation required")
