# pyright: reportUntypedBaseClass=false
from __future__ import annotations

import json
from typing import Final, override

from PySide6.QtCore import (
    QByteArray,
    QItemSelection,
    QItemSelectionModel,
    QMimeData,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.core.ast import DelayAction
from src.ui.models.action_model import ActionSequenceModel, FlatActionRow

__all__: Final[list[str]] = ["ActionTableView", "CodeTimelineDelegate", "TimelineView"]

MIME_ACTION_ROWS: Final[str] = "application/x-desktop-macro-action-rows"
INDENT_STEP_WIDTH: Final[int] = 20
BASE_INDENT_OFFSET: Final[int] = 16


class ActionTableView(QTableView):
    """Monospaced timeline table view supporting drag-and-drop reordering with insertion line guide."""

    rows_reordered: Signal = Signal(list, int, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.viewport().setAcceptDrops(True)

        self._drag_start_pos: QPoint | None = None
        self._drop_target_row: int | None = None
        self._drop_insert_below: bool | None = None

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
        ):
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._initiate_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def _initiate_drag(self) -> None:
        selection_model = self.selectionModel()
        rows = sorted({idx.row() for idx in selection_model.selectedRows()})
        if not rows and self._drag_start_pos is not None:
            clicked_idx = self.indexAt(self._drag_start_pos)
            if clicked_idx.isValid():
                rows = [clicked_idx.row()]

        if not rows:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        payload = json.dumps(rows).encode("utf-8")
        mime_data.setData(MIME_ACTION_ROWS, QByteArray(payload))
        drag.setMimeData(mime_data)
        _ = drag.exec(Qt.DropAction.MoveAction)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(MIME_ACTION_ROWS):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if not event.mimeData().hasFormat(MIME_ACTION_ROWS):
            event.ignore()
            return

        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        row_count = self.model().rowCount()

        if idx.isValid():
            rect = self.visualRect(idx)
            self._drop_target_row = idx.row()
            self._drop_insert_below = pos.y() > rect.center().y()
            self.viewport().update()
            event.acceptProposedAction()
        elif row_count > 0:
            self._drop_target_row = row_count - 1
            self._drop_insert_below = True
            self.viewport().update()
            event.acceptProposedAction()
        else:
            self._drop_target_row = None
            self._drop_insert_below = None
            self.viewport().update()
            event.ignore()

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._drop_target_row = None
        self._drop_insert_below = None
        self.viewport().update()
        event.accept()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasFormat(MIME_ACTION_ROWS):
            event.ignore()
            return

        raw_bytes: bytes = bytes(event.mimeData().data(MIME_ACTION_ROWS).data())
        source_rows: list[int] = json.loads(raw_bytes.decode("utf-8"))

        target_row = self._drop_target_row
        insert_below = self._drop_insert_below

        self._drop_target_row = None
        self._drop_insert_below = None
        self.viewport().update()

        if target_row is not None and insert_below is not None:
            self.rows_reordered.emit(source_rows, target_row, insert_below)
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._drop_target_row is None or self._drop_insert_below is None:
            return

        idx = self.model().index(self._drop_target_row, 0)
        if not idx.isValid():
            return

        rect = self.visualRect(idx)
        line_y = rect.bottom() if self._drop_insert_below else rect.top()

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(QColor(0, 230, 118), 2)
        painter.setPen(pen)
        painter.drawLine(0, line_y, self.viewport().width(), line_y)

        triangle = QPainterPath()
        triangle.moveTo(0, line_y - 4)
        triangle.lineTo(6, line_y)
        triangle.lineTo(0, line_y + 4)
        triangle.closeSubpath()
        painter.fillPath(triangle, QColor(0, 230, 118))


class CodeTimelineDelegate(QStyledItemDelegate):
    """High-performance item delegate rendering hierarchical code blocks with scope lines."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mono_font: QFont = QFont("Consolas", 10)
        self._mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self._gutter_font: QFont = QFont("Consolas", 9)
        self._gutter_font.setStyleHint(QFont.StyleHint.Monospace)
        self._text_doc: QTextDocument = QTextDocument(self)
        self._text_doc.setDefaultFont(self._mono_font)
        self._text_doc.setDocumentMargin(0)

    @override
    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        base_size: QSize = super().sizeHint(option, index)
        return QSize(base_size.width(), 32)

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect: QRect = option.rect
        col: int = index.column()
        is_selected: bool = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered: bool = bool(option.state & QStyle.StateFlag.State_MouseOver)

        meta: FlatActionRow | None = index.data(int(Qt.ItemDataRole.UserRole + 1))
        depth: int = meta.depth if meta is not None else 0
        is_loop: bool = meta.is_loop_header if meta is not None else False
        is_last: bool = meta.is_last_in_scope if meta is not None else False
        guides: list[int] = meta.active_guide_depths if meta is not None else []

        # 1. Row Background
        if is_selected:
            painter.fillRect(rect, QColor(36, 44, 58))
            if col == 0:
                accent_rect = QRect(rect.left(), rect.top(), 3, rect.height())
                painter.fillRect(accent_rect, QColor(0, 230, 118))
        elif is_hovered:
            painter.fillRect(rect, QColor(30, 33, 40))
        elif is_loop:
            painter.fillRect(rect, QColor(24, 27, 34))
        elif depth > 0:
            painter.fillRect(rect, QColor(20, 22, 27))
        else:
            painter.fillRect(rect, QColor(18, 20, 24))

        # 2. Line Number Gutter
        if col == 0:
            painter.setFont(self._gutter_font)
            line_str = str(index.data(int(Qt.ItemDataRole.DisplayRole)) or "")
            gutter_color = QColor(0, 230, 118) if is_selected else QColor(92, 99, 112)
            painter.setPen(gutter_color)

            text_rect = QRect(rect.left(), rect.top(), rect.width() - 8, rect.height())
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                line_str,
            )

            painter.setPen(QPen(QColor(40, 44, 52), 1))
            painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())

        # 3. Action Instruction with Scope Guide Connecting Lines
        elif col == 1:
            mid_y = rect.center().y()

            for g_depth in guides:
                gx = rect.left() + BASE_INDENT_OFFSET + ((g_depth - 1) * INDENT_STEP_WIDTH)
                pen = QPen(QColor(60, 68, 84, 180), 1.2, Qt.PenStyle.SolidLine)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.drawLine(gx, rect.top(), gx, rect.bottom())

            if depth > 0:
                self_x = rect.left() + BASE_INDENT_OFFSET + ((depth - 1) * INDENT_STEP_WIDTH)
                branch_len = INDENT_STEP_WIDTH - 6

                branch_pen = QPen(
                    QColor(0, 230, 118, 230) if is_selected else QColor(75, 85, 105, 200),
                    1.4,
                    Qt.PenStyle.SolidLine,
                )
                branch_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(branch_pen)

                if is_last:
                    painter.drawLine(self_x, rect.top(), self_x, mid_y)
                    painter.drawLine(self_x, mid_y, self_x + branch_len, mid_y)
                else:
                    painter.drawLine(self_x, rect.top(), self_x, rect.bottom())
                    painter.drawLine(self_x, mid_y, self_x + branch_len, mid_y)

                dot_color = QColor(0, 230, 118) if is_selected else QColor(100, 115, 140)
                painter.setBrush(QBrush(dot_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(self_x + branch_len, mid_y), 2.2, 2.2)

            if is_loop:
                next_x = rect.left() + BASE_INDENT_OFFSET + (depth * INDENT_STEP_WIDTH)
                loop_pen = QPen(QColor(0, 230, 118, 200) if is_selected else QColor(80, 92, 115), 1.4)
                painter.setPen(loop_pen)
                painter.drawLine(next_x, mid_y + 4, next_x, rect.bottom())

            html_text = str(index.data(int(Qt.ItemDataRole.UserRole)) or "")
            if not html_text:
                html_text = str(index.data(int(Qt.ItemDataRole.DisplayRole)) or "")

            code_left = rect.left() + BASE_INDENT_OFFSET + (depth * INDENT_STEP_WIDTH) + 8
            code_width = max(10, rect.right() - code_left - 8)

            self._text_doc.setHtml(html_text)
            self._text_doc.setTextWidth(code_width)

            painter.save()
            doc_height = self._text_doc.size().height()
            y_offset = (rect.height() - doc_height) / 2.0
            painter.translate(code_left, rect.top() + max(0.0, y_offset))
            painter.setClipRect(0, -int(y_offset), code_width, rect.height())
            self._text_doc.drawContents(painter)
            painter.restore()

        # 4. Timing Badges
        elif col == 2:
            timing_str = str(index.data(int(Qt.ItemDataRole.DisplayRole)) or "")
            painter.setFont(self._gutter_font)

            badge_rect = QRect(rect.left() + 6, rect.center().y() - 9, rect.width() - 12, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(33, 37, 43)))
            painter.drawRoundedRect(badge_rect, 4, 4)

            text_color = QColor(152, 195, 121) if timing_str != "0.0 ms" else QColor(92, 99, 112)
            painter.setPen(text_color)
            painter.drawText(
                badge_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                timing_str,
            )

        painter.restore()


class TimelineView(QWidget):
    """Sequence action timeline view with code styling, connecting lines, and drag-and-drop reordering."""

    action_selected: Signal = Signal(int)
    status_message_requested: Signal = Signal(str)

    def __init__(
        self,
        model: ActionSequenceModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model: ActionSequenceModel = model

        layout: QVBoxLayout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Action Toolbar
        toolbar: QHBoxLayout = QHBoxLayout()

        self._btn_cut: QPushButton = QPushButton("✂ Cut")
        self._btn_cut.setToolTip("Cut selected action(s) to clipboard (Ctrl+X)")
        self._btn_cut.clicked.connect(self._on_cut)

        self._btn_copy: QPushButton = QPushButton("📋 Copy")
        self._btn_copy.setToolTip("Copy selected action(s) to clipboard (Ctrl+C)")
        self._btn_copy.clicked.connect(self._on_copy)

        self._btn_paste: QPushButton = QPushButton("📥 Paste")
        self._btn_paste.setToolTip("Paste actions one line below selected action (Ctrl+V)")
        self._btn_paste.clicked.connect(self._on_paste)

        self._btn_up: QPushButton = QPushButton("▲ Up")
        self._btn_up.setToolTip("Move selected action(s) up (Alt+Up / Ctrl+Up)")
        self._btn_up.clicked.connect(self._on_move_up)

        self._btn_down: QPushButton = QPushButton("▼ Down")
        self._btn_down.setToolTip("Move selected action(s) down (Alt+Down / Ctrl+Down)")
        self._btn_down.clicked.connect(self._on_move_down)

        self._btn_indent: QPushButton = QPushButton("⇥ Indent")
        self._btn_indent.setToolTip("Nest action into preceding loop block (Tab)")
        self._btn_indent.clicked.connect(self._on_indent)

        self._btn_outdent: QPushButton = QPushButton("⇤ Outdent")
        self._btn_outdent.setToolTip("Move action out of loop block (Shift+Tab)")
        self._btn_outdent.clicked.connect(self._on_outdent)

        self._btn_wrap_loop: QPushButton = QPushButton("🔁 Wrap in Loop")
        self._btn_wrap_loop.setToolTip("Enclose selected actions in a loop container (Ctrl+L)")
        self._btn_wrap_loop.clicked.connect(self._on_wrap_loop)

        self._btn_add_delay: QPushButton = QPushButton("+ Delay")
        self._btn_add_delay.setToolTip("Insert a pause action (Insert / Alt+D)")
        self._btn_add_delay.clicked.connect(self._on_add_delay)

        self._btn_delete: QPushButton = QPushButton("✕ Delete")
        self._btn_delete.setToolTip("Delete selected action(s) (Delete / Backspace)")
        self._btn_delete.clicked.connect(self._on_delete)

        toolbar.addWidget(self._btn_cut)
        toolbar.addWidget(self._btn_copy)
        toolbar.addWidget(self._btn_paste)
        toolbar.addWidget(self._btn_up)
        toolbar.addWidget(self._btn_down)
        toolbar.addWidget(self._btn_indent)
        toolbar.addWidget(self._btn_outdent)
        toolbar.addWidget(self._btn_wrap_loop)
        toolbar.addWidget(self._btn_add_delay)
        toolbar.addWidget(self._btn_delete)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Drag-and-drop table view
        self._table: ActionTableView = ActionTableView(self)
        self._table.setModel(self._model)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableView {"
            "  background-color: #191B20;"
            "  border: 1px solid #282C34;"
            "  selection-background-color: transparent;"
            "}"
            "QHeaderView::section {"
            "  background-color: #16181D;"
            "  color: #8B949E;"
            "  font-weight: bold;"
            "  font-size: 11px;"
            "  border: none;"
            "  border-bottom: 1px solid #282C34;"
            "  padding: 4px 8px;"
            "}"
        )

        self._delegate: CodeTimelineDelegate = CodeTimelineDelegate(self)
        self._table.setItemDelegate(self._delegate)

        header: QHeaderView = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 48)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 95)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.rows_reordered.connect(self._on_rows_reordered)
        layout.addWidget(self._table)

        self._bind_shortcuts()

    def _bind_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        QShortcut(QKeySequence.StandardKey.Cut, self, self._on_cut, context=ctx)
        QShortcut(QKeySequence.StandardKey.Copy, self, self._on_copy, context=ctx)
        QShortcut(QKeySequence.StandardKey.Paste, self, self._on_paste, context=ctx)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self, self._on_delete, context=ctx)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, self._on_delete, context=ctx)
        QShortcut(QKeySequence("Alt+Up"), self, self._on_move_up, context=ctx)
        QShortcut(QKeySequence("Ctrl+Up"), self, self._on_move_up, context=ctx)
        QShortcut(QKeySequence("Alt+Down"), self, self._on_move_down, context=ctx)
        QShortcut(QKeySequence("Ctrl+Down"), self, self._on_move_down, context=ctx)
        QShortcut(QKeySequence(Qt.Key.Key_Tab), self, self._on_indent, context=ctx)
        QShortcut(QKeySequence("Shift+Tab"), self, self._on_outdent, context=ctx)
        QShortcut(QKeySequence("Ctrl+L"), self, self._on_wrap_loop, context=ctx)
        QShortcut(QKeySequence("Insert"), self, self._on_add_delay, context=ctx)
        QShortcut(QKeySequence("Alt+D"), self, self._on_add_delay, context=ctx)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.clear_selection, context=ctx)

    def selected_rows(self) -> list[int]:
        selection_model = self._table.selectionModel()
        rows: set[int] = {idx.row() for idx in selection_model.selectedRows()}
        if not rows:
            rows = {idx.row() for idx in selection_model.selectedIndexes()}
        return sorted(rows)

    def select_row(self, row: int) -> None:
        self.select_rows([row])

    def select_rows(self, rows: list[int]) -> None:
        if not rows:
            return

        selection_model = self._table.selectionModel()
        selection_model.clearSelection()
        flag = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows
        )
        for r in rows:
            selection_model.select(self._model.index(r, 0), flag)

        lead_idx = self._model.index(rows[0], 0)
        selection_model.setCurrentIndex(lead_idx, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.action_selected.emit(rows[0])

    def clear_selection(self) -> None:
        self._table.clearSelection()
        self.action_selected.emit(-1)

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        _ = selected
        _ = deselected
        rows = self.selected_rows()
        if rows:
            current = self._table.currentIndex()
            lead_row = current.row() if current.isValid() and current.row() in rows else rows[0]
            self.action_selected.emit(lead_row)
        else:
            self.action_selected.emit(-1)

    def _on_cut(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return

        anchor = min(rows)
        cut_list = self._model.cut_actions(rows)
        total = self._model.rowCount()

        if total > 0:
            next_row = min(anchor, total - 1)
            self.select_row(next_row)
        else:
            self.action_selected.emit(-1)

        msg = f"Cut {len(cut_list)} action(s) to clipboard."
        self.status_message_requested.emit(msg)

    def _on_copy(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return

        copied_list = self._model.copy_actions(rows)
        msg = f"Copied {len(copied_list)} action(s) to clipboard."
        self.status_message_requested.emit(msg)

    def _on_paste(self) -> None:
        if not self._model.has_clipboard():
            return

        rows = self.selected_rows()
        target_row = rows[-1] if rows else (self._model.rowCount() - 1)
        new_rows = self._model.paste_actions(target_row=target_row, insert_below=True)

        if new_rows:
            self.select_rows(new_rows)
            target_step = target_row + 1 if target_row >= 0 else 0
            self.status_message_requested.emit(
                f"Pasted {len(new_rows)} action(s) below step #{target_step}."
            )

    def _on_rows_reordered(
        self,
        source_rows: list[int],
        target_row: int,
        insert_below: bool,
    ) -> None:
        new_rows = self._model.move_action_hierarchy(
            source_rows=source_rows,
            target_row=target_row,
            insert_below=insert_below,
        )
        if new_rows:
            self.select_rows(new_rows)
            rel_str = "below" if insert_below else "above"
            self.status_message_requested.emit(
                f"Moved action(s) {rel_str} step #{target_row + 1}."
            )

    def _on_move_up(self) -> None:
        rows = self.selected_rows()
        if not rows or rows[0] <= 0:
            return

        target_row = rows[0]
        action = self._model.get_action(target_row)
        if action is None:
            return
        target_id = action.id

        if self._model.move_action(target_row, target_row - 1):
            new_row = self._model.find_row_by_id(target_id)
            if new_row >= 0:
                self.select_row(new_row)

    def _on_move_down(self) -> None:
        rows = self.selected_rows()
        if not rows or rows[-1] >= self._model.rowCount() - 1:
            return

        target_row = rows[-1]
        action = self._model.get_action(target_row)
        if action is None:
            return
        target_id = action.id

        if self._model.move_action(target_row, target_row + 1):
            new_row = self._model.find_row_by_id(target_id)
            if new_row >= 0:
                self.select_row(new_row)

    def _on_indent(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        if self._model.indent_action(rows[0]):
            self.select_row(rows[0])

    def _on_outdent(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        if self._model.outdent_action(rows[0]):
            self.select_row(rows[0])

    def _on_wrap_loop(self) -> None:
        rows = self.selected_rows()
        new_row = self._model.wrap_actions_in_loop(rows)
        self.select_row(new_row)

    def _on_add_delay(self) -> None:
        action = DelayAction(duration_ms=0.0, jitter_ms=0.0)
        self._model.append_action(action)
        self.select_row(self._model.rowCount() - 1)

    def _on_delete(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return

        anchor_row = min(rows)
        self._model.remove_actions(rows)

        total = self._model.rowCount()
        if total > 0:
            next_row = min(anchor_row, total - 1)
            self.select_row(next_row)
        else:
            self.action_selected.emit(-1)