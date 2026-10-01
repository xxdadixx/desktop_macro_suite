from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time
from collections.abc import Callable
from typing import Final, cast, override

from src.core.enums import ButtonState, KeyState, MouseButton
from src.core.exceptions import HookInstallationError
from src.core.types import (
    KeyboardHookCallback,
    MouseHookCallback,
    RawKeyboardEvent,
    RawMouseEvent,
)
from src.platform.base import LowLevelHookManagerProtocol

WH_KEYBOARD_LL: Final[int] = 13
WH_MOUSE_LL: Final[int] = 14

WM_QUIT: Final[int] = 0x0012
WM_KEYDOWN: Final[int] = 0x0100
WM_KEYUP: Final[int] = 0x0101
WM_SYSKEYDOWN: Final[int] = 0x0104
WM_SYSKEYUP: Final[int] = 0x0105

WM_MOUSEMOVE: Final[int] = 0x0200
WM_LBUTTONDOWN: Final[int] = 0x0201
WM_LBUTTONUP: Final[int] = 0x0202
WM_RBUTTONDOWN: Final[int] = 0x0204
WM_RBUTTONUP: Final[int] = 0x0205
WM_MBUTTONDOWN: Final[int] = 0x0207
WM_MBUTTONUP: Final[int] = 0x0208
WM_MOUSEWHEEL: Final[int] = 0x020A
WM_XBUTTONDOWN: Final[int] = 0x020B
WM_XBUTTONUP: Final[int] = 0x020C

XBUTTON1: Final[int] = 0x0001
XBUTTON2: Final[int] = 0x0002
LLKHF_EXTENDED: Final[int] = 0x0001


class POINT(ctypes.Structure):
    x: int
    y: int
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    pt: POINT
    mouseData: int
    flags: int
    time: int
    dwExtraInfo: int
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    vkCode: int
    scanCode: int
    flags: int
    time: int
    dwExtraInfo: int
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK

_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL

_user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t

_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.GetMessageW.restype = wintypes.BOOL

_user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.PostThreadMessageW.restype = wintypes.BOOL

_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_set_windows_hook_ex: Callable[[int, object, int | None, int], int] = cast(
    Callable[[int, object, int | None, int], int], _user32.SetWindowsHookExW
)
_unhook_windows_hook_ex: Callable[[int], int] = cast(
    Callable[[int], int], _user32.UnhookWindowsHookEx
)
_call_next_hook: Callable[[int, int, int, int], int] = cast(
    Callable[[int, int, int, int], int], _user32.CallNextHookEx
)
_get_message: Callable[[ctypes.Array[wintypes.MSG], int | None, int, int], int] = cast(
    Callable[[ctypes.Array[wintypes.MSG], int | None, int, int], int],
    _user32.GetMessageW,
)
_post_thread_message: Callable[[int, int, int, int], int] = cast(
    Callable[[int, int, int, int], int], _user32.PostThreadMessageW
)
_get_current_thread_id: Callable[[], int] = cast(
    Callable[[], int], _kernel32.GetCurrentThreadId
)
_get_module_handle: Callable[[str | None], int] = cast(
    Callable[[str | None], int], _kernel32.GetModuleHandleW
)


