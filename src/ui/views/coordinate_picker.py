# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final, override

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from src.core.types import Point2D

__all__: Final[list[str]] = ["CoordinatePickerOverlay"]


class CoordinatePickerOverlay(QWidget):
    """Full-screen translucent crosshair overlay for picking and dragging coordinates across displays."""

    coordinate_selected: Signal = Signal(Point2D)
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

        self._current_pos: QPoint | None = None
        self._is_active: bool = False
        self._hud_font: QFont = QFont("Consolas", 10, QFont.Weight.Bold)

    def start_selection(self) -> None:
        """Positions the overlay across the full virtual desktop and activates mouse grabbing."""
        screens = QGuiApplication.screens()
        if screens:
            virtual_geo: QRect = screens[0].virtualGeometry()
            for screen in screens[1:]:
                virtual_geo = virtual_geo.united(screen.virtualGeometry())
            self.setGeometry(virtual_geo)
        else:
            self.showFullScreen()

        self._is_active = True
        self._current_pos = self.mapFromGlobal(QCursor.pos())
        self.show()
        self.activateWindow()
        self.grabMouse()
        self.update()

    def _finish(self, global_x: int, global_y: int) -> None:
        self._is_active = False
        self.releaseMouse()
        self.hide()
        self.coordinate_selected.emit(Point2D(x=global_x, y=global_y))

    def _cancel(self) -> None:
        self._is_active = False
        self.releaseMouse()
        self.hide()
        self.selection_cancelled.emit()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._current_pos = event.pos()
        self.update()

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
        elif event.button() == Qt.MouseButton.LeftButton:
            global_pos: QPoint = self.mapToGlobal(event.pos())
            self._finish(global_pos.x(), global_pos.y())

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_active:
            global_pos: QPoint = self.mapToGlobal(event.pos())
            self._finish(global_pos.x(), global_pos.y())

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._current_pos is not None:
                global_pos: QPoint = self.mapToGlobal(self._current_pos)
                self._finish(global_pos.x(), global_pos.y())

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Translucent backdrop for clear visibility of target desktop elements
        painter.fillRect(self.rect(), QColor(10, 14, 20, 65))

        if self._current_pos is None:
            return

        cx: int = self._current_pos.x()
        cy: int = self._current_pos.y()
        global_pos: QPoint = self.mapToGlobal(self._current_pos)

        # Full-screen guide crosshair lines
        line_pen = QPen(QColor(0, 229, 255, 180), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(line_pen)
        painter.drawLine(0, cy, self.width(), cy)
        painter.drawLine(cx, 0, cx, self.height())

        # Dual concentric target reticles
        reticle_pen = QPen(QColor(0, 230, 118, 240), 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(reticle_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPoint(cx, cy), 8, 8)
        painter.drawEllipse(QPoint(cx, cy), 20, 20)

        # Center indicator point
        painter.setBrush(QColor(0, 230, 118))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(cx, cy), 2, 2)

        # Dynamic HUD Badge with boundary auto-flip
        hud_w: int = 210
        hud_h: int = 54
        hud_x: int = cx + 24
        hud_y: int = cy + 24

        if hud_x + hud_w > self.rect().right() - 10:
            hud_x = cx - hud_w - 24
        if hud_y + hud_h > self.rect().bottom() - 10:
            hud_y = cy - hud_h - 24

        hud_rect = QRect(hud_x, hud_y, hud_w, hud_h)
        painter.setBrush(QColor(22, 27, 34, 235))
        painter.setPen(QPen(QColor(0, 229, 255, 200), 1.2))
        painter.drawRoundedRect(hud_rect, 6, 6)

        painter.setFont(self._hud_font)
        painter.setPen(QColor(0, 230, 118))
        painter.drawText(
            hud_x + 10,
            hud_y + 22,
            f"X: {global_pos.x()}   Y: {global_pos.y()}",
        )

        sub_font = QFont("Consolas", 8)
        painter.setFont(sub_font)
        painter.setPen(QColor(160, 175, 195))
        painter.drawText(
            hud_x + 10,
            hud_y + 42,
            "Release / Click to Pick  |  ESC",
        )