from __future__ import annotations

from pathlib import Path
import time
from typing import Final, Protocol, runtime_checkable

from src.core.ast import CvBranchCase, CvMultiTriggerAction, CvTriggerAction
from src.core.enums import CvSelectionStrategy, TriggerComparison
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
    """Evaluates visual conditions by polling screen captures against single or candidate template pools."""

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

    def _adjust_match_coordinates(
        self,
        raw_match: MatchResult,
        region: Rect2D | None,
    ) -> MatchResult:
        if not raw_match.found or raw_match.region is None or raw_match.center is None:
            return raw_match

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

    def evaluate_once(
        self,
        action: CvTriggerAction,
        region: Rect2D | None = None,
    ) -> MatchResult:
        """Executes a single capture and template match check with optional search bounding."""
        target: str = action.image_base64 if action.image_base64 else action.template_path
        if not target.strip():
            raise TemplateMatchError(
                template_path=action.template_path,
                reason="CvTriggerAction has neither 'template_path' nor 'image_base64' defined.",
            )

        # Restrict screen capture to local search bounding box if padding is configured
        search_region: Rect2D | None = region
        if (
            search_region is None
            and action.search_roi_padding > 0
            and action.crop_x is not None
            and action.crop_y is not None
            and action.crop_width is not None
            and action.crop_height is not None
        ):
            pad: int = action.search_roi_padding
            search_region = Rect2D(
                x=max(0, action.crop_x - pad),
                y=max(0, action.crop_y - pad),
                width=action.crop_width + (pad * 2),
                height=action.crop_height + (pad * 2),
            )

        frame: ImageBuffer = self._capture.capture(region=search_region)
        try:
            raw_match: MatchResult = self._matcher.find(
                haystack=frame,
                template=target,
                threshold=action.confidence_threshold,
                match_mode=action.match_mode.value,
            )
        except (FileNotFoundError, ValueError) as err:
            raise TemplateMatchError(
                template_path=action.template_path,
                reason=str(err),
            ) from err

        return self._adjust_match_coordinates(raw_match, search_region)

    def evaluate_multi(
        self,
        branches: list[CvBranchCase],
        region: Rect2D | None = None,
        strategy: CvSelectionStrategy = CvSelectionStrategy.FIRST_MATCH,
    ) -> tuple[CvBranchCase | None, MatchResult | None]:
        """Captures a single desktop frame and checks all candidate branches against that snapshot."""
        if not branches:
            return None, None

        frame: ImageBuffer = self._capture.capture(region=region)

        best_branch: CvBranchCase | None = None
        best_match: MatchResult | None = None
        highest_confidence: float = -1.0

        for branch in branches:
            target: str = branch.image_base64 if branch.image_base64 else branch.template_path
            if not target.strip():
                continue

            try:
                raw_match: MatchResult = self._matcher.find(
                    haystack=frame,
                    template=target,
                    threshold=branch.confidence_threshold,
                )
            except (FileNotFoundError, ValueError):
                continue

            adjusted_match = self._adjust_match_coordinates(raw_match, region)

            if adjusted_match.found:
                if strategy == CvSelectionStrategy.FIRST_MATCH:
                    return branch, adjusted_match

                if adjusted_match.confidence > highest_confidence:
                    highest_confidence = adjusted_match.confidence
                    best_branch = branch
                    best_match = adjusted_match

        return best_branch, best_match

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
        peak_confidence: float = 0.0

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            result: MatchResult = self.evaluate_once(action, region=region)
            peak_confidence = max(peak_confidence, result.confidence)
            condition_met: bool = (not result.found) if wants_disappearance else result.found

            if condition_met:
                return result

            elapsed: float = time.monotonic() - start_time
            if elapsed >= timeout:
                raise MacroTimeoutError(
                    action_id=action.id,
                    timeout_seconds=timeout,
                    peak_confidence=peak_confidence,
                    threshold=action.confidence_threshold,
                )

            PreciseTimer.sleep_ms(poll_interval_ms, cancellation_token)

    def _extract_candidate_branches(
        self, action: CvMultiTriggerAction
    ) -> list[CvBranchCase]:
        """Extracts candidate visual branches from either action.actions or legacy action.branches."""
        if action.actions:
            candidates: list[CvBranchCase] = []
            for child in action.actions:
                if isinstance(child, CvTriggerAction):
                    name_str: str = (
                        child.description
                        if child.description
                        else (
                            Path(child.template_path).stem
                            if child.template_path
                            else f"Target #{len(candidates) + 1}"
                        )
                    )
                    candidates.append(
                        CvBranchCase(
                            id=child.id,
                            name=name_str,
                            template_path=child.template_path,
                            image_base64=child.image_base64,
                            confidence_threshold=child.confidence_threshold,
                            mouse_action=child.mouse_action,
                            offset_x=child.offset_x,
                            offset_y=child.offset_y,
                            crop_x=child.crop_x,
                            crop_y=child.crop_y,
                            crop_width=child.crop_width,
                            crop_height=child.crop_height,
                            match_mode=child.match_mode,
                            search_roi_padding=child.search_roi_padding,
                            actions=[],
                        )
                    )
            if candidates:
                return candidates

        return action.branches

    def wait_for_multi_trigger(
        self,
        action: CvMultiTriggerAction,
        region: Rect2D | None = None,
        poll_interval_ms: Milliseconds = DEFAULT_POLL_INTERVAL_MS,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> tuple[CvBranchCase | None, MatchResult | None]:
        """Polls screen frames continuously until any candidate branch in the pool matches or timeout expires."""
        start_time: float = time.monotonic()
        timeout: float = action.timeout_seconds
        candidates: list[CvBranchCase] = self._extract_candidate_branches(action)

        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            matched_branch, match_res = self.evaluate_multi(
                branches=candidates,
                region=region,
                strategy=action.strategy,
            )

            if matched_branch is not None and match_res is not None and match_res.found:
                return matched_branch, match_res

            elapsed: float = time.monotonic() - start_time
            if elapsed >= timeout:
                return None, None

            PreciseTimer.sleep_ms(poll_interval_ms, cancellation_token)