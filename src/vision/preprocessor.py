# pyright: reportUnknownParameterType=false
from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol, cast

import numpy as np

from src.core.types import ImageBuffer, Rect2D

CV_COLOR_BGR2GRAY: Final[int] = 6
CV_COLOR_GRAY2BGR: Final[int] = 8
CV_COLOR_BGR2HSV: Final[int] = 40
CV_INTER_LINEAR: Final[int] = 1

if TYPE_CHECKING:
    class _Cv2Protocol(Protocol):
        def cvtColor(self, src: ImageBuffer, code: int) -> ImageBuffer: ...
        def GaussianBlur(
            self, src: ImageBuffer, ksize: tuple[int, int], sigmaX: float
        ) -> ImageBuffer: ...
        def Canny(
            self, image: ImageBuffer, threshold1: float, threshold2: float
        ) -> ImageBuffer: ...
        def resize(
            self, src: ImageBuffer, dsize: tuple[int, int], interpolation: int = ...
        ) -> ImageBuffer: ...
        def inRange(
            self, src: ImageBuffer, lowerb: object, upperb: object
        ) -> ImageBuffer: ...
        def countNonZero(self, src: ImageBuffer) -> int: ...

    cv2: _Cv2Protocol
else:
    import cv2

__all__: Final[list[str]] = ["ImagePreprocessor"]


class ImagePreprocessor:
    """Transformation and filtering pipeline for image buffers prior to visual template matching."""

    @staticmethod
    def crop_roi(image: ImageBuffer, roi: Rect2D) -> ImageBuffer:
        """Extracts a bounding region of interest from an image buffer with clamp validation."""
        img_h: int = int(image.shape[0])
        img_w: int = int(image.shape[1])

        x: int = max(0, min(roi.x, img_w))
        y: int = max(0, min(roi.y, img_h))
        max_w: int = img_w - x
        max_h: int = img_h - y
        w: int = max(1, min(roi.width, max_w))
        h: int = max(1, min(roi.height, max_h))

        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid ROI bounds for buffer dimensions ({img_w}x{img_h}): {roi}")

        cropped = image[y : y + h, x : x + w]
        return cast(ImageBuffer, np.ascontiguousarray(cropped))

    @staticmethod
    def to_grayscale(image: ImageBuffer) -> ImageBuffer:
        """Converts a BGR image buffer into single-channel grayscale."""
        if image.ndim == 2:
            return image
        converted: ImageBuffer = cv2.cvtColor(image, CV_COLOR_BGR2GRAY)
        return np.ascontiguousarray(converted)

    @staticmethod
    def to_bgr(image: ImageBuffer) -> ImageBuffer:
        """Converts a single-channel grayscale buffer back to 3-channel BGR."""
        if image.ndim == 3:
            return image
        converted: ImageBuffer = cv2.cvtColor(image, CV_COLOR_GRAY2BGR)
        return np.ascontiguousarray(converted)

    @staticmethod
    def to_hsv(image: ImageBuffer) -> ImageBuffer:
        """Converts a 3-channel BGR image buffer into HSV color space."""
        if image.ndim != 3:
            raise ValueError("HSV conversion requires a 3-channel BGR image buffer")
        converted: ImageBuffer = cv2.cvtColor(image, CV_COLOR_BGR2HSV)
        return np.ascontiguousarray(converted)

    @staticmethod
    def extract_color_mask(
        image: ImageBuffer,
        lower_hsv: tuple[int, int, int],
        upper_hsv: tuple[int, int, int],
    ) -> ImageBuffer:
        """Extracts a binary mask where pixels falling within the HSV range are 255."""
        hsv_img: ImageBuffer = (
            ImagePreprocessor.to_hsv(image) if image.ndim == 3 else image
        )
        lower_arr = np.array(lower_hsv, dtype=np.uint8)
        upper_arr = np.array(upper_hsv, dtype=np.uint8)
        mask: ImageBuffer = cv2.inRange(hsv_img, lower_arr, upper_arr)
        return np.ascontiguousarray(mask)

    @staticmethod
    def measure_color_area(
        image: ImageBuffer,
        lower_hsv: tuple[int, int, int],
        upper_hsv: tuple[int, int, int],
    ) -> int:
        """Measures the active pixel count matching the specified HSV color boundary."""
        mask = ImagePreprocessor.extract_color_mask(image, lower_hsv, upper_hsv)
        return int(cv2.countNonZero(mask))

    @staticmethod
    def apply_gaussian_blur(
        image: ImageBuffer,
        kernel_size: int = 5,
        sigma: float = 0.0,
    ) -> ImageBuffer:
        """Applies Gaussian smoothing to suppress high-frequency noise."""
        k: int = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
        blurred: ImageBuffer = cv2.GaussianBlur(image, (k, k), sigma)
        return np.ascontiguousarray(blurred)

    @staticmethod
    def apply_canny(
        image: ImageBuffer,
        threshold1: float = 100.0,
        threshold2: float = 200.0,
    ) -> ImageBuffer:
        """Extracts edges using the Canny algorithm."""
        gray: ImageBuffer = ImagePreprocessor.to_grayscale(image)
        edges: ImageBuffer = cv2.Canny(gray, threshold1, threshold2)
        return np.ascontiguousarray(edges)

    @staticmethod
    def resize(
        image: ImageBuffer,
        target_width: int,
        target_height: int,
    ) -> ImageBuffer:
        """Resizes an image buffer to specific dimensions using bilinear interpolation."""
        if target_width <= 0 or target_height <= 0:
            raise ValueError(
                f"Invalid dimensions: width={target_width}, height={target_height}"
            )

        resized: ImageBuffer = cv2.resize(
            image,
            (target_width, target_height),
            CV_INTER_LINEAR,
        )
        return np.ascontiguousarray(resized)