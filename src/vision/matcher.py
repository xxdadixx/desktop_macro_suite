from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

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

        def imdecode(
            self, buf: ImageBuffer, flags: int
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
    """Computer vision engine for template matching with pre-computed dual-buffer caching."""

    def __init__(self) -> None:
        self._template_cache: dict[str, tuple[ImageBuffer, ImageBuffer]] = {}

    def _hash_payload(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def load_template(self, template_path: str | Path) -> tuple[ImageBuffer, ImageBuffer]:
        """Loads a template image from disk, caching both BGR and Grayscale representations."""
        path_str: str = str(Path(template_path).resolve())
        cached = self._template_cache.get(path_str)
        if cached is not None:
            return cached

        image: ImageBuffer | None = cv2.imread(path_str, CV_IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Failed to load template image at '{path_str}'")

        bgr_buf: ImageBuffer = np.ascontiguousarray(image)
        gray_buf: ImageBuffer = np.ascontiguousarray(cv2.cvtColor(bgr_buf, CV_COLOR_BGR2GRAY))
        entry = (bgr_buf, gray_buf)
        self._template_cache[path_str] = entry
        return entry

    def clear_cache(self) -> None:
        """Flushes all pre-loaded template images from memory."""
        self._template_cache.clear()

    def load_from_base64(self, b64_data: str) -> tuple[ImageBuffer, ImageBuffer]:
        """Decodes a Base64 string, caching both BGR and Grayscale representations."""
        cleaned_b64: str = b64_data.strip()
        if not cleaned_b64:
            raise ValueError("Base64 template data cannot be empty.")

        # Strip RFC 2397 Data URI headers if present
        if cleaned_b64.startswith("data:") and "," in cleaned_b64:
            cleaned_b64 = cleaned_b64.split(",", 1)[1].strip()

        cache_key = self._hash_payload(cleaned_b64)
        cached = self._template_cache.get(cache_key)
        if cached is not None:
            return cached

        raw_bytes: bytes = base64.b64decode(cleaned_b64)
        if not raw_bytes:
            raise ValueError("Decoded Base64 buffer contains 0 bytes.")

        arr: ImageBuffer = np.frombuffer(raw_bytes, dtype=np.uint8)
        decoded: ImageBuffer | None = cv2.imdecode(arr, CV_IMREAD_COLOR)
        if decoded is None:
            raise ValueError("Failed to decode in-memory template image from Base64")

        bgr_buf: ImageBuffer = np.ascontiguousarray(decoded)
        gray_buf: ImageBuffer = np.ascontiguousarray(cv2.cvtColor(bgr_buf, CV_COLOR_BGR2GRAY))
        entry = (bgr_buf, gray_buf)
        self._template_cache[cache_key] = entry
        return entry

    def find(
        self,
        haystack: ImageBuffer,
        template: ImageBuffer | str | Path,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> MatchResult:
        """Searches for needle template within haystack image buffer."""
        template_gray: ImageBuffer
        template_w: int
        template_h: int

        if isinstance(template, Path):
            _, template_gray = self.load_template(template)
            template_h, template_w = int(template_gray.shape[0]), int(template_gray.shape[1])
        elif isinstance(template, str):
            clean_str: str = template.strip()
            if not clean_str:
                raise ValueError("Template target identifier or Base64 payload cannot be empty.")

            # Identify and decode Data URI schemes directly
            if clean_str.startswith("data:") and "," in clean_str:
                _, template_gray = self.load_from_base64(clean_str)
            else:
                path_candidate = Path(clean_str)
                if path_candidate.is_file():
                    _, template_gray = self.load_template(path_candidate)
                elif clean_str.startswith("iVBORw0KGgo") or len(clean_str) > 260:
                    _, template_gray = self.load_from_base64(clean_str)
                else:
                    if any(sep in clean_str for sep in ("/", "\\", ".")):
                        raise FileNotFoundError(f"Template image file not found at '{clean_str}'")
                    _, template_gray = self.load_from_base64(clean_str)

            template_h, template_w = int(template_gray.shape[0]), int(template_gray.shape[1])
        else:
            if template.ndim == 3:
                template_gray = np.ascontiguousarray(cv2.cvtColor(template, CV_COLOR_BGR2GRAY))
            else:
                template_gray = np.ascontiguousarray(template)
            template_h, template_w = int(template.shape[0]), int(template.shape[1])

        haystack_h: int = int(haystack.shape[0])
        haystack_w: int = int(haystack.shape[1])

        if template_w > haystack_w or template_h > haystack_h:
            return MatchResult(found=False, confidence=0.0)

        haystack_gray: ImageBuffer = np.ascontiguousarray(
            cv2.cvtColor(haystack, CV_COLOR_BGR2GRAY)
            if haystack.ndim == 3
            else haystack
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