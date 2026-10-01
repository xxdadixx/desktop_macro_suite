from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

import numpy as np

from src.core.types import ImageBuffer, Rect2D

DEFAULT_CONFIDENCE_THRESHOLD: Final[float] = 0.8
MATCH_METHOD: Final[int] = 5  # cv2.TM_CCOEFF_NORMED
CV_IMREAD_COLOR: Final[int] = 1  # cv2.IMREAD_COLOR
CV_COLOR_BGR2GRAY: Final[int] = 6  # cv2.COLOR_BGR2GRAY

if TYPE_CHECKING:
    class _Cv2Protocol(Protocol):
        def imread(
            self, filename: str, flags: int = ...
        ) -> ImageBuffer | None: ...

        def cvtColor(
            self, src: ImageBuffer, code: int
        ) -> ImageBuffer: ...

        def matchTemplate(
            self, image: ImageBuffer, templ: ImageBuffer, method: int
        ) -> object: ...

        def minMaxLoc(
            self, src: object
        ) -> tuple[float, float, tuple[int, int], tuple[int, int]]: ...

    cv2: _Cv2Protocol
else:
    import cv2


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Outcome of a template search operation within a desktop screen frame."""

    found: bool
    confidence: float
    region: Rect2D | None = None
    center: tuple[int, int] | None = None


class TemplateMatcher:
    """Computer vision engine for template matching with in-memory bitmap caching."""

    def __init__(self) -> None:
        self._template_cache: dict[str, ImageBuffer] = {}

    def load_template(self, template_path: str | Path) -> ImageBuffer:
        """Loads and caches a template image from disk as a contiguous BGR buffer."""
        path_str: str = str(Path(template_path).resolve())
        cached: ImageBuffer | None = self._template_cache.get(path_str)
        if cached is not None:
            return cached

        image: ImageBuffer | None = cv2.imread(path_str, CV_IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Failed to load template image at '{path_str}'")

        buffer: ImageBuffer = cast(ImageBuffer, np.ascontiguousarray(image))
        self._template_cache[path_str] = buffer
        return buffer

    def clear_cache(self) -> None:
        """Flushes all pre-loaded template images from memory."""
        self._template_cache.clear()

    def find(
        self,
        haystack: ImageBuffer,
        template: ImageBuffer | str | Path,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> MatchResult:
        """Searches for needle template within haystack image buffer."""
        template_buffer: ImageBuffer = (
            self.load_template(template)
            if isinstance(template, (str, Path))
            else template
        )

        haystack_h: int = int(haystack.shape[0])
        haystack_w: int = int(haystack.shape[1])
        template_h: int = int(template_buffer.shape[0])
        template_w: int = int(template_buffer.shape[1])

        if template_w > haystack_w or template_h > haystack_h:
            return MatchResult(found=False, confidence=0.0)

        haystack_gray: ImageBuffer = (
            cv2.cvtColor(haystack, CV_COLOR_BGR2GRAY)
            if haystack.ndim == 3
            else haystack
        )
        template_gray: ImageBuffer = (
            cv2.cvtColor(template_buffer, CV_COLOR_BGR2GRAY)
            if template_buffer.ndim == 3
            else template_buffer
        )

        match_matrix: object = cv2.matchTemplate(
            haystack_gray, template_gray, MATCH_METHOD
        )

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_matrix)
        _ = min_val
        _ = min_loc

        confidence: float = max(0.0, min(1.0, float(max_val)))
        if confidence < threshold:
            return MatchResult(found=False, confidence=confidence)

        best_x: int = int(max_loc[0])
        best_y: int = int(max_loc[1])

        region = Rect2D(
            x=best_x,
            y=best_y,
            width=template_w,
            height=template_h,
        )
        center: tuple[int, int] = (
            best_x + template_w // 2,
            best_y + template_h // 2,
        )

        return MatchResult(
            found=True,
            confidence=confidence,
            region=region,
            center=center,
        )