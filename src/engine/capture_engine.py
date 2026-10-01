from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Final

from src.core.ast import (
    ActionNode,
    DelayAction,
    KeyboardKeyAction,
    MacroSequence,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.types import Nanoseconds, RawKeyboardEvent, RawMouseEvent
from src.platform.base import LowLevelHookManagerProtocol

NS_PER_MS: Final[float] = 1_000_000.0
MIN_DELAY_THRESHOLD_MS: Final[float] = 1.0


class InputCaptureEngine:
    """Captures low-level hardware input events and normalizes them into AST action nodes."""

    def __init__(self, hook_manager: LowLevelHookManagerProtocol) -> None:
        self._hook_manager: LowLevelHookManagerProtocol = hook_manager
        self._lock: threading.Lock = threading.Lock()
        self._recording: bool = False
        self._recorded_actions: list[ActionNode] = []
        self._last_event_ns: Nanoseconds | None = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return

            self._recorded_actions.clear()
            self._last_event_ns = None
            self._recording = True

            self._hook_manager.register_mouse_callback(self._on_mouse_event)
            self._hook_manager.register_keyboard_callback(self._on_keyboard_event)

    def stop_recording(self) -> list[ActionNode]:
        with self._lock:
            if not self._recording:
                return list(self._recorded_actions)

            self._hook_manager.unregister_mouse_callback(self._on_mouse_event)
            self._hook_manager.unregister_keyboard_callback(self._on_keyboard_event)
            self._recording = False
            self._last_event_ns = None

            return list(self._recorded_actions)

    def to_macro_sequence(
        self,
        name: str,
        description: str = "",
        author: str = "",
    ) -> MacroSequence:
        with self._lock:
            actions_snapshot: list[ActionNode] = list(self._recorded_actions)

        created_time: str = datetime.now(timezone.utc).isoformat()
        return MacroSequence(
            name=name,
            description=description,
            author=author,
            created_at_utc=created_time,
            actions=actions_snapshot,
        )

    def _append_delay_if_needed(self, current_ns: Nanoseconds) -> None:
        if self._last_event_ns is not None:
            delta_ns: int = current_ns - self._last_event_ns
            delta_ms: float = delta_ns / NS_PER_MS
            if delta_ms >= MIN_DELAY_THRESHOLD_MS:
                delay_action = DelayAction(
                    duration_ms=round(delta_ms, 2),
                    jitter_ms=0.0,
                )
                self._recorded_actions.append(delay_action)
        self._last_event_ns = current_ns

    def _on_mouse_event(self, event: RawMouseEvent) -> None:
        with self._lock:
            if not self._recording:
                return

            self._append_delay_if_needed(event.timestamp_ns)

            if event.wheel_delta != 0:
                scroll_action = MouseScrollAction(
                    delta=event.wheel_delta,
                    horizontal=False,
                )
                self._recorded_actions.append(scroll_action)
            elif event.button is not None and event.state is not None:
                btn_action = MouseButtonAction(
                    button=event.button,
                    state=event.state,
                    x=event.x,
                    y=event.y,
                )
                self._recorded_actions.append(btn_action)
            else:
                move_action = MouseMoveAction(
                    x=event.x,
                    y=event.y,
                    duration_ms=0.0,
                    is_relative=False,
                )
                self._recorded_actions.append(move_action)

    def _on_keyboard_event(self, event: RawKeyboardEvent) -> None:
        with self._lock:
            if not self._recording:
                return

            self._append_delay_if_needed(event.timestamp_ns)

            key_action = KeyboardKeyAction(
                vk_code=event.vk_code,
                scan_code=event.scan_code,
                state=event.state,
                is_extended=event.is_extended,
                key_name=f"VK_{event.vk_code:02X}",
            )
            self._recorded_actions.append(key_action)