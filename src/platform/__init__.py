from __future__ import annotations

import sys
from typing import Final

from src.core.exceptions import PlatformError
from src.platform.base import BasePlatformProvider

__all__: Final[list[str]] = [
    "BasePlatformProvider",
    "get_platform_provider",
]


def get_platform_provider() -> BasePlatformProvider:
    """Instantiates and returns the platform-specific provider for the active operating system."""
    current_platform: str = sys.platform
    if current_platform == "win32":
        from src.platform.win32 import Win32PlatformProvider

        return Win32PlatformProvider()

    raise PlatformError(
        f"Unsupported operating system platform: '{current_platform}'. Currently, only Windows ('win32') is supported."
    )