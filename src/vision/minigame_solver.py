from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.core.enums import PlatePosition, RabbitSlot
from src.core.types import ImageBuffer, Point2D, Rect2D
from src.vision.preprocessor import ImagePreprocessor

__all__: Final[list[str]] = ["MooncakeGameSolver", "SolvedMove"]

# Pastry Golden-Yellow Color Thresholds in OpenCV HSV (H: 0-180, S: 0-255, V: 0-255)
PASTRY_LOWER_HSV: Final[tuple[int, int, int]] = (12, 100, 140)
PASTRY_UPPER_HSV: Final[tuple[int, int, int]] = (35, 255, 255)

# Selection Banner Cyan Color Range for Game State Verification
BANNER_LOWER_HSV: Final[tuple[int, int, int]] = (80, 100, 100)
BANNER_UPPER_HSV: Final[tuple[int, int, int]] = (105, 255, 255)

# Normalized plate center coordinates relative to 1920x1080 display geometry
PLATE_NORMALIZED_COORDS: Final[dict[PlatePosition, tuple[float, float]]] = {
    PlatePosition.TOP_LEFT: (0.428, 0.333),
    PlatePosition.TOP_RIGHT: (0.635, 0.333),
    PlatePosition.CENTER: (0.528, 0.537),
    PlatePosition.BOTTOM_LEFT: (0.402, 0.787),
    PlatePosition.BOTTOM_RIGHT: (0.655, 0.778),
}

# Legal move adjacency mapping: player slot -> accessible adjacent plates
ADJACENCY_MAP: Final[dict[RabbitSlot, tuple[PlatePosition, PlatePosition, PlatePosition]]] = {
    RabbitSlot.TOP: (
        PlatePosition.TOP_LEFT,
        PlatePosition.CENTER,
        PlatePosition.TOP_RIGHT,
    ),
    RabbitSlot.LEFT: (
        PlatePosition.TOP_LEFT,
        PlatePosition.CENTER,
        PlatePosition.BOTTOM_LEFT,
    ),
    RabbitSlot.RIGHT: (
        PlatePosition.TOP_RIGHT,
        PlatePosition.CENTER,
        PlatePosition.BOTTOM_RIGHT,
    ),
    RabbitSlot.BOTTOM: (
        PlatePosition.BOTTOM_LEFT,
        PlatePosition.CENTER,
        PlatePosition.BOTTOM_RIGHT,
    ),
}


@dataclass(frozen=True, slots=True)
class SolvedMove:
    """Calculated decision outcome for the Mooncake Battle mini-game."""

    player_slot: RabbitSlot
    chosen_plate: PlatePosition
    target_point: Point2D
    cake_counts: dict[PlatePosition, int]
    is_selection_active: bool


class MooncakeGameSolver:
    """Computer vision board parser and decision solver for the Mooncake Battle mini-game."""

    def __init__(
        self,
        pastry_lower_hsv: tuple[int, int, int] = PASTRY_LOWER_HSV,
        pastry_upper_hsv: tuple[int, int, int] = PASTRY_UPPER_HSV,
    ) -> None:
        self._pastry_lower: tuple[int, int, int] = pastry_lower_hsv
        self._pastry_upper: tuple[int, int, int] = pastry_upper_hsv

    def is_selection_phase_active(self, frame: ImageBuffer) -> bool:
        """Determines if the active countdown selection banner is visible at screen bottom."""
        h, w = int(frame.shape[0]), int(frame.shape[1])
        # Bottom banner instruction ROI ("โปรดเลือกช่องรอบตัวที่มี Moon Cake")
        banner_roi = Rect2D(
            x=int(w * 0.30),
            y=int(h * 0.90),
            width=int(w * 0.40),
            height=int(h * 0.08),
        )
        crop = ImagePreprocessor.crop_roi(frame, banner_roi)
        area = ImagePreprocessor.measure_color_area(
            crop, BANNER_LOWER_HSV, BANNER_UPPER_HSV
        )
        return area > 400

    def classify_plate_cakes(self, frame: ImageBuffer, plate: PlatePosition) -> int:
        """Analyzes pastry area on a specific plate to estimate whether it holds 1, 2, or 3 cakes."""
        h, w = int(frame.shape[0]), int(frame.shape[1])
        norm_x, norm_y = PLATE_NORMALIZED_COORDS[plate]

        # Sample plate surface bounding box centered at normalized plate coordinates
        box_w: int = int(w * 0.11)
        box_h: int = int(h * 0.14)
        center_x: int = int(w * norm_x)
        center_y: int = int(h * norm_y)

        plate_roi = Rect2D(
            x=max(0, center_x - (box_w // 2)),
            y=max(0, center_y - (box_h // 2)),
            width=box_w,
            height=box_h,
        )

        crop = ImagePreprocessor.crop_roi(frame, plate_roi)
        pastry_area = ImagePreprocessor.measure_color_area(
            crop, self._pastry_lower, self._pastry_upper
        )

        # Normalized area scaling relative to 1080p reference area
        reference_scale: float = (w * h) / (1920.0 * 1080.0)
        norm_area: float = pastry_area / max(0.1, reference_scale)

        # Pastry area clustering thresholds calibrated for 1, 2, and 3 mooncakes
        if norm_area < 800:
            return 0
        if norm_area < 2800:
            return 1
        if norm_area < 5200:
            return 2
        return 3

    def solve(
        self,
        frame: ImageBuffer,
        player_slot: RabbitSlot = RabbitSlot.RIGHT,
        origin: Point2D = Point2D(x=0, y=0),
    ) -> SolvedMove:
        """Evaluates adjacent plate values for the given player slot and selects the plate with max cakes."""
        actual_slot: RabbitSlot = (
            RabbitSlot.RIGHT if player_slot == RabbitSlot.AUTO else player_slot
        )
        accessible_plates = ADJACENCY_MAP[actual_slot]

        cake_counts: dict[PlatePosition, int] = {}
        for plate in accessible_plates:
            cake_counts[plate] = self.classify_plate_cakes(frame, plate)

        # Greedy argmax selection: select adjacent plate with the highest pastry count
        best_plate: PlatePosition = accessible_plates[0]
        max_cakes: int = -1
        for plate in accessible_plates:
            count = cake_counts[plate]
            if count > max_cakes:
                max_cakes = count
                best_plate = plate

        h, w = int(frame.shape[0]), int(frame.shape[1])
        norm_x, norm_y = PLATE_NORMALIZED_COORDS[best_plate]
        target_point = Point2D(
            x=origin.x + int(w * norm_x),
            y=origin.y + int(h * norm_y),
        )

        selection_active = self.is_selection_phase_active(frame)

        return SolvedMove(
            player_slot=actual_slot,
            chosen_plate=best_plate,
            target_point=target_point,
            cake_counts=cake_counts,
            is_selection_active=selection_active,
        )