# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
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
from src.core.enums import ButtonState, KeyState, LoopType, MouseButton

__all__: Final[list[str]] = ["ActionInspectorView"]


class ActionInspectorView(QWidget):
    """Unified Action Component providing an Action Library and dynamic parameter Inspector."""

    action_updated: Signal = Signal(int, object)
    action_created: Signal = Signal(object)
    request_cv_capture: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_row: int = -1
        self._current_action: ActionNode | None = None

        self._root_layout: QVBoxLayout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(6, 6, 6, 6)

        self._tabs: QTabWidget = QTabWidget(self)
        self._root_layout.addWidget(self._tabs)

        self._build_properties_tab()
        self._build_toolbox_tab()

        self._bind_shortcuts()
        self.set_active_tab(1)

    def set_active_tab(self, index: int) -> None:
        self._tabs.setCurrentIndex(index)

    def _build_properties_tab(self) -> None:
        self._prop_tab: QWidget = QWidget(self._tabs)
        layout: QVBoxLayout = QVBoxLayout(self._prop_tab)
        layout.setContentsMargins(6, 6, 6, 6)

        self._prop_header: QLabel = QLabel("Select an action from timeline", self._prop_tab)
        self._prop_header.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #00E676; padding: 4px;"
        )
        layout.addWidget(self._prop_header)

        self._group: QGroupBox = QGroupBox("Parameters", self._prop_tab)
        self._group_layout: QVBoxLayout = QVBoxLayout(self._group)
        self._group_layout.setContentsMargins(4, 4, 4, 4)

        self._stack: QStackedWidget = QStackedWidget(self._group)
        self._group_layout.addWidget(self._stack)
        layout.addWidget(self._group)

        self._build_mouse_move_page()
        self._build_mouse_button_page()
        self._build_mouse_scroll_page()
        self._build_keyboard_key_page()
        self._build_delay_page()
        self._build_cv_trigger_page()
        self._build_loop_container_page()

        self._btn_save: QPushButton = QPushButton("Apply Changes (Ctrl+Enter)")
        self._btn_save.setStyleSheet("background-color: #00796B; font-weight: bold; padding: 6px;")
        self._btn_save.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._btn_save)

        self._empty_label: QLabel = QLabel("No action selected.\nPick an action from the timeline or add one from the Library.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        layout.addStretch()
        self._tabs.addTab(self._prop_tab, "⚙ Properties")
        self._set_editor_visible(False)

    def _build_toolbox_tab(self) -> None:
        self._tool_tab: QWidget = QWidget(self._tabs)
        layout: QVBoxLayout = QVBoxLayout(self._tool_tab)
        layout.setContentsMargins(6, 6, 6, 6)

        intro = QLabel("Click an action to insert it into the sequence:")
        intro.setStyleSheet("color: #B0BEC5; padding: 2px;")
        layout.addWidget(intro)

        # Mouse Group
        mouse_box = QGroupBox("Mouse Actions", self._tool_tab)
        mouse_grid = QGridLayout(mouse_box)
        btn_move = QPushButton("🖱 Move Cursor")
        btn_click = QPushButton("👆 Mouse Click")
        btn_scroll = QPushButton("📜 Scroll Wheel")
        btn_move.clicked.connect(self._create_mouse_move)
        btn_click.clicked.connect(self._create_mouse_click)
        btn_scroll.clicked.connect(self._create_mouse_scroll)
        mouse_grid.addWidget(btn_move, 0, 0)
        mouse_grid.addWidget(btn_click, 0, 1)
        mouse_grid.addWidget(btn_scroll, 1, 0, 1, 2)
        layout.addWidget(mouse_box)

        # Keyboard Group
        kb_box = QGroupBox("Keyboard Actions", self._tool_tab)
        kb_layout = QHBoxLayout(kb_box)
        btn_key = QPushButton("⌨ Key Press")
        btn_key.clicked.connect(self._create_keyboard_key)
        kb_layout.addWidget(btn_key)
        layout.addWidget(kb_box)

        # Timing Group
        timing_box = QGroupBox("Timing Actions", self._tool_tab)
        timing_layout = QHBoxLayout(timing_box)
        btn_delay = QPushButton("⏱ Delay / Pause")
        btn_delay.clicked.connect(self._create_delay)
        timing_layout.addWidget(btn_delay)
        layout.addWidget(timing_box)

        # Loop Control Flow Group (All Coding Loops)
        loop_box = QGroupBox("Control Flow Loops", self._tool_tab)
        loop_grid = QGridLayout(loop_box)
        btn_loop_count = QPushButton("🔁 For (Count)")
        btn_loop_infinite = QPushButton("♾ While True")
        btn_loop_duration = QPushButton("⏱ While Time")
        btn_loop_cv = QPushButton("👁 Until Visual")

        btn_loop_count.clicked.connect(lambda: self._create_loop(LoopType.COUNT))
        btn_loop_infinite.clicked.connect(lambda: self._create_loop(LoopType.INFINITE))
        btn_loop_duration.clicked.connect(lambda: self._create_loop(LoopType.DURATION))
        btn_loop_cv.clicked.connect(lambda: self._create_loop(LoopType.UNTIL_CV))

        loop_grid.addWidget(btn_loop_count, 0, 0)
        loop_grid.addWidget(btn_loop_infinite, 0, 1)
        loop_grid.addWidget(btn_loop_duration, 1, 0)
        loop_grid.addWidget(btn_loop_cv, 1, 1)
        layout.addWidget(loop_box)

        # Vision Group
        vision_box = QGroupBox("Computer Vision", self._tool_tab)
        vision_layout = QVBoxLayout(vision_box)
        btn_cv = QPushButton("👁 Grab CV Template Gate (Ctrl+G)")
        btn_cv.setStyleSheet("background-color: #2E7D32; font-weight: bold; padding: 6px;")
        btn_cv.clicked.connect(self.request_cv_capture.emit)
        vision_layout.addWidget(btn_cv)
        layout.addWidget(vision_box)

        layout.addStretch()
        self._tabs.addTab(self._tool_tab, "➕ Action Library")

    def _create_mouse_move(self) -> None:
        self.action_created.emit(MouseMoveAction(x=500, y=500, duration_ms=100.0, is_relative=False))

    def _create_mouse_click(self) -> None:
        self.action_created.emit(MouseButtonAction(button=MouseButton.LEFT, state=ButtonState.CLICK))

    def _create_mouse_scroll(self) -> None:
        self.action_created.emit(MouseScrollAction(delta=-120, horizontal=False))

    def _create_keyboard_key(self) -> None:
        self.action_created.emit(KeyboardKeyAction(vk_code=13, scan_code=28, state=KeyState.KEY_PRESS, key_name="Enter"))

    def _create_delay(self) -> None:
        self.action_created.emit(DelayAction(duration_ms=500.0, jitter_ms=0.0))

    def _create_loop(self, loop_type: LoopType) -> None:
        loop_action = LoopContainerAction(
            loop_type=loop_type,
            iterations=3 if loop_type == LoopType.COUNT else 1,
            duration_seconds=10.0,
            actions=[],
        )
        self.action_created.emit(loop_action)

    def _build_mouse_move_page(self) -> None:
        self._page_move: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_move)

        self._move_x_spin: QSpinBox = QSpinBox()
        self._move_x_spin.setRange(-32768, 32767)
        self._move_y_spin: QSpinBox = QSpinBox()
        self._move_y_spin.setRange(-32768, 32767)

        self._move_duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._move_duration_spin.setRange(0.0, 3600000.0)
        self._move_duration_spin.setSuffix(" ms")

        self._move_relative_check: QCheckBox = QCheckBox("Is Relative")

        layout.addRow("X:", self._move_x_spin)
        layout.addRow("Y:", self._move_y_spin)
        layout.addRow("Duration:", self._move_duration_spin)
        layout.addRow("", self._move_relative_check)
        self._stack.addWidget(self._page_move)

    def _build_mouse_button_page(self) -> None:
        self._page_button: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_button)

        self._btn_button_combo: QComboBox = QComboBox()
        for btn in MouseButton:
            self._btn_button_combo.addItem(btn.value.title(), btn)

        self._btn_state_combo: QComboBox = QComboBox()
        for state in ButtonState:
            self._btn_state_combo.addItem(state.value.title(), state)

        self._btn_x_spin: QSpinBox = QSpinBox()
        self._btn_x_spin.setRange(-32768, 32767)
        self._btn_y_spin: QSpinBox = QSpinBox()
        self._btn_y_spin.setRange(-32768, 32767)

        layout.addRow("Button:", self._btn_button_combo)
        layout.addRow("State:", self._btn_state_combo)
        layout.addRow("X (Optional):", self._btn_x_spin)
        layout.addRow("Y (Optional):", self._btn_y_spin)
        self._stack.addWidget(self._page_button)

    def _build_mouse_scroll_page(self) -> None:
        self._page_scroll: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_scroll)

        self._scroll_delta_spin: QSpinBox = QSpinBox()
        self._scroll_delta_spin.setRange(-32768, 32767)
        self._scroll_horizontal_check: QCheckBox = QCheckBox("Is Horizontal")

        layout.addRow("Delta:", self._scroll_delta_spin)
        layout.addRow("", self._scroll_horizontal_check)
        self._stack.addWidget(self._page_scroll)

    def _build_keyboard_key_page(self) -> None:
        self._page_key: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_key)

        self._key_vk_spin: QSpinBox = QSpinBox()
        self._key_vk_spin.setRange(0, 255)

        self._key_state_combo: QComboBox = QComboBox()
        for kstate in KeyState:
            self._key_state_combo.addItem(kstate.value.title(), kstate)

        self._key_name_edit: QLineEdit = QLineEdit()

        layout.addRow("VK Code:", self._key_vk_spin)
        layout.addRow("State:", self._key_state_combo)
        layout.addRow("Key Name:", self._key_name_edit)
        self._stack.addWidget(self._page_key)

    def _build_delay_page(self) -> None:
        self._page_delay: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_delay)

        self._delay_duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._delay_duration_spin.setRange(0.0, 3600000.0)
        self._delay_duration_spin.setSuffix(" ms")

        self._delay_jitter_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._delay_jitter_spin.setRange(0.0, 60000.0)
        self._delay_jitter_spin.setSuffix(" ms")

        layout.addRow("Duration:", self._delay_duration_spin)
        layout.addRow("Jitter (±):", self._delay_jitter_spin)
        self._stack.addWidget(self._page_delay)

    def _build_cv_trigger_page(self) -> None:
        self._page_cv: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_cv)

        self._cv_template_edit: QLineEdit = QLineEdit()
        self._cv_confidence_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._cv_confidence_spin.setRange(0.0, 1.0)
        self._cv_confidence_spin.setSingleStep(0.05)

        self._cv_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._cv_timeout_spin.setRange(0.1, 3600.0)
        self._cv_timeout_spin.setSuffix(" s")

        layout.addRow("Template:", self._cv_template_edit)
        layout.addRow("Confidence:", self._cv_confidence_spin)
        layout.addRow("Timeout:", self._cv_timeout_spin)
        self._stack.addWidget(self._page_cv)

    def _build_loop_container_page(self) -> None:
        self._page_loop: QWidget = QWidget(self._stack)
        self._loop_layout: QFormLayout = QFormLayout(self._page_loop)

        self._loop_type_combo: QComboBox = QComboBox()
        self._loop_type_combo.addItem("for _ in range(N) [Count]", LoopType.COUNT)
        self._loop_type_combo.addItem("while True [Infinite]", LoopType.INFINITE)
        self._loop_type_combo.addItem("while elapsed < T [Duration]", LoopType.DURATION)
        self._loop_type_combo.addItem("while vision.exists [Visual Condition]", LoopType.WHILE_CV)
        self._loop_type_combo.addItem("until vision.exists [Visual Condition]", LoopType.UNTIL_CV)
        self._loop_type_combo.currentIndexChanged.connect(self._on_loop_type_changed)

        self._loop_iterations_spin: QSpinBox = QSpinBox()
        self._loop_iterations_spin.setRange(1, 1000000)

        self._loop_duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_duration_spin.setRange(0.1, 86400.0)
        self._loop_duration_spin.setSuffix(" s")

        self._loop_template_edit: QLineEdit = QLineEdit()
        self._loop_confidence_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_confidence_spin.setRange(0.0, 1.0)
        self._loop_confidence_spin.setSingleStep(0.05)

        self._loop_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_timeout_spin.setRange(0.1, 3600.0)
        self._loop_timeout_spin.setSuffix(" s")

        self._loop_layout.addRow("Loop Type:", self._loop_type_combo)
        self._loop_layout.addRow("Iterations:", self._loop_iterations_spin)
        self._loop_layout.addRow("Duration:", self._loop_duration_spin)
        self._loop_layout.addRow("CV Template:", self._loop_template_edit)
        self._loop_layout.addRow("Confidence:", self._loop_confidence_spin)
        self._loop_layout.addRow("Timeout:", self._loop_timeout_spin)

        self._stack.addWidget(self._page_loop)

    def _on_loop_type_changed(self) -> None:
        selected_type = self._loop_type_combo.currentData()
        is_count = selected_type == LoopType.COUNT
        is_duration = selected_type == LoopType.DURATION
        is_cv = selected_type in (LoopType.WHILE_CV, LoopType.UNTIL_CV)

        self._loop_iterations_spin.setVisible(is_count)
        self._loop_duration_spin.setVisible(is_duration)
        self._loop_template_edit.setVisible(is_cv)
        self._loop_confidence_spin.setVisible(is_cv)
        self._loop_timeout_spin.setVisible(is_cv)

    def _bind_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_save_clicked, context=ctx)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self._on_save_clicked, context=ctx)

    def _set_editor_visible(self, visible: bool) -> None:
        self._group.setVisible(visible)
        self._btn_save.setVisible(visible)
        self._prop_header.setVisible(visible)
        self._empty_label.setVisible(not visible)

    def inspect(self, row: int, action: ActionNode | None) -> None:
        self._current_row = row
        self._current_action = action

        if action is None or row < 0:
            self._set_editor_visible(False)
            self._prop_header.setText("No action selected")
            return

        self._set_editor_visible(True)
        self._prop_header.setText(f"Action #{row + 1}: {action.action_type.value.upper()}")
        self._tabs.setCurrentIndex(0)

        match action:
            case MouseMoveAction() as m:
                self._move_x_spin.setValue(m.x)
                self._move_y_spin.setValue(m.y)
                self._move_duration_spin.setValue(m.duration_ms)
                self._move_relative_check.setChecked(m.is_relative)
                self._stack.setCurrentWidget(self._page_move)

            case MouseButtonAction() as b:
                self._btn_button_combo.setCurrentText(b.button.value.title())
                self._btn_state_combo.setCurrentText(b.state.value.title())
                self._btn_x_spin.setValue(b.x if b.x is not None else 0)
                self._btn_y_spin.setValue(b.y if b.y is not None else 0)
                self._stack.setCurrentWidget(self._page_button)

            case MouseScrollAction() as s:
                self._scroll_delta_spin.setValue(s.delta)
                self._scroll_horizontal_check.setChecked(s.horizontal)
                self._stack.setCurrentWidget(self._page_scroll)

            case KeyboardKeyAction() as k:
                self._key_vk_spin.setValue(k.vk_code)
                self._key_state_combo.setCurrentText(k.state.value.title())
                self._key_name_edit.setText(k.key_name)
                self._stack.setCurrentWidget(self._page_key)

            case DelayAction() as d:
                self._delay_duration_spin.setValue(d.duration_ms)
                self._delay_jitter_spin.setValue(d.jitter_ms)
                self._stack.setCurrentWidget(self._page_delay)

            case CvTriggerAction() as c:
                self._cv_template_edit.setText(c.template_path)
                self._cv_template_edit.setPlaceholderText(
                    "(Embedded Image)" if c.image_base64 else "Path to template image file"
                )
                self._cv_confidence_spin.setValue(c.confidence_threshold)
                self._cv_timeout_spin.setValue(c.timeout_seconds)
                self._stack.setCurrentWidget(self._page_cv)

            case LoopContainerAction() as lp:
                idx = self._loop_type_combo.findData(lp.loop_type)
                if idx >= 0:
                    self._loop_type_combo.setCurrentIndex(idx)
                self._loop_iterations_spin.setValue(lp.iterations)
                self._loop_duration_spin.setValue(lp.duration_seconds)
                self._loop_template_edit.setText(lp.template_path)
                self._loop_confidence_spin.setValue(lp.confidence_threshold)
                self._loop_timeout_spin.setValue(lp.timeout_seconds)
                self._on_loop_type_changed()
                self._stack.setCurrentWidget(self._page_loop)

    def _on_save_clicked(self) -> None:
        if self._current_action is None or self._current_row < 0:
            return

        updated: ActionNode | None = None
        match self._current_action:
            case MouseMoveAction() as m:
                updated = MouseMoveAction(
                    id=m.id,
                    description=m.description,
                    enabled=m.enabled,
                    x=self._move_x_spin.value(),
                    y=self._move_y_spin.value(),
                    duration_ms=self._move_duration_spin.value(),
                    is_relative=self._move_relative_check.isChecked(),
                )
            case MouseButtonAction() as b:
                btn_item = self._btn_button_combo.currentData()
                state_item = self._btn_state_combo.currentData()
                if isinstance(btn_item, MouseButton) and isinstance(state_item, ButtonState):
                    updated = MouseButtonAction(
                        id=b.id,
                        description=b.description,
                        enabled=b.enabled,
                        button=btn_item,
                        state=state_item,
                        x=self._btn_x_spin.value() if self._btn_x_spin.value() != 0 else None,
                        y=self._btn_y_spin.value() if self._btn_y_spin.value() != 0 else None,
                    )
            case MouseScrollAction() as s:
                updated = MouseScrollAction(
                    id=s.id,
                    description=s.description,
                    enabled=s.enabled,
                    delta=self._scroll_delta_spin.value(),
                    horizontal=self._scroll_horizontal_check.isChecked(),
                )
            case KeyboardKeyAction() as k:
                kstate_item = self._key_state_combo.currentData()
                if isinstance(kstate_item, KeyState):
                    updated = KeyboardKeyAction(
                        id=k.id,
                        description=k.description,
                        enabled=k.enabled,
                        vk_code=self._key_vk_spin.value(),
                        scan_code=k.scan_code,
                        state=kstate_item,
                        is_extended=k.is_extended,
                        key_name=self._key_name_edit.text(),
                    )
            case DelayAction() as d:
                updated = DelayAction(
                    id=d.id,
                    description=d.description,
                    enabled=d.enabled,
                    duration_ms=self._delay_duration_spin.value(),
                    jitter_ms=self._delay_jitter_spin.value(),
                )
            case CvTriggerAction() as c:
                updated = CvTriggerAction(
                    id=c.id,
                    description=c.description,
                    enabled=c.enabled,
                    template_path=self._cv_template_edit.text(),
                    image_base64=c.image_base64,
                    confidence_threshold=self._cv_confidence_spin.value(),
                    timeout_seconds=self._cv_timeout_spin.value(),
                )
            case LoopContainerAction() as lp:
                selected_type = self._loop_type_combo.currentData()
                if isinstance(selected_type, LoopType):
                    updated = LoopContainerAction(
                        id=lp.id,
                        description=lp.description,
                        enabled=lp.enabled,
                        loop_type=selected_type,
                        iterations=self._loop_iterations_spin.value(),
                        duration_seconds=self._loop_duration_spin.value(),
                        template_path=self._loop_template_edit.text(),
                        image_base64=lp.image_base64,
                        confidence_threshold=self._loop_confidence_spin.value(),
                        timeout_seconds=self._loop_timeout_spin.value(),
                        actions=lp.actions,
                    )

        if updated is not None:
            self._current_action = updated
            self.action_updated.emit(self._current_row, updated)