# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final, override

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from src.core.types import Rect2D

__all__: Final[list[str]] = ["RoiSelectorOverlay"]


class RoiSelectorOverlay(QWidget):
    """Full-screen translucent overlay for capturing visual template coordinates across displays."""

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
        self.setMouseTracking(True)

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._is_selecting: bool = False

    def start_selection(self) -> None:
        """Positions the overlay across the full virtual desktop and activates mouse tracking."""
        screens = QGuiApplication.screens()
        if screens:
            virtual_geo: QRect = screens[0].virtualGeometry()
            for screen in screens[1:]:
                virtual_geo = virtual_geo.united(screen.virtualGeometry())
            self.setGeometry(virtual_geo)
        else:
            self.showFullScreen()

        self._start_pos = None
        self._current_pos = None
        self._is_selecting = False
        self.show()
        self.activateWindow()
        self.grabMouse()
        self.update()

    def _cancel(self) -> None:
        self._is_selecting = False
        self.releaseMouse()
        self.hide()
        self.selection_cancelled.emit()

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
            self.releaseMouse()
            self.hide()

            if self._start_pos is not None and self._current_pos is not None:
                p1_global: QPoint = self.mapToGlobal(self._start_pos)
                p2_global: QPoint = self.mapToGlobal(self._current_pos)
                rect: QRect = QRect(p1_global, p2_global).normalized()
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

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Draw darkened background over full virtual desktop
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._start_pos is not None and self._current_pos is not None:
            selection_rect: QRect = QRect(self._start_pos, self._current_pos).normalized()

            # Clear selected box cutout using local widget coordinates
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection_rect, Qt.GlobalColor.transparent)

            # Draw outer highlight border
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen: QPen = QPen(QColor(0, 220, 130), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(selection_rect)

            # Coordinate and dimension tooltip in global screen space
            p_global = self.mapToGlobal(selection_rect.topLeft())
            coord_text: str = (
                f"Global: ({p_global.x()}, {p_global.y()}) "
                f"[{selection_rect.width()}x{selection_rect.height()} px]"
            )
            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                selection_rect.x() + 4,
                max(20, selection_rect.y() - 6),
                coord_text,
            )