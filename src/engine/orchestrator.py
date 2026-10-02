from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Final, Self

from src.core.ast import MacroSequence
from src.core.exceptions import ExecutionAbortedError, ExecutionError
from src.core.types import ExecutionTelemetryCallback
from src.engine.capture_engine import InputCaptureEngine
from src.engine.kill_switch import (
    DEFAULT_ABORT_VK,
    CancellationToken,
    HardwareKillSwitch,
)
from src.engine.playback_engine import MacroPlaybackEngine
from src.engine.scheduler import MacroScheduler
from src.platform import get_platform_provider
from src.platform.base import BasePlatformProvider
from src.vision.trigger import VisualTriggerEvaluator

logger: logging.Logger = logging.getLogger(__name__)

__all__: Final[list[str]] = ["MacroOrchestrator"]


class MacroOrchestrator:
    """Central engine coordinator managing platform subsystems, recording, playback, and scheduling with structured logging."""

    def __init__(
        self,
        platform_provider: BasePlatformProvider | None = None,
        abort_vk_code: int = DEFAULT_ABORT_VK,
        visual_evaluator: VisualTriggerEvaluator | None = None,
    ) -> None:
        self._platform: BasePlatformProvider = (
            platform_provider if platform_provider is not None else get_platform_provider()
        )
        self._cancellation_token: CancellationToken = CancellationToken()
        self._kill_switch: HardwareKillSwitch = HardwareKillSwitch(
            hook_manager=self._platform.hook_manager,
            token=self._cancellation_token,
            abort_vk_code=abort_vk_code,
        )
        self._capture_engine: InputCaptureEngine = InputCaptureEngine(
            hook_manager=self._platform.hook_manager,
            abort_vk_code=abort_vk_code,
        )
        self._visual_evaluator: VisualTriggerEvaluator = (
            visual_evaluator
            if visual_evaluator is not None
            else VisualTriggerEvaluator(
                capture_provider=self._platform.screen_capture
            )
        )
        self._playback_engine: MacroPlaybackEngine = MacroPlaybackEngine(
            synthesizer=self._platform.synthesizer,
            cancellation_token=self._cancellation_token,
            visual_evaluator=self._visual_evaluator,
        )
        self._scheduler: MacroScheduler = MacroScheduler(
            playback_engine=self._playback_engine,
            cancellation_token=self._cancellation_token,
        )

        self._state_lock: threading.Lock = threading.Lock()
        self._is_playing: bool = False
        self._initialized: bool = False

    @property
    def platform(self) -> BasePlatformProvider:
        return self._platform

    @property
    def cancellation_token(self) -> CancellationToken:
        return self._cancellation_token

    @property
    def kill_switch(self) -> HardwareKillSwitch:
        return self._kill_switch

    @property
    def capture_engine(self) -> InputCaptureEngine:
        return self._capture_engine

    @property
    def playback_engine(self) -> MacroPlaybackEngine:
        return self._playback_engine

    @property
    def scheduler(self) -> MacroScheduler:
        return self._scheduler

    @property
    def is_recording(self) -> bool:
        return self._capture_engine.is_recording

    @property
    def is_playing(self) -> bool:
        with self._state_lock:
            return self._is_playing

    @property
    def visual_evaluator(self) -> VisualTriggerEvaluator:
        return self._visual_evaluator

    def initialize(self) -> None:
        """Initializes low-level platform hooks, timer resolution, and the kill-switch."""
        if self._initialized:
            return

        logger.info("Initializing MacroOrchestrator subsystems (%s)...", type(self._platform).__name__)
        self._platform.initialize()
        self._kill_switch.activate()
        self._scheduler.start()
        self._initialized = True
        logger.info("MacroOrchestrator initialization complete. Emergency Kill-Switch active (F12).")

    def shutdown(self) -> None:
        """Stops background tasks, cancels active playback, and unhooks OS listeners."""
        if not self._initialized:
            return

        logger.info("Shutting down MacroOrchestrator...")
        self.abort("Engine shutdown requested")

        if self._capture_engine.is_recording:
            logger.info("Halting active input capture session during shutdown.")
            _ = self._capture_engine.stop_recording()

        self._scheduler.stop()
        self._kill_switch.deactivate()
        self._platform.shutdown()
        self._initialized = False
        logger.info("MacroOrchestrator shutdown complete.")

    def __enter__(self) -> Self:
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.shutdown()

    def start_recording(self) -> None:
        """Begins recording hardware input events into an AST sequence."""
        with self._state_lock:
            if self._is_playing:
                raise ExecutionError("Cannot record inputs while macro playback is active")
            if self._capture_engine.is_recording:
                return

        logger.info("Starting input recording session...")
        self._cancellation_token.reset()
        self._capture_engine.start_recording()

    def stop_recording(
        self,
        name: str = "Recorded Macro",
        description: str = "",
        author: str = "",
    ) -> MacroSequence:
        """Stops recording and returns the compiled MacroSequence."""
        if not self._capture_engine.is_recording:
            raise ExecutionError("Recording is not currently active")

        actions = self._capture_engine.stop_recording()
        logger.info("Input recording stopped. Captured %d hardware input actions.", len(actions))
        return self._capture_engine.to_macro_sequence(
            name=name,
            description=description,
            author=author,
        )

    def play_sequence(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
    ) -> None:
        """Synchronously executes the given macro sequence with optional telemetry tracking."""
        with self._state_lock:
            if self._is_playing:
                raise ExecutionError("Playback is already in progress")
            if self._capture_engine.is_recording:
                raise ExecutionError("Cannot play sequence while input recording is active")
            self._is_playing = True

        logger.info("Dispatching synchronous sequence execution: '%s'", sequence.name)
        self._cancellation_token.reset()
        try:
            self._playback_engine.play(
                sequence=sequence,
                repeat_count=repeat_count,
                telemetry_callback=telemetry_callback,
            )
        except ExecutionAbortedError as exc:
            logger.info("Synchronous playback halted gracefully: %s", exc)
            raise
        finally:
            with self._state_lock:
                self._is_playing = False

    def play_sequence_threaded(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
        telemetry_callback: ExecutionTelemetryCallback | None = None,
        on_complete: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Dispatches sequence playback in a dedicated background daemon thread with telemetry."""
        def _worker() -> None:
            with self._state_lock:
                if self._is_playing:
                    if on_error is not None:
                        on_error(ExecutionError("Playback is already in progress"))
                    return
                if self._capture_engine.is_recording:
                    if on_error is not None:
                        on_error(ExecutionError("Cannot play sequence while input recording is active"))
                    return
                self._is_playing = True

            logger.info("Playback background worker spawned for sequence '%s'.", sequence.name)
            self._cancellation_token.reset()
            try:
                self._playback_engine.play(
                    sequence=sequence,
                    repeat_count=repeat_count,
                    telemetry_callback=telemetry_callback,
                )
                if on_complete is not None:
                    on_complete()
            except ExecutionAbortedError as exc:
                logger.info("Playback halted gracefully: %s", exc)
                if on_error is not None:
                    on_error(exc)
            except Exception as exc:
                logger.error("Playback terminated with exception: %s", exc, exc_info=True)
                if on_error is not None:
                    on_error(exc)
            finally:
                with self._state_lock:
                    self._is_playing = False

        thread = threading.Thread(
            target=_worker,
            name="MacroPlaybackWorker",
            daemon=True,
        )
        thread.start()
        return thread

    def abort(self, reason: str = "Manual execution abort requested") -> None:
        """Cancels all active playbacks and pending scheduled tasks."""
        logger.warning("Aborting macro execution: %s", reason)
        self._cancellation_token.cancel(reason)