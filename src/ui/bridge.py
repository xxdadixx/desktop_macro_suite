# pyright: reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false
from __future__ import annotations

import base64
from pathlib import Path
from typing import Final

import cv2
from PySide6.QtCore import QObject, Signal, Slot

from src.core.ast import MacroSequence
from src.core.exceptions import FrameCaptureError
from src.core.types import ImageBuffer, Rect2D
from src.engine.orchestrator import MacroOrchestrator
from src.ui.models.telemetry_model import PlaybackTelemetry
from src.vision.capture import VisionCapture

__all__: Final[list[str]] = ["UIBridge"]


class UIBridge(QObject):
    """Thread-safe facade bridging the engine orchestrator to the Qt main thread."""

    recording_state_changed: Signal = Signal(bool)
    playback_state_changed: Signal = Signal(bool)
    telemetry_updated: Signal = Signal(PlaybackTelemetry)
    error_occurred: Signal = Signal(str)

    def __init__(
        self,
        orchestrator: MacroOrchestrator,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._orchestrator: MacroOrchestrator = orchestrator
        self._vision_capture: VisionCapture = VisionCapture(
            capture_provider=orchestrator.platform.screen_capture
        )

    @property
    def is_recording(self) -> bool:
        return self._orchestrator.is_recording

    @property
    def is_playing(self) -> bool:
        return self._orchestrator.is_playing

    @property
    def vision_capture(self) -> VisionCapture:
        """Direct accessor for high-level vision capture operations."""
        return self._vision_capture

    @Slot()
    def start_recording(self) -> None:
        try:
            self._orchestrator.start_recording()
            self.recording_state_changed.emit(True)
        except Exception as e:
            self.error_occurred.emit(str(e))

    @Slot()
    def stop_recording(self) -> MacroSequence | None:
        try:
            seq: MacroSequence = self._orchestrator.stop_recording()
            self.recording_state_changed.emit(False)
            return seq
        except Exception as e:
            self.recording_state_changed.emit(False)
            self.error_occurred.emit(str(e))
            return None

    def start_playback(self, sequence: MacroSequence, repeat_count: int = 1) -> None:
        if self._orchestrator.is_playing:
            return

        self.playback_state_changed.emit(True)

        def _on_done() -> None:
            self.playback_state_changed.emit(False)

        def _on_error(exc: Exception) -> None:
            self.playback_state_changed.emit(False)
            self.error_occurred.emit(str(exc))

        self._orchestrator.play_sequence_threaded(
            sequence=sequence,
            repeat_count=repeat_count,
            on_complete=_on_done,
            on_error=_on_error,
        )

    @Slot()
    def abort(self) -> None:
        self._orchestrator.abort("User requested UI abort")

    def save_template(self, region: Rect2D, output_path: str | Path) -> Path:
        return self._vision_capture.save_template(region, output_path)

    def capture_template_base64(self, region: Rect2D) -> str:
        """Captures a desktop ROI region and encodes it as an in-memory Base64 PNG string."""
        frame: ImageBuffer = self._vision_capture.capture(region=region)
        success, encoded_buf = cv2.imencode(".png", frame)
        if not success:
            raise FrameCaptureError("Failed to encode captured ROI to PNG format")
        return base64.b64encode(encoded_buf.tobytes()).decode("ascii")