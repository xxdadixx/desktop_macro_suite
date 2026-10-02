from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import random
import sys
import threading
import time
from typing import Final

from src.core.ast import (
    ActionNode,
    CvMultiTriggerAction,
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MacroSequence,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.enums import (
    ButtonState,
    CvFailurePolicy,
    CvMouseAction,
    LoopType,
    MouseButton,
)
from src.core.exceptions import ExecutionError, MacroTimeoutError
from src.core.types import (
    CancellationTokenProtocol,
    ExecutionTelemetryCallback,
    InputSynthesizerProtocol,
    Milliseconds,
)
from src.engine.timing import PreciseTimer
from src.vision.matcher import MatchResult
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


class _BreakLoopSignal(Exception):
    """Internal interpreter signal to break out of an active loop container."""


class MacroPlaybackEngine:
    """Executes MacroSequence AST nodes sequentially with sub-millisecond hardware dispatch, trace logging, and reentrancy safety."""

    def __init__(
        self,
        synthesizer: InputSynthesizerProtocol,
        cancellation_token: CancellationTokenProtocol | None = None,
        visual_evaluator: VisualTriggerEvaluator | None = None,
    ) -> None:
        self._synthesizer: InputSynthesizerProtocol = synthesizer
        self._token: CancellationTokenProtocol | None = cancellation_token
        self._visual_evaluator: VisualTriggerEvaluator | None = visual_evaluator
        self._execution_lock: threading.Lock = threading.Lock()
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
        """Synchronizes internal tracker coordinates with the physical operating system cursor."""
        cx, cy = _query_system_cursor_pos()
        self._current_mouse_x = cx
        self._current_mouse_y = cy

    def play(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        """Executes the macro sequence with reentrancy protection and end-to-end operation tracing."""
        if not self._execution_lock.acquire(blocking=False):
            raise ExecutionError(
                f"Cannot execute '{sequence.name}': Playback engine is already actively executing a sequence."
            )

        try:
            self._sync_cursor_position()
            total_actions: int = len(sequence.actions)
            iter_display: str = f"{repeat_count}" if repeat_count > 0 else "∞"
            logger.info(
                "Starting execution of '%s' [%d actions, %s iteration(s)]",
                sequence.name,
                total_actions,
                iter_display,
            )

            iteration: int = 0
            start_sequence_epoch: float = time.monotonic()

            while repeat_count <= 0 or iteration < repeat_count:
                self._check_cancellation()
                logger.info("--- Beginning iteration %d/%s ---", iteration + 1, iter_display)

                for step_idx, action in enumerate(sequence.actions, start=1):
                    self._check_cancellation()
                    if not action.enabled:
                        logger.debug(
                            "Step [%d/%d] Action '%s' (%s) is disabled. Skipping.",
                            step_idx,
                            total_actions,
                            action.id[:8],
                            action.action_type.value,
                        )
                        continue

                    logger.info(
                        "Step [%d/%d] Executing %s (ID: %s)",
                        step_idx,
                        total_actions,
                        action.action_type.value.upper(),
                        action.id[:8],
                    )

                    self._execute_action_with_telemetry(action, telemetry_callback)

                iteration += 1

            total_elapsed: float = time.monotonic() - start_sequence_epoch
            logger.info(
                "Playback completed successfully for '%s' in %.2fs (%d iteration(s)).",
                sequence.name,
                total_elapsed,
                iteration,
            )
        finally:
            self._execution_lock.release()

    def _execute_action_with_telemetry(
        self,
        node: ActionNode,
        telemetry_callback: ExecutionTelemetryCallback | None,
    ) -> None:
        start_epoch: float = time.monotonic()
        self.execute_action(node, telemetry_callback=telemetry_callback)
        elapsed_ms: float = (time.monotonic() - start_epoch) * 1000.0

        if telemetry_callback is not None:
            telemetry_callback(node.id, elapsed_ms)

    def execute_action(
        self,
        node: ActionNode,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        """Evaluates and dispatches a single AST action node exhaustively with trace logs."""
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
                self._execute_loop(action, telemetry_callback=telemetry_callback)
            case CvTriggerAction() as action:
                self._execute_cv_trigger(action)
            case CvMultiTriggerAction() as action:
                self._execute_cv_multi_trigger(action, telemetry_callback=telemetry_callback)

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
        mode_str: str = "relative offset" if action.is_relative else "absolute coordinates"

        if action.duration_ms <= 0.0:
            logger.debug(
                "Mouse move instant: -> (%d, %d) [%s]",
                target_x,
                target_y,
                mode_str,
            )
            self._synthesizer.send_mouse_move(target_x, target_y)
            self._current_mouse_x = target_x
            self._current_mouse_y = target_y
            return

        logger.debug(
            "Mouse move smooth: (%d, %d) -> (%d, %d) over %.1fms",
            self._current_mouse_x,
            self._current_mouse_y,
            target_x,
            target_y,
            action.duration_ms,
        )

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
            logger.debug("Mouse repositioning before click: -> (%d, %d)", action.x, action.y)
            self._synthesizer.send_mouse_move(action.x, action.y)
            self._current_mouse_x = action.x
            self._current_mouse_y = action.y

        logger.info(
            "Mouse button event: %s button -> %s at (%d, %d)",
            action.button.value.upper(),
            action.state.value.upper(),
            self._current_mouse_x,
            self._current_mouse_y,
        )
        self._synthesizer.send_mouse_button(action.button, action.state)

    def _execute_mouse_scroll(self, action: MouseScrollAction) -> None:
        direction_str: str = "horizontal" if action.horizontal else "vertical"
        logger.info("Mouse scroll event: delta=%d (%s)", action.delta, direction_str)
        self._synthesizer.send_mouse_scroll(action.delta, horizontal=action.horizontal)

    def _execute_keyboard_key(self, action: KeyboardKeyAction) -> None:
        key_label: str = action.key_name if action.key_name else f"0x{action.vk_code:02X}"
        logger.info(
            "Keyboard event: key='%s' (vk=0x%02X, scan=0x%02X, extended=%s) -> %s",
            key_label,
            action.vk_code,
            action.scan_code,
            action.is_extended,
            action.state.value.upper(),
        )
        self._synthesizer.send_keyboard_key(
            vk_code=action.vk_code,
            scan_code=action.scan_code,
            state=action.state,
            is_extended=action.is_extended,
        )

    def _execute_delay(self, action: DelayAction) -> None:
        effective_delay: Milliseconds = action.duration_ms
        jitter_str: str = ""
        if action.jitter_ms > 0.0:
            jitter: float = random.uniform(-action.jitter_ms, action.jitter_ms)
            effective_delay = max(0.0, effective_delay + jitter)
            jitter_str = f" [jitter offset: {jitter:+.1f}ms]"

        logger.info("Executing delay: %.1fms%s", effective_delay, jitter_str)
        PreciseTimer.sleep_ms(effective_delay, self._token)

    def _execute_loop(
        self,
        action: LoopContainerAction,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        logger.info(
            "Entering Loop block '%s' (type=%s, child_actions=%d)",
            action.id[:8],
            action.loop_type.value,
            len(action.actions),
        )

        match action.loop_type:
            case LoopType.COUNT:
                for cycle in range(action.iterations):
                    self._check_cancellation()
                    logger.debug("Loop iteration [%d/%d]", cycle + 1, action.iterations)
                    try:
                        for child in action.actions:
                            self._execute_action_with_telemetry(child, telemetry_callback)
                    except _BreakLoopSignal:
                        logger.info("Loop break signal received. Exiting loop '%s'.", action.id[:8])
                        break

            case LoopType.INFINITE:
                cycle_count: int = 0
                while True:
                    self._check_cancellation()
                    cycle_count += 1
                    logger.debug("Infinite loop cycle #%d", cycle_count)
                    try:
                        for child in action.actions:
                            self._execute_action_with_telemetry(child, telemetry_callback)
                    except _BreakLoopSignal:
                        logger.info("Loop break signal received. Exiting infinite loop '%s'.", action.id[:8])
                        break

            case LoopType.DURATION:
                start_epoch = time.monotonic()
                deadline = start_epoch + action.duration_seconds
                logger.info("Starting timed duration loop (limit: %.1fs)", action.duration_seconds)
                while time.monotonic() < deadline:
                    self._check_cancellation()
                    try:
                        for child in action.actions:
                            self._execute_action_with_telemetry(child, telemetry_callback)
                    except _BreakLoopSignal:
                        logger.info("Loop break signal received. Exiting duration loop '%s'.", action.id[:8])
                        break
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
                        logger.warning("While-CV loop '%s' exceeded timeout limit of %.1fs.", action.id[:8], action.timeout_seconds)
                        raise MacroTimeoutError(action.id, action.timeout_seconds)

                    res = self._visual_evaluator.evaluate_once(cv_check)
                    if not res.found:
                        logger.info("While-CV condition no longer matched. Terminating loop '%s'.", action.id[:8])
                        break

                    try:
                        for child in action.actions:
                            self._execute_action_with_telemetry(child, telemetry_callback)
                    except _BreakLoopSignal:
                        break

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
                        logger.warning("Until-CV loop '%s' exceeded timeout limit of %.1fs.", action.id[:8], action.timeout_seconds)
                        raise MacroTimeoutError(action.id, action.timeout_seconds)

                    res = self._visual_evaluator.evaluate_once(cv_check)
                    if res.found:
                        logger.info("Until-CV target detected (confidence=%.2f). Terminating loop '%s'.", res.confidence, action.id[:8])
                        break

                    try:
                        for child in action.actions:
                            self._execute_action_with_telemetry(child, telemetry_callback)
                    except _BreakLoopSignal:
                        break

                    if not action.actions:
                        PreciseTimer.sleep_ms(CV_POLL_INTERVAL_MS, self._token)

        logger.info("Exited Loop block '%s'.", action.id[:8])

    def _execute_cv_trigger(self, action: CvTriggerAction) -> None:
        if self._visual_evaluator is None:
            raise ExecutionError(
                f"Cannot execute visual trigger action '{action.id}': "
                "VisualTriggerEvaluator is not initialized or injected."
            )

        target_desc: str = f"file='{action.template_path}'" if action.template_path else "in-memory embedded image"
        logger.info(
            "Evaluating visual condition [%s] (policy=%s, comparison=%s, mouse_action=%s, threshold=%.2f, timeout=%.1fs)",
            target_desc,
            action.failure_policy.value,
            action.comparison.value,
            action.mouse_action.value,
            action.confidence_threshold,
            action.timeout_seconds,
        )

        try:
            match_res: MatchResult = self._visual_evaluator.wait_for_trigger(
                action=action,
                poll_interval_ms=CV_POLL_INTERVAL_MS,
                cancellation_token=self._token,
            )
        except MacroTimeoutError:
            match action.failure_policy:
                case CvFailurePolicy.ABORT:
                    logger.error(
                        "Visual match failed within %.1fs timeout. Policy=ABORT -> Raising MacroTimeoutError.",
                        action.timeout_seconds,
                    )
                    raise
                case CvFailurePolicy.SKIP:
                    logger.warning(
                        "Visual match not found within %.1fs timeout. Policy=SKIP -> Continuing sequence.",
                        action.timeout_seconds,
                    )
                    return
                case CvFailurePolicy.BREAK_LOOP:
                    logger.warning(
                        "Visual match not found within %.1fs timeout. Policy=BREAK_LOOP -> Breaking enclosing loop.",
                        action.timeout_seconds,
                    )
                    raise _BreakLoopSignal()

        if match_res.found and match_res.center is not None:
            self._dispatch_cv_interaction(
                center=match_res.center,
                offset_x=action.offset_x,
                offset_y=action.offset_y,
                mouse_action=action.mouse_action,
                confidence=match_res.confidence,
            )

    def _execute_cv_multi_trigger(
        self,
        action: CvMultiTriggerAction,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        if self._visual_evaluator is None:
            raise ExecutionError(
                f"Cannot execute multi-target visual action '{action.id}': "
                "VisualTriggerEvaluator is not initialized or injected."
            )

        logger.info(
            "Evaluating multi-target visual pool [%d candidate(s)] (strategy=%s, policy=%s, timeout=%.1fs)",
            len(action.branches),
            action.strategy.value,
            action.failure_policy.value,
            action.timeout_seconds,
        )

        matched_branch, match_res = self._visual_evaluator.wait_for_multi_trigger(
            action=action,
            poll_interval_ms=CV_POLL_INTERVAL_MS,
            cancellation_token=self._token,
        )

        if matched_branch is None or match_res is None or not match_res.found:
            match action.failure_policy:
                case CvFailurePolicy.ABORT:
                    logger.error(
                        "No visual candidates matched within %.1fs timeout. Policy=ABORT -> Raising MacroTimeoutError.",
                        action.timeout_seconds,
                    )
                    raise MacroTimeoutError(action.id, action.timeout_seconds)
                case CvFailurePolicy.SKIP:
                    logger.warning(
                        "No visual candidates matched within %.1fs timeout. Policy=SKIP -> Continuing sequence.",
                        action.timeout_seconds,
                    )
                    return
                case CvFailurePolicy.BREAK_LOOP:
                    logger.warning(
                        "No visual candidates matched within %.1fs timeout. Policy=BREAK_LOOP -> Breaking enclosing loop.",
                        action.timeout_seconds,
                    )
                    raise _BreakLoopSignal()

        logger.info(
            "Multi-CV match confirmed: Branch '%s' (Confidence: %.2f)",
            matched_branch.name,
            match_res.confidence,
        )

        if match_res.center is not None and matched_branch.mouse_action != CvMouseAction.NONE:
            self._dispatch_cv_interaction(
                center=match_res.center,
                offset_x=matched_branch.offset_x,
                offset_y=matched_branch.offset_y,
                mouse_action=matched_branch.mouse_action,
                confidence=match_res.confidence,
            )

        if matched_branch.actions:
            logger.info("Executing %d child action(s) for branch '%s'.", len(matched_branch.actions), matched_branch.name)
            for child in matched_branch.actions:
                self._execute_action_with_telemetry(child, telemetry_callback)

    def _dispatch_cv_interaction(
        self,
        center: tuple[int, int],
        offset_x: int,
        offset_y: int,
        mouse_action: CvMouseAction,
        confidence: float,
    ) -> None:
        target_x: int = center[0] + offset_x
        target_y: int = center[1] + offset_y

        logger.info(
            "Target location resolved! Confidence: %.2f (center: %s, offset: [%+d, %+d] -> target: (%d, %d))",
            confidence,
            center,
            offset_x,
            offset_y,
            target_x,
            target_y,
        )

        if mouse_action == CvMouseAction.NONE:
            self._current_mouse_x = target_x
            self._current_mouse_y = target_y
            return

        logger.info("Moving cursor to target coordinates: (%d, %d)", target_x, target_y)
        self._synthesizer.send_mouse_move(target_x, target_y)
        self._current_mouse_x = target_x
        self._current_mouse_y = target_y

        match mouse_action:
            case CvMouseAction.CLICK:
                logger.info("Clicking target at (%d, %d) [LEFT CLICK]", target_x, target_y)
                self._synthesizer.send_mouse_button(MouseButton.LEFT, ButtonState.CLICK)
            case CvMouseAction.DOUBLE_CLICK:
                logger.info("Double-clicking target at (%d, %d)", target_x, target_y)
                self._synthesizer.send_mouse_button(MouseButton.LEFT, ButtonState.DOUBLE_CLICK)
            case CvMouseAction.RIGHT_CLICK:
                logger.info("Right-clicking target at (%d, %d)", target_x, target_y)
                self._synthesizer.send_mouse_button(MouseButton.RIGHT, ButtonState.CLICK)
            case CvMouseAction.MOVE_ONLY:
                logger.info("Cursor positioned at (%d, %d) [Move only]", target_x, target_y)