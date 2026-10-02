from __future__ import annotations

import time
from typing import Final, Protocol, runtime_checkable

from src.core.ast import CvTriggerAction
from src.core.enums import TriggerComparison
from src.core.exceptions import MacroTimeoutError, TemplateMatchError
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


@runtime_checkable
class _VirtualOriginProtocol(Protocol):
    """Runtime-checkable protocol for capture providers supporting multi-monitor virtual desktop origins."""

    def get_virtual_origin(self) -> tuple[int, int]:
        raise NotImplementedError("Protocol implementation required")


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
        """Executes a single capture and template match check with virtual desktop offset correction."""
        target: str = action.image_base64 if action.image_base64 else action.template_path
        if not target.strip():
            raise TemplateMatchError(
                template_path=action.template_path,
                reason="CvTriggerAction has neither 'template_path' nor 'image_base64' defined.",
            )

        frame: ImageBuffer = self._capture.capture(region=region)
        try:
            raw_match: MatchResult = self._matcher.find(
                haystack=frame,
                template=target,
                threshold=action.confidence_threshold,
            )
        except (FileNotFoundError, ValueError) as err:
            raise TemplateMatchError(
                template_path=action.template_path,
                reason=str(err),
            ) from err

        if not raw_match.found or raw_match.region is None or raw_match.center is None:
            return raw_match

        # Determine capture surface origin across multi-monitor virtual desktop
        origin_x: int = 0
        origin_y: int = 0
        if region is not None:
            origin_x = region.x
            origin_y = region.y
        elif isinstance(self._capture, _VirtualOriginProtocol):
            origin_x, origin_y = self._capture.get_virtual_origin()

        adjusted_region = Rect2D(
            x=raw_match.region.x + origin_x,
            y=raw_match.region.y + origin_y,
            width=raw_match.region.width,
            height=raw_match.region.height,
        )
        adjusted_center = (
            raw_match.center[0] + origin_x,
            raw_match.center[1] + origin_y,
        )

        return MatchResult(
            found=True,
            confidence=raw_match.confidence,
            region=adjusted_region,
            center=adjusted_center,
        )

    def wait_for_trigger(
        self,
        action: CvTriggerAction,
        region: Rect2D | None = None,
        poll_interval_ms: Milliseconds = DEFAULT_POLL_INTERVAL_MS,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> MatchResult:
        """Blocks execution until the target visual condition matches or timeout expires."""
        start_time: float = time.monotonic()
        timeout: float = action.timeout_seconds
        wants_disappearance: bool = action.comparison == TriggerComparison.DISAPPEARS

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            result: MatchResult = self.evaluate_once(action, region=region)
            condition_met: bool = (not result.found) if wants_disappearance else result.found

            if condition_met:
                return result

            elapsed: float = time.monotonic() - start_time
            if elapsed >= timeout:
                raise MacroTimeoutError(
                    action_id=action.id,
                    timeout_seconds=timeout,
                )

            PreciseTimer.sleep_ms(poll_interval_ms, cancellation_token)