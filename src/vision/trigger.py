from __future__ import annotations

import time
from typing import Final

from src.core.ast import CvTriggerAction
from src.core.exceptions import MacroTimeoutError
from src.core.types import (
    CancellationTokenProtocol,
    FrameCaptureProtocol,
    ImageBuffer,
    Milliseconds,
    Rect2D,
)
from src.engine.timing import PreciseTimer
from src.vision.matcher import MatchResult, TemplateMatcher

__all__: Final[list[str]] = ["VisualTriggerEvaluator"]

DEFAULT_POLL_INTERVAL_MS: Final[Milliseconds] = 50.0


class VisualTriggerEvaluator:
    """Evaluates visual conditions by polling screen captures against template images."""

    def __init__(
        self,
        capture_provider: FrameCaptureProtocol,
        matcher: TemplateMatcher | None = None,
    ) -> None:
        self._capture: FrameCaptureProtocol = capture_provider
        self._matcher: TemplateMatcher = (
            matcher if matcher is not None else TemplateMatcher()
        )

    @property
    def matcher(self) -> TemplateMatcher:
        return self._matcher

    def evaluate_once(
        self,
        action: CvTriggerAction,
        region: Rect2D | None = None,
    ) -> MatchResult:
        """Executes a single capture and template match check."""
        frame: ImageBuffer = self._capture.capture(region=region)
        return self._matcher.find(
            haystack=frame,
            template=action.template_path,
            threshold=action.confidence_threshold,
        )

    def wait_for_trigger(
        self,
        action: CvTriggerAction,
        region: Rect2D | None = None,
        poll_interval_ms: Milliseconds = DEFAULT_POLL_INTERVAL_MS,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> MatchResult:
        """Blocks execution until the target visual template matches or timeout expires."""
        start_time: float = time.monotonic()
        timeout: float = action.timeout_seconds

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            result: MatchResult = self.evaluate_once(action, region=region)
            if result.found:
                return result

            elapsed: float = time.monotonic() - start_time
            if elapsed >= timeout:
                raise MacroTimeoutError(
                    action_id=action.id,
                    timeout_seconds=timeout,
                )

            PreciseTimer.sleep_ms(poll_interval_ms, cancellation_token)