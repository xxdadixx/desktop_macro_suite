# pyright: reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false
from __future__ import annotations

import base64
from collections.abc import Callable
import ctypes
from pathlib import Path
import sys
import time
from typing import Final, cast

import cv2
from PySide6.QtCore import QObject, Signal, Slot

from src.core.ast import (
    ActionNode,
    CvBranchCase,
    CvMultiTriggerAction,
    CvTriggerAction,
    LoopContainerAction,
    MacroSequence,
)
from src.core.enums import KeyState
from src.core.exceptions import FrameCaptureError
from src.core.types import ImageBuffer, RawKeyboardEvent, Rect2D
from src.engine.orchestrator import MacroOrchestrator
from src.ui.models.telemetry_model import PlaybackTelemetry
from src.vision.capture import VisionCapture
from src.vision.matcher import MatchResult

__all__: Final[list[str]] = ["UIBridge"]

VK_SHIFT: Final[int] = 0x10
VK_CONTROL: Final[int] = 0x11
VK_C: Final[int] = 0x43
VK_G: Final[int] = 0x47
VK_F7: Final[int] = 0x76
VK_F8: Final[int] = 0x77

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _get_async_key_state: Callable[[int], int] = cast(
        Callable[[int], int], _user32.GetAsyncKeyState
    )

    def _is_vk_pressed(vk: int) -> bool:
        """Queries asynchronous hardware state to determine if a modifier key is physically held."""
        return bool(_get_async_key_state(vk) & 0x8000)
else:
    def _is_vk_pressed(vk: int) -> bool:
        _ = vk
        return False


class UIBridge(QObject):
    """Thread-safe facade bridging the engine orchestrator to the Qt main thread with global hotkeys."""

    recording_state_changed: Signal = Signal(bool)
    playback_state_changed: Signal = Signal(bool)
    telemetry_updated: Signal = Signal(PlaybackTelemetry)
    error_occurred: Signal = Signal(str)
    roi_capture_requested: Signal = Signal()
    coord_pick_requested: Signal = Signal()

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
        self._orchestrator.platform.hook_manager.register_keyboard_callback(
            self._on_global_keyboard_event
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

    def _on_global_keyboard_event(self, event: RawKeyboardEvent) -> None:
        """Evaluates OS-wide keystrokes and dispatches global hotkeys across all applications."""
        if event.state != KeyState.KEY_DOWN:
            return

        if self._orchestrator.is_playing:
            return

        vk = event.vk_code
        is_ctrl = _is_vk_pressed(VK_CONTROL)
        is_shift = _is_vk_pressed(VK_SHIFT)

        if (vk == VK_G and is_ctrl and not is_shift) or vk == VK_F7:
            self.roi_capture_requested.emit()
        elif (vk == VK_C and is_ctrl and is_shift) or vk == VK_F8:
            self.coord_pick_requested.emit()

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
        start_time: float = time.monotonic()

        flat_action_order: list[ActionNode] = []

        def _traverse(nodes: list[ActionNode]) -> None:
            for node in nodes:
                flat_action_order.append(node)
                if isinstance(node, LoopContainerAction):
                    _traverse(node.actions)
                elif isinstance(node, CvMultiTriggerAction):
                    for b in node.branches:
                        _traverse(b.actions)

        _traverse(sequence.actions)
        total_steps: int = len(flat_action_order)

        action_step_map: dict[str, int] = {
            act.id: idx + 1 for idx, act in enumerate(flat_action_order)
        }

        def _on_telemetry(action_id: str, elapsed_ms: float) -> None:
            _ = elapsed_ms
            step_idx: int = action_step_map.get(action_id, 0)
            telemetry = PlaybackTelemetry(
                is_playing=True,
                is_recording=False,
                current_step=step_idx,
                total_steps=total_steps,
                iteration=1,
                total_iterations=repeat_count,
                elapsed_seconds=round(time.monotonic() - start_time, 1),
                status_message=f"Executing step {step_idx}/{total_steps}",
            )
            self.telemetry_updated.emit(telemetry)

        def _on_done() -> None:
            self.playback_state_changed.emit(False)

        def _on_error(exc: Exception) -> None:
            self.playback_state_changed.emit(False)
            self.error_occurred.emit(str(exc))

        self._orchestrator.play_sequence_threaded(
            sequence=sequence,
            repeat_count=repeat_count,
            telemetry_callback=_on_telemetry,
            on_complete=_on_done,
            on_error=_on_error,
        )

    @Slot()
    def abort(self) -> None:
        self._orchestrator.abort("User requested UI abort")

    def test_cv_action(self, action: CvTriggerAction) -> MatchResult:
        """Executes a one-shot visual template match against the current screen for diagnostic verification."""
        return self._orchestrator.visual_evaluator.evaluate_once(action)

    def test_cv_multi_action(
        self,
        action: CvMultiTriggerAction,
    ) -> tuple[CvBranchCase | None, MatchResult | None]:
        """Executes a one-shot multi-candidate match against the current screen snapshot."""
        return self._orchestrator.visual_evaluator.evaluate_multi(
            branches=action.branches,
            strategy=action.strategy,
        )

    def save_template(self, region: Rect2D, output_path: str | Path) -> Path:
        return self._vision_capture.save_template(region, output_path)

    def capture_template_base64(self, region: Rect2D) -> str:
        """Captures a desktop ROI region and encodes it as an in-memory Base64 PNG string."""
        frame: ImageBuffer = self._vision_capture.capture(region=region)
        success, encoded_buf = cv2.imencode(".png", frame)
        if not success:
            raise FrameCaptureError("Failed to encode captured ROI to PNG format")
        return base64.b64encode(encoded_buf.tobytes()).decode("ascii")