from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import Final, Self

from src.core.ast import MacroSequence
from src.core.exceptions import ExecutionError
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

__all__: Final[list[str]] = ["MacroOrchestrator"]


class MacroOrchestrator:
    """Central engine coordinator managing platform subsystems, recording, playback, and scheduling."""

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
            hook_manager=self._platform.hook_manager
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

        self._platform.initialize()
        self._kill_switch.activate()
        self._scheduler.start()
        self._initialized = True

    def shutdown(self) -> None:
        """Stops background tasks and unhooks low-level platform listeners."""
        if not self._initialized:
            return

        if self._capture_engine.is_recording:
            _ = self._capture_engine.stop_recording()

        self._scheduler.stop()
        self._kill_switch.deactivate()
        self._platform.shutdown()
        self._initialized = False

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

        _ = self._capture_engine.stop_recording()
        return self._capture_engine.to_macro_sequence(
            name=name,
            description=description,
            author=author,
        )

    def play_sequence(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
    ) -> None:
        """Synchronously executes the given macro sequence."""
        with self._state_lock:
            if self._is_playing:
                raise ExecutionError("Playback is already in progress")
            if self._capture_engine.is_recording:
                raise ExecutionError("Cannot play sequence while input recording is active")
            self._is_playing = True

        self._cancellation_token.reset()
        try:
            self._playback_engine.play(sequence, repeat_count=repeat_count)
        finally:
            with self._state_lock:
                self._is_playing = False

    def play_sequence_threaded(
        self,
        sequence: MacroSequence,
        repeat_count: int = 1,
        on_complete: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Dispatches sequence playback in a dedicated background daemon thread."""
        def _worker() -> None:
            try:
                self.play_sequence(sequence, repeat_count=repeat_count)
                if on_complete is not None:
                    on_complete()
            except Exception as exc:
                if on_error is not None:
                    on_error(exc)

        thread = threading.Thread(
            target=_worker,
            name="MacroPlaybackWorker",
            daemon=True,
        )
        thread.start()
        return thread

    def abort(self, reason: str = "Manual execution abort requested") -> None:
        """Cancels all active playbacks and pending scheduled tasks."""
        self._cancellation_token.cancel(reason)