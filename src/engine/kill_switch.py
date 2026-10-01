from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final, override

from src.core.enums import KeyState
from src.core.exceptions import ExecutionAbortedError
from src.core.types import CancellationTokenProtocol, RawKeyboardEvent
from src.platform.base import LowLevelHookManagerProtocol

DEFAULT_ABORT_VK: Final[int] = 0x7B  # VK_F12


class CancellationToken(CancellationTokenProtocol):
    """Thread-safe cancellation token supporting cooperative execution halting."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._cancelled: bool = False
        self._reason: str = "Execution was cancelled"

    @override
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @override
    def raise_if_cancelled(self) -> None:
        with self._lock:
            if self._cancelled:
                raise ExecutionAbortedError(self._reason)

    def cancel(self, reason: str = "Execution was cancelled") -> None:
        with self._lock:
            self._cancelled = True
            self._reason = reason

    def reset(self) -> None:
        with self._lock:
            self._cancelled = False
            self._reason = "Execution was cancelled"


class HardwareKillSwitch:
    """Low-level emergency halt interceptor attaching directly to the OS hook layer."""

    def __init__(
        self,
        hook_manager: LowLevelHookManagerProtocol,
        token: CancellationToken,
        abort_vk_code: int = DEFAULT_ABORT_VK,
    ) -> None:
        self._hook_manager: LowLevelHookManagerProtocol = hook_manager
        self._token: CancellationToken = token
        self._abort_vk_code: int = abort_vk_code
        self._lock: threading.Lock = threading.Lock()
        self._active: bool = False
        self._abort_callbacks: list[Callable[[str], None]] = []

    def register_abort_callback(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if callback not in self._abort_callbacks:
                self._abort_callbacks.append(callback)

    def unregister_abort_callback(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if callback in self._abort_callbacks:
                self._abort_callbacks.remove(callback)

    def activate(self) -> None:
        with self._lock:
            if self._active:
                return
            self._hook_manager.register_keyboard_callback(self._handle_keyboard_event)
            self._active = True

    def deactivate(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._hook_manager.unregister_keyboard_callback(self._handle_keyboard_event)
            self._active = False

    def _handle_keyboard_event(self, event: RawKeyboardEvent) -> None:
        if event.state != KeyState.KEY_DOWN:
            return

        if event.vk_code == self._abort_vk_code:
            reason: str = f"Hardware kill-switch triggered by keycode 0x{event.vk_code:02X}"
            self._token.cancel(reason)

            with self._lock:
                callbacks: list[Callable[[str], None]] = list(self._abort_callbacks)

            for cb in callbacks:
                try:
                    cb(reason)
                except Exception:
                    continue