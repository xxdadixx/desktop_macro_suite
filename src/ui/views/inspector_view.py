# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.ast import (
    ActionNode,
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.enums import ButtonState, KeyState, MouseButton

__all__: Final[list[str]] = ["ActionInspectorView"]


class ActionInspectorView(QWidget):
    """Dynamic AST node inspector and property editor."""

    action_updated: Signal = Signal(int, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_row: int = -1
        self._current_action: ActionNode | None = None

        self._root_layout: QVBoxLayout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(8, 8, 8, 8)

        self._group: QGroupBox = QGroupBox("Action Properties", self)
        self._form_layout: QFormLayout = QFormLayout(self._group)
        self._root_layout.addWidget(self._group)

        # Form Controls
        self._x_spin: QSpinBox = QSpinBox()
        self._x_spin.setRange(-32768, 32767)
        self._y_spin: QSpinBox = QSpinBox()
        self._y_spin.setRange(-32768, 32767)

        self._duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._duration_spin.setRange(0.0, 3600000.0)
        self._duration_spin.setSuffix(" ms")

        self._jitter_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._jitter_spin.setRange(0.0, 60000.0)
        self._jitter_spin.setSuffix(" ms")

        self._relative_check: QCheckBox = QCheckBox("Is Relative")

        self._mouse_button_combo: QComboBox = QComboBox()
        for btn in MouseButton:
            self._mouse_button_combo.addItem(btn.value.title(), btn)

        self._button_state_combo: QComboBox = QComboBox()
        for state in ButtonState:
            self._button_state_combo.addItem(state.value.title(), state)

        self._key_state_combo: QComboBox = QComboBox()
        for kstate in KeyState:
            self._key_state_combo.addItem(kstate.value.title(), kstate)

        self._delta_spin: QSpinBox = QSpinBox()
        self._delta_spin.setRange(-32768, 32767)

        self._vk_spin: QSpinBox = QSpinBox()
        self._vk_spin.setRange(0, 255)

        self._key_name_edit: QLineEdit = QLineEdit()

        self._template_path_edit: QLineEdit = QLineEdit()
        self._confidence_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._confidence_spin.setRange(0.0, 1.0)
        self._confidence_spin.setSingleStep(0.05)

        self._timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._timeout_spin.setRange(0.1, 3600.0)
        self._timeout_spin.setSuffix(" s")

        self._iterations_spin: QSpinBox = QSpinBox()
        self._iterations_spin.setRange(1, 1000000)

        self._btn_save: QPushButton = QPushButton("Apply Changes")
        self._btn_save.clicked.connect(self._on_save_clicked)
        self._root_layout.addWidget(self._btn_save)

        self._empty_label: QLabel = QLabel("Select an action to inspect parameters.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root_layout.addWidget(self._empty_label)

        self._set_editor_visible(False)

    def _set_editor_visible(self, visible: bool) -> None:
        self._group.setVisible(visible)
        self._btn_save.setVisible(visible)
        self._empty_label.setVisible(not visible)

    def inspect(self, row: int, action: ActionNode | None) -> None:
        self._current_row = row
        self._current_action = action

        if action is None or row < 0:
            self._set_editor_visible(False)
            return

        self._clear_form()
        self._set_editor_visible(True)

        match action:
            case MouseMoveAction() as m:
                self._x_spin.setValue(m.x)
                self._y_spin.setValue(m.y)
                self._duration_spin.setValue(m.duration_ms)
                self._relative_check.setChecked(m.is_relative)
                self._form_layout.addRow("X:", self._x_spin)
                self._form_layout.addRow("Y:", self._y_spin)
                self._form_layout.addRow("Duration:", self._duration_spin)
                self._form_layout.addRow("", self._relative_check)

            case MouseButtonAction() as b:
                self._mouse_button_combo.setCurrentText(b.button.value.title())
                self._button_state_combo.setCurrentText(b.state.value.title())
                self._x_spin.setValue(b.x if b.x is not None else 0)
                self._y_spin.setValue(b.y if b.y is not None else 0)
                self._form_layout.addRow("Button:", self._mouse_button_combo)
                self._form_layout.addRow("State:", self._button_state_combo)
                self._form_layout.addRow("X:", self._x_spin)
                self._form_layout.addRow("Y:", self._y_spin)

            case MouseScrollAction() as s:
                self._delta_spin.setValue(s.delta)
                self._relative_check.setChecked(s.horizontal)
                self._relative_check.setText("Is Horizontal")
                self._form_layout.addRow("Delta:", self._delta_spin)
                self._form_layout.addRow("", self._relative_check)

            case KeyboardKeyAction() as k:
                self._vk_spin.setValue(k.vk_code)
                self._key_state_combo.setCurrentText(k.state.value.title())
                self._key_name_edit.setText(k.key_name)
                self._form_layout.addRow("VK Code:", self._vk_spin)
                self._form_layout.addRow("State:", self._key_state_combo)
                self._form_layout.addRow("Key Name:", self._key_name_edit)

            case DelayAction() as d:
                self._duration_spin.setValue(d.duration_ms)
                self._jitter_spin.setValue(d.jitter_ms)
                self._form_layout.addRow("Duration:", self._duration_spin)
                self._form_layout.addRow("Jitter (±):", self._jitter_spin)

            case CvTriggerAction() as c:
                self._template_path_edit.setText(c.template_path)
                self._confidence_spin.setValue(c.confidence_threshold)
                self._timeout_spin.setValue(c.timeout_seconds)
                self._form_layout.addRow("Template:", self._template_path_edit)
                self._form_layout.addRow("Confidence:", self._confidence_spin)
                self._form_layout.addRow("Timeout:", self._timeout_spin)

            case LoopContainerAction() as lp:
                self._iterations_spin.setValue(lp.iterations)
                self._form_layout.addRow("Iterations:", self._iterations_spin)

    def _clear_form(self) -> None:
        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)

    def _on_save_clicked(self) -> None:
        if self._current_action is None or self._current_row < 0:
            return

        updated: ActionNode | None = None
        match self._current_action:
            case MouseMoveAction() as m:
                updated = MouseMoveAction(
                    id=m.id,
                    x=self._x_spin.value(),
                    y=self._y_spin.value(),
                    duration_ms=self._duration_spin.value(),
                    is_relative=self._relative_check.isChecked(),
                )
            case MouseButtonAction() as b:
                btn_item = self._mouse_button_combo.currentData()
                state_item = self._button_state_combo.currentData()
                if isinstance(btn_item, MouseButton) and isinstance(state_item, ButtonState):
                    updated = MouseButtonAction(
                        id=b.id,
                        button=btn_item,
                        state=state_item,
                        x=self._x_spin.value(),
                        y=self._y_spin.value(),
                    )
            case MouseScrollAction() as s:
                updated = MouseScrollAction(
                    id=s.id,
                    delta=self._delta_spin.value(),
                    horizontal=self._relative_check.isChecked(),
                )
            case KeyboardKeyAction() as k:
                kstate_item = self._key_state_combo.currentData()
                if isinstance(kstate_item, KeyState):
                    updated = KeyboardKeyAction(
                        id=k.id,
                        vk_code=self._vk_spin.value(),
                        scan_code=k.scan_code,
                        state=kstate_item,
                        key_name=self._key_name_edit.text(),
                    )
            case DelayAction() as d:
                updated = DelayAction(
                    id=d.id,
                    duration_ms=self._duration_spin.value(),
                    jitter_ms=self._jitter_spin.value(),
                )
            case CvTriggerAction() as c:
                updated = CvTriggerAction(
                    id=c.id,
                    template_path=self._template_path_edit.text(),
                    confidence_threshold=self._confidence_spin.value(),
                    timeout_seconds=self._timeout_spin.value(),
                )
            case LoopContainerAction() as lp:
                updated = LoopContainerAction(
                    id=lp.id,
                    iterations=self._iterations_spin.value(),
                    actions=lp.actions,
                )

        if updated is not None:
            self._current_action = updated
            self.action_updated.emit(self._current_row, updated)