from __future__ import annotations

import ctypes
from ctypes import wintypes
from collections.abc import Callable
from typing import Final, cast, override

import numpy as np

from src.core.exceptions import FrameCaptureError
from src.core.types import FrameCaptureProtocol, ImageBuffer, Rect2D

SRCCOPY: Final[int] = 0x00CC0020
CAPTUREBLT: Final[int] = 0x40000000
BI_RGB: Final[int] = 0
DIB_RGB_COLORS: Final[int] = 0

SM_XVIRTUALSCREEN: Final[int] = 76
SM_YVIRTUALSCREEN: Final[int] = 77
SM_CXVIRTUALSCREEN: Final[int] = 78
SM_CYVIRTUALSCREEN: Final[int] = 79
SM_CXSCREEN: Final[int] = 0
SM_CYSCREEN: Final[int] = 1


class BITMAPINFOHEADER(ctypes.Structure):
    biSize: int
    biWidth: int
    biHeight: int
    biPlanes: int
    biBitCount: int
    biCompression: int
    biSizeImage: int
    biXPelsPerMeter: int
    biYPelsPerMeter: int
    biClrUsed: int
    biClrImportant: int
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    bmiHeader: BITMAPINFOHEADER
    bmiColors: ctypes.Array[wintypes.DWORD]
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

_user32.GetDesktopWindow.argtypes = []
_user32.GetDesktopWindow.restype = wintypes.HWND

_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC

_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int

_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC

_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP

_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ

_gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]
_gdi32.BitBlt.restype = wintypes.BOOL

_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL

_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL

_gdi32.GdiFlush.argtypes = []
_gdi32.GdiFlush.restype = wintypes.BOOL

_gdi_flush: Callable[[], int] = cast(Callable[[], int], _gdi32.GdiFlush)

_get_desktop_window: Callable[[], int] = cast(
    Callable[[], int], _user32.GetDesktopWindow
)
_get_dc: Callable[[int], int] = cast(Callable[[int], int], _user32.GetDC)
_release_dc: Callable[[int, int], int] = cast(
    Callable[[int, int], int], _user32.ReleaseDC
)
_get_system_metrics: Callable[[int], int] = cast(
    Callable[[int], int], _user32.GetSystemMetrics
)
_create_compatible_dc: Callable[[int], int] = cast(
    Callable[[int], int], _gdi32.CreateCompatibleDC
)
_create_dib_section: Callable[
    [int, object, int, object, int | None, int],
    int,
] = cast(
    Callable[
        [int, object, int, object, int | None, int],
        int,
    ],
    _gdi32.CreateDIBSection,
)
_select_object: Callable[[int, int], int] = cast(
    Callable[[int, int], int], _gdi32.SelectObject
)
_bit_blt: Callable[[int, int, int, int, int, int, int, int, int], int] = cast(
    Callable[[int, int, int, int, int, int, int, int, int], int], _gdi32.BitBlt
)
_delete_object: Callable[[int], int] = cast(Callable[[int], int], _gdi32.DeleteObject)
_delete_dc: Callable[[int], int] = cast(Callable[[int], int], _gdi32.DeleteDC)


class Win32GdiCapture(FrameCaptureProtocol):
    """High-performance desktop frame provider using Win32 GDI DIB sections."""

    def get_virtual_origin(self) -> tuple[int, int]:
        """Returns the global top-left coordinate (vx, vy) of the virtual desktop surface."""
        vx: int = _get_system_metrics(SM_XVIRTUALSCREEN)
        vy: int = _get_system_metrics(SM_YVIRTUALSCREEN)
        vw: int = _get_system_metrics(SM_CXVIRTUALSCREEN)
        vh: int = _get_system_metrics(SM_CYVIRTUALSCREEN)

        if vw <= 0 or vh <= 0:
            return 0, 0
        return vx, vy

    @override
    def capture(self, region: Rect2D | None = None) -> ImageBuffer:
        vx: int = _get_system_metrics(SM_XVIRTUALSCREEN)
        vy: int = _get_system_metrics(SM_YVIRTUALSCREEN)
        vw: int = _get_system_metrics(SM_CXVIRTUALSCREEN)
        vh: int = _get_system_metrics(SM_CYVIRTUALSCREEN)

        if vw <= 0 or vh <= 0:
            vx = 0
            vy = 0
            vw = _get_system_metrics(SM_CXSCREEN)
            vh = _get_system_metrics(SM_CYSCREEN)

        if region is None:
            src_x: int = vx
            src_y: int = vy
            width: int = vw
            height: int = vh
        else:
            src_x = region.x
            src_y = region.y
            width = region.width
            height = region.height

        if width <= 0 or height <= 0:
            raise FrameCaptureError(f"Invalid capture dimensions: width={width}, height={height}")

        hwnd_desktop: int = _get_desktop_window()
        hdc_screen: int = _get_dc(hwnd_desktop)
        if hdc_screen == 0:
            raise FrameCaptureError("Failed to acquire desktop device context (GetDC)")

        hdc_mem: int = _create_compatible_dc(hdc_screen)
        if hdc_mem == 0:
            _ = _release_dc(hwnd_desktop, hdc_screen)
            raise FrameCaptureError("Failed to create compatible memory DC (CreateCompatibleDC)")

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # Top-down uncompressed DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = width * height * 4

        bits_ptr = ctypes.c_void_p()
        hbitmap: int = _create_dib_section(
            hdc_mem,
            ctypes.pointer(bmi),
            DIB_RGB_COLORS,
            ctypes.pointer(bits_ptr),
            None,
            0,
        )

        if hbitmap == 0 or bits_ptr.value is None:
            _ = _delete_dc(hdc_mem)
            _ = _release_dc(hwnd_desktop, hdc_screen)
            raise FrameCaptureError("Failed to allocate DIB section bitmap (CreateDIBSection)")

        old_bmp: int = _select_object(hdc_mem, hbitmap)

        try:
            success: int = _bit_blt(
                hdc_mem,
                0,
                0,
                width,
                height,
                hdc_screen,
                src_x,
                src_y,
                SRCCOPY | CAPTUREBLT,
            )
            if success == 0:
                raise FrameCaptureError("BitBlt screen raster transfer failed")

            _ = _gdi_flush()

            total_bytes: int = width * height * 4
            buffer_type = ctypes.c_uint8 * total_bytes
            raw_array = buffer_type.from_address(bits_ptr.value)
            bgra_array = np.frombuffer(raw_array, dtype=np.uint8).reshape((height, width, 4))
            bgr_array = np.ascontiguousarray(bgra_array[:, :, :3])
            return cast(ImageBuffer, bgr_array)
        finally:
            _ = _select_object(hdc_mem, old_bmp)
            _ = _delete_object(hbitmap)
            _ = _delete_dc(hdc_mem)
            _ = _release_dc(hwnd_desktop, hdc_screen)