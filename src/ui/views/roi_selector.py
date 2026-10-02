# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final, override

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
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

__all__: Final[list[str]] = ["RoiSelectorOverlay", "TargetHighlightOverlay"]


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
        if self.isVisible():
            return

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

        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._start_pos is not None and self._current_pos is not None:
            selection_rect: QRect = QRect(self._start_pos, self._current_pos).normalized()

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection_rect, Qt.GlobalColor.transparent)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen: QPen = QPen(QColor(0, 220, 130), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(selection_rect)

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


class TargetHighlightOverlay(QWidget):
    """Full-screen click-through overlay for highlighting crop origins and live matches on screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._highlight_rect: QRect | None = None
        self._highlight_color: QColor = QColor(0, 230, 118)
        self._label: str = ""
        self._timer: QTimer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def highlight(
        self,
        rect: Rect2D,
        color: QColor = QColor(0, 230, 118),
        label: str = "",
        duration_ms: int = 1800,
    ) -> None:
        """Positions overlay over the virtual desktop and renders a target bounding box."""
        screens = QGuiApplication.screens()
        if screens:
            virtual_geo: QRect = screens[0].virtualGeometry()
            for screen in screens[1:]:
                virtual_geo = virtual_geo.united(screen.virtualGeometry())
            self.setGeometry(virtual_geo)
        else:
            self.showFullScreen()

        self._highlight_rect = QRect(rect.x, rect.y, rect.width, rect.height)
        self._highlight_color = color
        self._label = label
        self.show()
        self.update()
        self._timer.start(duration_ms)

    def _on_timeout(self) -> None:
        self.hide()
        self._highlight_rect = None

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        _ = event
        if self._highlight_rect is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        local_pos = self.mapFromGlobal(self._highlight_rect.topLeft())
        draw_rect = QRect(
            local_pos.x(),
            local_pos.y(),
            self._highlight_rect.width(),
            self._highlight_rect.height(),
        )

        fill_color = QColor(
            self._highlight_color.red(),
            self._highlight_color.green(),
            self._highlight_color.blue(),
            35,
        )
        painter.fillRect(draw_rect, fill_color)

        pen = QPen(self._highlight_color, 2.5, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(draw_rect)

        corner_len = max(4, min(14, min(draw_rect.width(), draw_rect.height()) // 2))
        accent_pen = QPen(QColor(255, 255, 255), 2.5)
        painter.setPen(accent_pen)
        painter.drawLine(draw_rect.left(), draw_rect.top(), draw_rect.left() + corner_len, draw_rect.top())
        painter.drawLine(draw_rect.left(), draw_rect.top(), draw_rect.left(), draw_rect.top() + corner_len)
        painter.drawLine(draw_rect.right(), draw_rect.top(), draw_rect.right() - corner_len, draw_rect.top())
        painter.drawLine(draw_rect.right(), draw_rect.top(), draw_rect.right(), draw_rect.top() + corner_len)
        painter.drawLine(draw_rect.left(), draw_rect.bottom(), draw_rect.left() + corner_len, draw_rect.bottom())
        painter.drawLine(draw_rect.left(), draw_rect.bottom(), draw_rect.left(), draw_rect.bottom() - corner_len)
        painter.drawLine(draw_rect.right(), draw_rect.bottom(), draw_rect.right() - corner_len, draw_rect.bottom())
        painter.drawLine(draw_rect.right(), draw_rect.bottom(), draw_rect.right(), draw_rect.bottom() - corner_len)

        painter.setBrush(self._highlight_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(draw_rect.center().x(), draw_rect.center().y()), 3, 3)

        if self._label:
            font = QFont("Consolas", 9, QFont.Weight.Bold)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(self._label) + 12
            text_h = metrics.height() + 6

            badge_y = draw_rect.top() - text_h - 4
            if badge_y < 10:
                badge_y = draw_rect.bottom() + 4

            badge_rect = QRect(draw_rect.left(), badge_y, text_w, text_h)
            painter.setBrush(QColor(15, 20, 25, 220))
            painter.setPen(QPen(self._highlight_color, 1))
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(self._highlight_color)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._label)