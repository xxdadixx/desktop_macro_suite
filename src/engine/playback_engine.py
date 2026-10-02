from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import random
import sys
import time
from typing import Final

from src.core.ast import (
    ActionNode,
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MacroSequence,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.enums import LoopType
from src.core.exceptions import ExecutionError, MacroTimeoutError
from src.core.types import (
    CancellationTokenProtocol,
    ExecutionTelemetryCallback,
    InputSynthesizerProtocol,
    Milliseconds,
)
from src.engine.timing import PreciseTimer
from src.vision.trigger import VisualTriggerEvaluator

logger: logging.Logger = logging.getLogger(__name__)

MOUSE_INTERPOLATION_STEP_MS: Final[float] = 5.0
CV_POLL_INTERVAL_MS: Final[float] = 50.0


def _query_system_cursor_pos() -> tuple[int, int]:
    """Retrieves current operating system cursor coordinates via Win32 GetCursorPos."""
    if sys.platform == "win32":
        try:
            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return int(point.x), int(point.y)
        except Exception:
            pass
    return 0, 0


class MacroPlaybackEngine:
    """Executes MacroSequence AST nodes sequentially with sub-millisecond hardware dispatch."""

    def __init__(
        self,
        synthesizer: InputSynthesizerProtocol,
        cancellation_token: CancellationTokenProtocol | None = None,
        visual_evaluator: VisualTriggerEvaluator | None = None,
    ) -> None:
        self._synthesizer: InputSynthesizerProtocol = synthesizer
        self._token: CancellationTokenProtocol | None = cancellation_token
        self._visual_evaluator: VisualTriggerEvaluator | None = visual_evaluator
        self._current_mouse_x: int = 0
        self._current_mouse_y: int = 0
        self._sync_cursor_position()

    @property
    def visual_evaluator(self) -> VisualTriggerEvaluator | None:
        return self._visual_evaluator

    @visual_evaluator.setter
    def visual_evaluator(self, evaluator: VisualTriggerEvaluator | None) -> None:
        self._visual_evaluator = evaluator

    def _sync_cursor_position(self) -> None:
        cx, cy = _query_system_cursor_pos()
        self._current_mouse_x = cx
        self._current_mouse_y = cy

    def play(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        """Executes the macro sequence. Set repeat_count <= 0 to loop indefinitely."""
        self._sync_cursor_position()
        iteration: int = 0
        while repeat_count <= 0 or iteration < repeat_count:
            self._check_cancellation()
            for action in sequence.actions:
                self._check_cancellation()
                if not action.enabled:
                    continue

                start_epoch = time.monotonic()
                self.execute_action(action)
                if telemetry_callback is not None:
                    elapsed_ms = (time.monotonic() - start_epoch) * 1000.0
                    telemetry_callback(action.id, elapsed_ms)

            iteration += 1

    def execute_action(self, node: ActionNode) -> None:
        """Evaluates and dispatches a single AST action node exhaustively."""
        self._check_cancellation()
        if not node.enabled:
            return

        match node:
            case MouseMoveAction() as action:
                self._execute_mouse_move(action)
            case MouseButtonAction() as action:
                self._execute_mouse_button(action)
            case MouseScrollAction() as action:
                self._execute_mouse_scroll(action)
            case KeyboardKeyAction() as action:
                self._execute_keyboard_key(action)
            case DelayAction() as action:
                self._execute_delay(action)
            case LoopContainerAction() as action:
                self._execute_loop(action)
            case CvTriggerAction() as action:
                self._execute_cv_trigger(action)

    def _check_cancellation(self) -> None:
        if self._token is not None:
            self._token.raise_if_cancelled()

    def _execute_mouse_move(self, action: MouseMoveAction) -> None:
        target_x: int = (
            self._current_mouse_x + action.x if action.is_relative else action.x
        )
        target_y: int = (
            self._current_mouse_y + action.y if action.is_relative else action.y
        )

        if action.duration_ms <= 0.0:
            self._synthesizer.send_mouse_move(target_x, target_y)
            self._current_mouse_x = target_x
            self._current_mouse_y = target_y
            return

        start_x: int = self._current_mouse_x
        start_y: int = self._current_mouse_y
        total_steps: int = max(
            1, int(action.duration_ms / MOUSE_INTERPOLATION_STEP_MS)
        )
        step_delay: Milliseconds = action.duration_ms / total_steps

        for step in range(1, total_steps):
            self._check_cancellation()
            progress: float = step / total_steps
            intermediate_x: int = int(start_x + (target_x - start_x) * progress)
            intermediate_y: int = int(start_y + (target_y - start_y) * progress)

            self._synthesizer.send_mouse_move(intermediate_x, intermediate_y)
            self._current_mouse_x = intermediate_x
            self._current_mouse_y = intermediate_y

            PreciseTimer.sleep_ms(step_delay, self._token)

        self._synthesizer.send_mouse_move(target_x, target_y)
        self._current_mouse_x = target_x
        self._current_mouse_y = target_y

    def _execute_mouse_button(self, action: MouseButtonAction) -> None:
        if action.x is not None and action.y is not None:
            self._synthesizer.send_mouse_move(action.x, action.y)
            self._current_mouse_x = action.x
            self._current_mouse_y = action.y

        self._synthesizer.send_mouse_button(action.button, action.state)

    def _execute_mouse_scroll(self, action: MouseScrollAction) -> None:
        self._synthesizer.send_mouse_scroll(action.delta, horizontal=action.horizontal)

    def _execute_keyboard_key(self, action: KeyboardKeyAction) -> None:
        self._synthesizer.send_keyboard_key(
            vk_code=action.vk_code,
            scan_code=action.scan_code,
            state=action.state,
        )

    def _execute_delay(self, action: DelayAction) -> None:
        effective_delay: Milliseconds = action.duration_ms
        if action.jitter_ms > 0.0:
            jitter: float = random.uniform(-action.jitter_ms, action.jitter_ms)
            effective_delay = max(0.0, effective_delay + jitter)

        PreciseTimer.sleep_ms(effective_delay, self._token)

    def _execute_loop(self, action: LoopContainerAction) -> None:
        match action.loop_type:
            case LoopType.COUNT:
                for _ in range(action.iterations):
                    self._check_cancellation()
                    for child in action.actions:
                        self.execute_action(child)

            case LoopType.INFINITE:
                while True:
                    self._check_cancellation()
                    for child in action.actions:
                        self.execute_action(child)

            case LoopType.DURATION:
                start_epoch = time.monotonic()
                deadline = start_epoch + action.duration_seconds
                while time.monotonic() < deadline:
                    self._check_cancellation()
                    for child in action.actions:
                        self.execute_action(child)
                    if not action.actions:
                        PreciseTimer.sleep_ms(1.0, self._token)

            case LoopType.WHILE_CV:
                if self._visual_evaluator is None:
                    raise ExecutionError(
                        f"Cannot evaluate while-cv loop '{action.id}': Visual evaluator not initialized."
                    )
                cv_check = CvTriggerAction(
                    template_path=action.template_path,
                    image_base64=action.image_base64,
                    confidence_threshold=action.confidence_threshold,
                    timeout_seconds=action.timeout_seconds,
                )
                start_time = time.monotonic()
                while True:
                    self._check_cancellation()
                    if (time.monotonic() - start_time) >= action.timeout_seconds:
                        raise MacroTimeoutError(action.id, action.timeout_seconds)

                    res = self._visual_evaluator.evaluate_once(cv_check)
                    if not res.found:
                        break

                    for child in action.actions:
                        self.execute_action(child)

                    if not action.actions:
                        PreciseTimer.sleep_ms(CV_POLL_INTERVAL_MS, self._token)

            case LoopType.UNTIL_CV:
                if self._visual_evaluator is None:
                    raise ExecutionError(
                        f"Cannot evaluate until-cv loop '{action.id}': Visual evaluator not initialized."
                    )
                cv_check = CvTriggerAction(
                    template_path=action.template_path,
                    image_base64=action.image_base64,
                    confidence_threshold=action.confidence_threshold,
                    timeout_seconds=action.timeout_seconds,
                )
                start_time = time.monotonic()
                while True:
                    self._check_cancellation()
                    if (time.monotonic() - start_time) >= action.timeout_seconds:
                        raise MacroTimeoutError(action.id, action.timeout_seconds)

                    res = self._visual_evaluator.evaluate_once(cv_check)
                    if res.found:
                        break

                    for child in action.actions:
                        self.execute_action(child)

                    if not action.actions:
                        PreciseTimer.sleep_ms(CV_POLL_INTERVAL_MS, self._token)

    def _execute_cv_trigger(self, action: CvTriggerAction) -> None:
        if self._visual_evaluator is None:
            raise ExecutionError(
                f"Cannot execute visual trigger action '{action.id}': "
                "VisualTriggerEvaluator is not initialized or injected."
            )

        logger.debug(
            "Polling visual trigger for template '%s' (timeout: %.2fs, threshold: %.2f)",
            action.template_path,
            action.timeout_seconds,
            action.confidence_threshold,
        )

        _ = self._visual_evaluator.wait_for_trigger(
            action=action,
            poll_interval_ms=CV_POLL_INTERVAL_MS,
            cancellation_token=self._token,
        )