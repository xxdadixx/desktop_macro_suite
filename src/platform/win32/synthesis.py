import ctypes
from ctypes import wintypes
from collections.abc import Callable
from typing import Final, cast, override

from src.core.enums import ButtonState, KeyState, MouseButton
from src.core.exceptions import InputSynthesisError
from src.core.types import InputSynthesizerProtocol

INPUT_MOUSE: Final[int] = 0
INPUT_KEYBOARD: Final[int] = 1

MOUSEEVENTF_MOVE: Final[int] = 0x0001
MOUSEEVENTF_LEFTDOWN: Final[int] = 0x0002
MOUSEEVENTF_LEFTUP: Final[int] = 0x0004
MOUSEEVENTF_RIGHTDOWN: Final[int] = 0x0008
MOUSEEVENTF_RIGHTUP: Final[int] = 0x0010
MOUSEEVENTF_MIDDLEDOWN: Final[int] = 0x0020
MOUSEEVENTF_MIDDLEUP: Final[int] = 0x0040
MOUSEEVENTF_XDOWN: Final[int] = 0x0080
MOUSEEVENTF_XUP: Final[int] = 0x0100
MOUSEEVENTF_WHEEL: Final[int] = 0x0800
MOUSEEVENTF_VIRTUALDESK: Final[int] = 0x4000
MOUSEEVENTF_ABSOLUTE: Final[int] = 0x8000

KEYEVENTF_EXTENDEDKEY: Final[int] = 0x0001
KEYEVENTF_KEYUP: Final[int] = 0x0002
KEYEVENTF_SCANCODE: Final[int] = 0x0008

XBUTTON1: Final[int] = 0x0001
XBUTTON2: Final[int] = 0x0002

SM_XVIRTUALSCREEN: Final[int] = 76
SM_YVIRTUALSCREEN: Final[int] = 77
SM_CXVIRTUALSCREEN: Final[int] = 78
SM_CYVIRTUALSCREEN: Final[int] = 79
SM_CXSCREEN: Final[int] = 0
SM_CYSCREEN: Final[int] = 1

MAPVK_VK_TO_VSC: Final[int] = 0


class MOUSEINPUT(ctypes.Structure):
    dx: int
    dy: int
    mouseData: int
    dwFlags: int
    time: int
    dwExtraInfo: int
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    wVk: int
    wScan: int
    dwFlags: int
    time: int
    dwExtraInfo: int
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    uMsg: int
    wParamL: int
    wParamH: int
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    mi: MOUSEINPUT
    ki: KEYBDINPUT
    hi: HARDWAREINPUT
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    type: int
    u: INPUT_UNION
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
_user32.SendInput.restype = wintypes.UINT

_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int

_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT

_send_input: Callable[[int, ctypes.Array[INPUT], int], int] = cast(
    Callable[[int, ctypes.Array[INPUT], int], int], _user32.SendInput
)
_get_system_metrics: Callable[[int], int] = cast(
    Callable[[int], int], _user32.GetSystemMetrics
)
_map_virtual_key: Callable[[int, int], int] = cast(
    Callable[[int, int], int], _user32.MapVirtualKeyW
)


