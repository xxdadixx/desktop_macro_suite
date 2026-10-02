# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final, override

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.core.types import Rect2D

__all__: Final[list[str]] = ["RoiSelectorOverlay"]


class RoiSelectorOverlay(QWidget):
    """Full-screen transparent overlay for capturing visual template coordinates."""

    roi_selected: Signal = Signal(Rect2D)
    selection_cancelled: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_selecting: bool = False

    def start_selection(self) -> None:
        """Launches the overlay across the virtual screen bounds."""
        self._start_pos = None
        self._current_pos = None
        self._is_selecting = False
        self.showFullScreen()
        self.activateWindow()

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.pos()
            self._current_pos = event.pos()
            self._is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cancel()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_selecting:
            self._current_pos = event.pos()
            self.update()

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self.hide()

            if self._start_pos is not None and self._current_pos is not None:
                rect: QRect = QRect(self._start_pos, self._current_pos).normalized()
                if rect.width() >= 4 and rect.height() >= 4:
                    self.roi_selected.emit(
                        Rect2D(
                            x=rect.x(),
                            y=rect.y(),
                            width=rect.width(),
                            height=rect.height(),
                        )
                    )
                    return

            self.selection_cancelled.emit()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self) -> None:
        self._is_selecting = False
        self.hide()
        self.selection_cancelled.emit()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Draw darkened background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._start_pos is not None and self._current_pos is not None:
            selection_rect: QRect = QRect(self._start_pos, self._current_pos).normalized()

            # Clear selected box cutout
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection_rect, Qt.GlobalColor.transparent)

            # Draw outer highlight border
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen: QPen = QPen(QColor(0, 220, 130), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(selection_rect)

            # Coordinate and dimension tooltip
            coord_text: str = (
                f"{selection_rect.x()}, {selection_rect.y()} "
                f"({selection_rect.width()}x{selection_rect.height()})"
            )
            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                selection_rect.x() + 4,
                max(20, selection_rect.y() - 6),
                coord_text,
            )