class Win32HookManager(LowLevelHookManagerProtocol):
    """Low-level OS hook interceptor running on an isolated message pump thread."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._mouse_callbacks: list[MouseHookCallback] = []
        self._keyboard_callbacks: list[KeyboardHookCallback] = []

        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._mouse_hook: int | None = None
        self._keyboard_hook: int | None = None

        self._running: bool = False
        self._ready_event: threading.Event = threading.Event()
        self._init_error: HookInstallationError | None = None

        self._mouse_proc: object = cast(object, HOOKPROC(self._low_level_mouse_proc))
        self._keyboard_proc: object = cast(
            object, HOOKPROC(self._low_level_keyboard_proc)
        )

    @override
    def register_mouse_callback(self, callback: MouseHookCallback) -> None:
        with self._lock:
            if callback not in self._mouse_callbacks:
                self._mouse_callbacks.append(callback)

    @override
    def unregister_mouse_callback(self, callback: MouseHookCallback) -> None:
        with self._lock:
            if callback in self._mouse_callbacks:
                self._mouse_callbacks.remove(callback)

    @override
    def register_keyboard_callback(self, callback: KeyboardHookCallback) -> None:
        with self._lock:
            if callback not in self._keyboard_callbacks:
                self._keyboard_callbacks.append(callback)

    @override
    def unregister_keyboard_callback(self, callback: KeyboardHookCallback) -> None:
        with self._lock:
            if callback in self._keyboard_callbacks:
                self._keyboard_callbacks.remove(callback)

    @override
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @override
    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            self._ready_event.clear()
            self._init_error = None

            worker = threading.Thread(
                target=self._pump_messages,
                name="Win32HookPumpThread",
                daemon=True,
            )
            self._thread = worker
            worker.start()

        _ = self._ready_event.wait()
        if self._init_error is not None:
            self.stop()
            raise self._init_error

    @override
    def stop(self) -> None:
        with self._lock:
            if not self._running or self._thread_id is None:
                return

            _ = _post_thread_message(self._thread_id, WM_QUIT, 0, 0)
            thread = self._thread

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            self._running = False
            self._thread = None
            self._thread_id = None

    def _pump_messages(self) -> None:
        thread_id: int = _get_current_thread_id()
        h_mod: int = _get_module_handle(None)

        mouse_hhook: int = _set_windows_hook_ex(
            WH_MOUSE_LL,
            self._mouse_proc,
            h_mod,
            0,
        )
        if mouse_hhook == 0:
            err = ctypes.get_last_error()
            self._init_error = HookInstallationError("WH_MOUSE_LL", err)
            self._ready_event.set()
            return

        keyboard_hhook: int = _set_windows_hook_ex(
            WH_KEYBOARD_LL,
            self._keyboard_proc,
            h_mod,
            0,
        )
        if keyboard_hhook == 0:
            err = ctypes.get_last_error()
            _ = _unhook_windows_hook_ex(mouse_hhook)
            self._init_error = HookInstallationError("WH_KEYBOARD_LL", err)
            self._ready_event.set()
            return

        with self._lock:
            self._thread_id = thread_id
            self._mouse_hook = mouse_hhook
            self._keyboard_hook = keyboard_hhook
            self._running = True

        self._ready_event.set()

        try:
            msg_buffer = (wintypes.MSG * 1)()
            while _get_message(msg_buffer, None, 0, 0) > 0:
                continue
        finally:
            _ = _unhook_windows_hook_ex(mouse_hhook)
            _ = _unhook_windows_hook_ex(keyboard_hhook)
            with self._lock:
                self._mouse_hook = None
                self._keyboard_hook = None
                self._running = False

    def _low_level_mouse_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        hook: int = self._mouse_hook or 0
        if n_code < 0:
            return _call_next_hook(hook, n_code, w_param, l_param)

        now_ns: int = time.perf_counter_ns()
        ms = MSLLHOOKSTRUCT.from_address(l_param)

        button: MouseButton | None = None
        state: ButtonState | None = None
        wheel_delta: int = 0

        if w_param == WM_LBUTTONDOWN:
            button = MouseButton.LEFT
            state = ButtonState.DOWN
        elif w_param == WM_LBUTTONUP:
            button = MouseButton.LEFT
            state = ButtonState.UP
        elif w_param == WM_RBUTTONDOWN:
            button = MouseButton.RIGHT
            state = ButtonState.DOWN
        elif w_param == WM_RBUTTONUP:
            button = MouseButton.RIGHT
            state = ButtonState.UP
        elif w_param == WM_MBUTTONDOWN:
            button = MouseButton.MIDDLE
            state = ButtonState.DOWN
        elif w_param == WM_MBUTTONUP:
            button = MouseButton.MIDDLE
            state = ButtonState.UP
        elif w_param == WM_MOUSEWHEEL:
            raw_delta: int = (ms.mouseData >> 16) & 0xFFFF
            wheel_delta = ctypes.c_short(raw_delta).value
        elif w_param in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            high_word: int = (ms.mouseData >> 16) & 0xFFFF
            button = MouseButton.X1 if high_word == XBUTTON1 else MouseButton.X2
            state = ButtonState.DOWN if w_param == WM_XBUTTONDOWN else ButtonState.UP

        event = RawMouseEvent(
            x=ms.pt.x,
            y=ms.pt.y,
            button=button,
            state=state,
            wheel_delta=wheel_delta,
            timestamp_ns=now_ns,
        )

        with self._lock:
            callbacks = list(self._mouse_callbacks)

        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                continue

        return _call_next_hook(hook, n_code, w_param, l_param)

    def _low_level_keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        hook: int = self._keyboard_hook or 0
        if n_code < 0:
            return _call_next_hook(hook, n_code, w_param, l_param)

        now_ns: int = time.perf_counter_ns()
        kb = KBDLLHOOKSTRUCT.from_address(l_param)

        if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            state = KeyState.KEY_DOWN
        elif w_param in (WM_KEYUP, WM_SYSKEYUP):
            state = KeyState.KEY_UP
        else:
            return _call_next_hook(hook, n_code, w_param, l_param)

        event = RawKeyboardEvent(
            vk_code=kb.vkCode,
            scan_code=kb.scanCode,
            state=state,
            is_extended=bool(kb.flags & LLKHF_EXTENDED),
            timestamp_ns=now_ns,
        )

        with self._lock:
            callbacks = list(self._keyboard_callbacks)

        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                continue

        return _call_next_hook(hook, n_code, w_param, l_param)
