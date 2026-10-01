# pyright: reportAny=false, reportExplicitAny=false, reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt

from src.core.ast import (
    ActionNode,
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MacroSequence,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)

__all__: Final[list[str]] = ["ActionSequenceModel"]

COLUMNS: Final[list[str]] = ["#", "Type", "Details", "Timing"]


class ActionSequenceModel(QAbstractTableModel):
    """Qt Table Model wrapping sequential MacroSequence ActionNodes."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._actions: list[ActionNode] = []
        self._sequence_name: str = "Untitled Sequence"
        self._sequence_description: str = ""
        self._sequence_author: str = ""

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._actions)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if role == int(Qt.ItemDataRole.DisplayRole) and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section]
        return None

    def data(
        self,
        index: QModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if not index.isValid() or not (0 <= index.row() < len(self._actions)):
            return None

        action: ActionNode = self._actions[index.row()]

        if role == int(Qt.ItemDataRole.DisplayRole):
            col: int = index.column()
            if col == 0:
                return str(index.row() + 1)
            if col == 1:
                return action.action_type.value
            if col == 2:
                return self._format_action_details(action)
            if col == 3:
                return self._format_action_timing(action)

        return None

    def _format_action_details(self, action: ActionNode) -> str:
        match action:
            case MouseMoveAction() as m:
                mode: str = "rel" if m.is_relative else "abs"
                return f"Move -> ({m.x}, {m.y}) [{mode}]"
            case MouseButtonAction() as b:
                coords: str = (
                    f" at ({b.x}, {b.y})" if b.x is not None and b.y is not None else ""
                )
                return f"{b.button.value.title()} Button {b.state.value.title()}{coords}"
            case MouseScrollAction() as s:
                orient: str = "Horizontal" if s.horizontal else "Vertical"
                return f"Scroll {orient} -> Delta: {s.delta}"
            case KeyboardKeyAction() as k:
                name: str = f" ({k.key_name})" if k.key_name else ""
                return f"Key {k.state.value.title()} -> VK: {k.vk_code}{name}"
            case DelayAction() as d:
                jitter: str = f" ±{d.jitter_ms:.1f}ms" if d.jitter_ms > 0 else ""
                return f"Pause execution{jitter}"
            case CvTriggerAction() as c:
                return f"Find '{c.template_path}' (≥{int(c.confidence_threshold * 100)}%)"
            case LoopContainerAction() as lp:
                return f"Repeat {len(lp.actions)} sub-actions ({lp.iterations}x)"

    def _format_action_timing(self, action: ActionNode) -> str:
        match action:
            case MouseMoveAction() as m:
                return f"{m.duration_ms:.1f} ms"
            case DelayAction() as d:
                return f"{d.duration_ms:.1f} ms"
            case CvTriggerAction() as c:
                return f"Timeout: {c.timeout_seconds:.1f}s"
            case _:
                return "0.0 ms"

    def set_sequence(self, sequence: MacroSequence) -> None:
        self.beginResetModel()
        self._actions = list(sequence.actions)
        self._sequence_name = sequence.name
        self._sequence_description = sequence.description
        self._sequence_author = sequence.author
        self.endResetModel()

    def get_action(self, row: int) -> ActionNode | None:
        if 0 <= row < len(self._actions):
            return self._actions[row]
        return None

    def update_action(self, row: int, updated: ActionNode) -> bool:
        if not (0 <= row < len(self._actions)):
            return False
        self._actions[row] = updated
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))
        return True

    def append_action(self, action: ActionNode) -> None:
        row: int = len(self._actions)
        self.beginInsertRows(QModelIndex(), row, row)
        self._actions.append(action)
        self.endInsertRows()

    def remove_action(self, row: int) -> bool:
        if not (0 <= row < len(self._actions)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._actions[row]
        self.endRemoveRows()
        return True

    def move_action(self, source_row: int, dest_row: int) -> bool:
        if source_row == dest_row:
            return False
        if not (0 <= source_row < len(self._actions)) or not (0 <= dest_row < len(self._actions)):
            return False

        target_row: int = dest_row + 1 if dest_row > source_row else dest_row
        if not self.beginMoveRows(QModelIndex(), source_row, source_row, QModelIndex(), target_row):
            return False

        item: ActionNode = self._actions.pop(source_row)
        self._actions.insert(dest_row, item)
        self.endMoveRows()
        return True

    def clear(self) -> None:
        self.beginResetModel()
        self._actions.clear()
        self.endResetModel()

    def to_macro_sequence(self) -> MacroSequence:
        return MacroSequence(
            name=self._sequence_name,
            description=self._sequence_description,
            author=self._sequence_author,
            actions=list(self._actions),
        )