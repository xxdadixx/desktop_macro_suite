from __future__ import annotations

from typing import TYPE_CHECKING, Final

from .bridge import UIBridge

if TYPE_CHECKING:
    from .app import run_app
else:
    def __getattr__(name: str) -> object:
        if name == "run_app":
            from .app import run_app
            return run_app
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__: Final[list[str]] = [
    "UIBridge",
    "run_app",
]