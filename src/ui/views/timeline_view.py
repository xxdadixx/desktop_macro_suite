from __future__ import annotations

from typing import Final

from PySide6.QtCore import QItemSelection, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.core.ast import DelayAction
from src.ui.models.action_model import ActionSequenceModel

__all__: Final[list[str]] = ["TimelineView"]


class TimelineView(QWidget):
    """Sequence action timeline view with row control buttons."""

    action_selected: Signal = Signal(int)

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
        self._btn_up: QPushButton = QPushButton("▲ Up")
        self._btn_down: QPushButton = QPushButton("▼ Down")
        self._btn_add_delay: QPushButton = QPushButton("+ Delay")
        self._btn_delete: QPushButton = QPushButton("✕ Delete")

        self._btn_up.clicked.connect(self._on_move_up)
        self._btn_down.clicked.connect(self._on_move_down)
        self._btn_add_delay.clicked.connect(self._on_add_delay)
        self._btn_delete.clicked.connect(self._on_delete)

        toolbar.addWidget(self._btn_up)
        toolbar.addWidget(self._btn_down)
        toolbar.addWidget(self._btn_add_delay)
        toolbar.addWidget(self._btn_delete)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Table View
        self._table: QTableView = QTableView(self)
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self._table)

    def selected_row(self) -> int:
        indexes = self._table.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        _ = deselected
        indexes = selected.indexes()
        if indexes:
            self.action_selected.emit(indexes[0].row())

    def _on_move_up(self) -> None:
        row = self.selected_row()
        if row > 0:
            if self._model.move_action(row, row - 1):
                self._table.selectRow(row - 1)

    def _on_move_down(self) -> None:
        row = self.selected_row()
        if 0 <= row < self._model.rowCount() - 1:
            if self._model.move_action(row, row + 1):
                self._table.selectRow(row + 1)

    def _on_add_delay(self) -> None:
        action = DelayAction(duration_ms=250.0, jitter_ms=0.0)
        self._model.append_action(action)
        self._table.selectRow(self._model.rowCount() - 1)

    def _on_delete(self) -> None:
        row = self.selected_row()
        if row >= 0:
            _ = self._model.remove_action(row)
            if self._model.rowCount() > 0:
                next_row = min(row, self._model.rowCount() - 1)
                self._table.selectRow(next_row)