class Win32InputSynthesizer(InputSynthesizerProtocol):
    """Low-level Windows input synthesizer using SendInput and hardware scan codes."""

    def _dispatch(self, inputs: list[INPUT]) -> None:
        if not inputs:
            return

        count: int = len(inputs)
        input_array_cls = INPUT * count
        input_array = input_array_cls(*inputs)
        size: int = ctypes.sizeof(INPUT)

        sent: int = _send_input(count, input_array, size)
        if sent != count:
            err: int = ctypes.get_last_error()
            raise InputSynthesisError(
                expected_events=count,
                injected_events=sent,
                win32_error_code=err,
            )

    @override
    def send_mouse_move(self, x: int, y: int) -> None:
        vx: int = _get_system_metrics(SM_XVIRTUALSCREEN)
        vy: int = _get_system_metrics(SM_YVIRTUALSCREEN)
        vw: int = _get_system_metrics(SM_CXVIRTUALSCREEN)
        vh: int = _get_system_metrics(SM_CYVIRTUALSCREEN)

        if vw <= 0 or vh <= 0:
            vx = 0
            vy = 0
            vw = _get_system_metrics(SM_CXSCREEN)
            vh = _get_system_metrics(SM_CYSCREEN)

        norm_x: int = max(0, min(65535, int(((x - vx) * 65535) / max(1, vw - 1))))
        norm_y: int = max(0, min(65535, int(((y - vy) * 65535) / max(1, vh - 1))))

        event = INPUT()
        event.type = INPUT_MOUSE
        event.u.mi.dx = norm_x
        event.u.mi.dy = norm_y
        event.u.mi.mouseData = 0
        event.u.mi.dwFlags = (
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        )
        event.u.mi.time = 0
        event.u.mi.dwExtraInfo = 0

        self._dispatch([event])

    @override
    def send_mouse_button(self, button: MouseButton, state: ButtonState) -> None:
        events: list[INPUT] = []

        match button:
            case MouseButton.LEFT:
                down_flag = MOUSEEVENTF_LEFTDOWN
                up_flag = MOUSEEVENTF_LEFTUP
                data = 0
            case MouseButton.RIGHT:
                down_flag = MOUSEEVENTF_RIGHTDOWN
                up_flag = MOUSEEVENTF_RIGHTUP
                data = 0
            case MouseButton.MIDDLE:
                down_flag = MOUSEEVENTF_MIDDLEDOWN
                up_flag = MOUSEEVENTF_MIDDLEUP
                data = 0
            case MouseButton.X1:
                down_flag = MOUSEEVENTF_XDOWN
                up_flag = MOUSEEVENTF_XUP
                data = XBUTTON1
            case MouseButton.X2:
                down_flag = MOUSEEVENTF_XDOWN
                up_flag = MOUSEEVENTF_XUP
                data = XBUTTON2

        def create_event(flags: int, mouse_data: int) -> INPUT:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.u.mi.dx = 0
            inp.u.mi.dy = 0
            inp.u.mi.mouseData = mouse_data
            inp.u.mi.dwFlags = flags
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0
            return inp

        match state:
            case ButtonState.DOWN:
                events.append(create_event(down_flag, data))
            case ButtonState.UP:
                events.append(create_event(up_flag, data))
            case ButtonState.CLICK:
                events.append(create_event(down_flag, data))
                events.append(create_event(up_flag, data))
            case ButtonState.DOUBLE_CLICK:
                events.append(create_event(down_flag, data))
                events.append(create_event(up_flag, data))
                events.append(create_event(down_flag, data))
                events.append(create_event(up_flag, data))

        self._dispatch(events)

    @override
    def send_mouse_scroll(self, delta: int) -> None:
        event = INPUT()
        event.type = INPUT_MOUSE
        event.u.mi.dx = 0
        event.u.mi.dy = 0
        event.u.mi.mouseData = delta & 0xFFFFFFFF
        event.u.mi.dwFlags = MOUSEEVENTF_WHEEL
        event.u.mi.time = 0
        event.u.mi.dwExtraInfo = 0

        self._dispatch([event])

    @override
    def send_keyboard_key(
        self,
        vk_code: int,
        scan_code: int,
        state: KeyState,
    ) -> None:
        if scan_code == 0 and vk_code != 0:
            scan_code = _map_virtual_key(vk_code, MAPVK_VK_TO_VSC)

        base_flags: int = KEYEVENTF_SCANCODE
        if (scan_code & 0xE000) == 0xE000:
            base_flags |= KEYEVENTF_EXTENDEDKEY

        effective_scan: int = scan_code & 0xFF

        def create_key_event(flags: int) -> INPUT:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.u.ki.wVk = 0
            inp.u.ki.wScan = effective_scan
            inp.u.ki.dwFlags = flags
            inp.u.ki.time = 0
            inp.u.ki.dwExtraInfo = 0
            return inp

        events: list[INPUT] = []

        match state:
            case KeyState.KEY_DOWN:
                events.append(create_key_event(base_flags))
            case KeyState.KEY_UP:
                events.append(create_key_event(base_flags | KEYEVENTF_KEYUP))
            case KeyState.KEY_PRESS:
                events.append(create_key_event(base_flags))
                events.append(create_key_event(base_flags | KEYEVENTF_KEYUP))

        self._dispatch(events)