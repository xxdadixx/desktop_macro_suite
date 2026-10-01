from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from src.core.exceptions import FrameCaptureError
from src.core.types import FrameCaptureProtocol, ImageBuffer, Rect2D

if TYPE_CHECKING:
    class _Cv2Protocol(Protocol):
        def imwrite(self, filename: str, img: ImageBuffer) -> bool: ...

    cv2: _Cv2Protocol
else:
    import cv2

__all__: Final[list[str]] = ["VisionCapture"]


class VisionCapture:
    """High-level frame capture service for template acquisition and debug snapshotting."""

    def __init__(self, capture_provider: FrameCaptureProtocol) -> None:
        self._provider: FrameCaptureProtocol = capture_provider

    @property
    def provider(self) -> FrameCaptureProtocol:
        return self._provider

    def capture(self, region: Rect2D | None = None) -> ImageBuffer:
        """Captures a desktop frame or sub-region."""
        return self._provider.capture(region=region)

    def save_template(
        self,
        region: Rect2D,
        output_path: str | Path,
    ) -> Path:
        """Captures a screen region and writes it to disk as a template image."""
        target_path: Path = Path(output_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        frame: ImageBuffer = self._provider.capture(region=region)
        success: bool = cv2.imwrite(str(target_path), frame)
        if not success:
            raise FrameCaptureError(
                f"Failed to write template image to disk at '{target_path}'"
            )

        return target_path

    def save_snapshot(
        self,
        output_path: str | Path,
        region: Rect2D | None = None,
    ) -> Path:
        """Captures the current screen and writes a diagnostic snapshot file."""
        target_path: Path = Path(output_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        frame: ImageBuffer = self._provider.capture(region=region)
        success: bool = cv2.imwrite(str(target_path), frame)
        if not success:
            raise FrameCaptureError(
                f"Failed to write screen snapshot to disk at '{target_path}'"
            )

        return target_path