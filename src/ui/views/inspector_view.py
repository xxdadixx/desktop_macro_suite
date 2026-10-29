# pyright: reportUntypedBaseClass=false
from __future__ import annotations

import base64
from enum import StrEnum
from pathlib import Path
from typing import Final, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QMouseEvent, QPixmap, QShortcut
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
    CvBranchCase,
    CvMultiTriggerAction,
    CvTriggerAction,
    DelayAction,
    FlowControlAction,
    IfElseContainerAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MiniGameSolverAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
    SetVariableAction,
)
from src.core.enums import (
    ButtonState,
    CvFailurePolicy,
    CvMatchMode,
    CvMouseAction,
    CvSelectionStrategy,
    FlowSignal,
    KeyState,
    LoopType,
    MouseButton,
    RabbitSlot,
    TriggerComparison,
    VariableOp,
)
from src.vision.matcher import MatchResult

__all__: Final[list[str]] = ["ActionInspectorView", "CoordinatePickButton"]


def _coerce_enum[T: StrEnum](val: object, enum_cls: type[T]) -> T | None:
    """Safely coerces Python enum or Qt-unboxed string variants into the concrete StrEnum type."""
    if isinstance(val, enum_cls):
        return val
    if isinstance(val, str):
        try:
            return enum_cls(val)
        except ValueError:
            return None
    return None


class CoordinatePickButton(QPushButton):
    """Action button that initiates coordinate drag-picking immediately upon mouse press."""

    pick_requested: Signal = Signal()

    def __init__(
        self,
        text: str = "🎯 Drag / Pick Screen Location",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            "QPushButton {"
            "  background-color: #0277BD;"
            "  color: #FFFFFF;"
            "  font-weight: bold;"
            "  padding: 6px 10px;"
            "  border-radius: 4px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #0288D1;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #01579B;"
            "}"
        )
        self.setToolTip("Click or drag directly onto the target desktop location (Ctrl+Shift+C)")

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.pick_requested.emit()


class ActionInspectorView(QWidget):
    """Unified Action Component providing an Action Library and dynamic parameter Inspector."""

    action_updated: Signal = Signal(int, object)
    action_created: Signal = Signal(object)
    request_cv_capture: Signal = Signal()
    request_recrop_cv: Signal = Signal()
    request_coordinate_pick: Signal = Signal()
    request_test_cv: Signal = Signal(object)
    request_locate_crop: Signal = Signal(int, int, int, int)

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
        self._build_cv_multi_trigger_page()
        self._build_loop_container_page()
        self._build_set_variable_page()
        self._build_if_else_page()
        self._build_flow_control_page()
        self._build_minigame_solver_page()

        self._btn_save: QPushButton = QPushButton("Apply Changes (Ctrl+Enter)")
        self._btn_save.setStyleSheet("background-color: #00796B; font-weight: bold; padding: 6px;")
        self._btn_save.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._btn_save)

        self._empty_label: QLabel = QLabel(
            "No action selected.\nPick an action from the timeline or add one from the Library."
        )
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

        # 1. Variables & State
        var_box = QGroupBox("Variables & State", self._tool_tab)
        var_layout = QHBoxLayout(var_box)
        btn_set_var = QPushButton("📝 Set Variable")
        btn_set_var.setToolTip("Create or mutate a scoped runtime variable")
        btn_set_var.clicked.connect(self._create_set_variable)
        var_layout.addWidget(btn_set_var)
        layout.addWidget(var_box)

        # 2. Conditional Logic
        cond_box = QGroupBox("Conditional Branching", self._tool_tab)
        cond_layout = QHBoxLayout(cond_box)
        btn_if_else = QPushButton("🔀 If / Else Condition")
        btn_if_else.setStyleSheet("background-color: #4A148C; font-weight: bold; padding: 5px;")
        btn_if_else.setToolTip("Evaluate expression against variables and branch execution")
        btn_if_else.clicked.connect(self._create_if_else)
        cond_layout.addWidget(btn_if_else)
        layout.addWidget(cond_box)

        # 3. Control Flow Signals
        flow_box = QGroupBox("Flow Interrupters", self._tool_tab)
        flow_layout = QHBoxLayout(flow_box)
        btn_break = QPushButton("🛑 Break")
        btn_break.setToolTip("Break out of enclosing loop immediately")
        btn_break.clicked.connect(lambda: self._create_flow_control(FlowSignal.BREAK))
        btn_cont = QPushButton("⏭ Continue")
        btn_cont.setToolTip("Skip to the next iteration of enclosing loop")
        btn_cont.clicked.connect(lambda: self._create_flow_control(FlowSignal.CONTINUE))
        btn_exit = QPushButton("🚪 Exit Macro")
        btn_exit.setToolTip("Halt and abort entire macro execution")
        btn_exit.clicked.connect(lambda: self._create_flow_control(FlowSignal.ABORT))
        flow_layout.addWidget(btn_break)
        flow_layout.addWidget(btn_cont)
        flow_layout.addWidget(btn_exit)
        layout.addWidget(flow_box)

        # 4. Mouse Actions
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

        # 5. Keyboard Actions
        kb_box = QGroupBox("Keyboard Actions", self._tool_tab)
        kb_layout = QHBoxLayout(kb_box)
        btn_key = QPushButton("⌨ Key Press")
        btn_key.clicked.connect(self._create_keyboard_key)
        kb_layout.addWidget(btn_key)
        layout.addWidget(kb_box)

        # 6. Timing Actions
        timing_box = QGroupBox("Timing Actions", self._tool_tab)
        timing_layout = QHBoxLayout(timing_box)
        btn_delay = QPushButton("⏱ Delay / Pause")
        btn_delay.clicked.connect(self._create_delay)
        timing_layout.addWidget(btn_delay)
        layout.addWidget(timing_box)

        # 7. Loops
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

        # 8. Computer Vision
        vision_box = QGroupBox("Computer Vision", self._tool_tab)
        vision_layout = QVBoxLayout(vision_box)
        btn_cv = QPushButton("👁 Grab CV Template Gate (Ctrl+G)")
        btn_cv.setStyleSheet("background-color: #2E7D32; font-weight: bold; padding: 6px;")
        btn_cv.clicked.connect(self.request_cv_capture.emit)
        vision_layout.addWidget(btn_cv)
        layout.addWidget(vision_box)

        # 9. Mini-Game Automation
        game_box = QGroupBox("Mini-Game Automation", self._tool_tab)
        game_layout = QVBoxLayout(game_box)
        btn_solver = QPushButton("🎮 Mooncake Mini-Game Solver")
        btn_solver.setStyleSheet("background-color: #00695C; font-weight: bold; padding: 6px;")
        btn_solver.setToolTip("Auto-detect adjacent plates, count cakes, and click optimal tile")
        btn_solver.clicked.connect(self._create_minigame_solver)
        game_layout.addWidget(btn_solver)
        layout.addWidget(game_box)

        layout.addStretch()
        self._tabs.addTab(self._tool_tab, "➕ Action Library")

    def _create_set_variable(self) -> None:
        self.action_created.emit(
            SetVariableAction(name="counter", expression="0", operation=VariableOp.ASSIGN)
        )

    def _create_if_else(self) -> None:
        self.action_created.emit(
            IfElseContainerAction(condition="loop_index >= 1", then_actions=[], else_actions=[])
        )

    def _create_flow_control(self, signal: FlowSignal) -> None:
        reason = "Execution halted by user flow action" if signal == FlowSignal.ABORT else ""
        self.action_created.emit(FlowControlAction(signal=signal, reason=reason))

    def _create_mouse_move(self) -> None:
        self.action_created.emit(
            MouseMoveAction(x=500, y=500, duration_ms=0.0, is_relative=False)
        )

    def _create_mouse_click(self) -> None:
        self.action_created.emit(
            MouseButtonAction(button=MouseButton.LEFT, state=ButtonState.CLICK)
        )

    def _create_mouse_scroll(self) -> None:
        self.action_created.emit(MouseScrollAction(delta=-120, horizontal=False))

    def _create_keyboard_key(self) -> None:
        self.action_created.emit(
            KeyboardKeyAction(vk_code=13, scan_code=28, state=KeyState.KEY_PRESS, key_name="Enter")
        )

    def _create_delay(self) -> None:
        self.action_created.emit(DelayAction(duration_ms=0.0, jitter_ms=0.0))

    def _create_loop(self, loop_type: LoopType) -> None:
        loop_action = LoopContainerAction(
            loop_type=loop_type,
            iterations=3 if loop_type == LoopType.COUNT else 1,
            duration_seconds=10.0,
            actions=[],
        )
        self.action_created.emit(loop_action)

    def _create_minigame_solver(self) -> None:
        self.action_created.emit(
            MiniGameSolverAction(
                player_slot=RabbitSlot.RIGHT,
                player_name="DADI_",
                auto_click=True,
                timeout_seconds=8.0,
            )
        )

    def _build_set_variable_page(self) -> None:
        self._page_set_var: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_set_var)

        self._var_name_edit: QLineEdit = QLineEdit()
        self._var_name_edit.setPlaceholderText("e.g. counter, base_x, status")

        self._var_op_combo: QComboBox = QComboBox()
        self._var_op_combo.addItem("Assign (=)", VariableOp.ASSIGN)
        self._var_op_combo.addItem("Increment (+=)", VariableOp.INCREMENT)
        self._var_op_combo.addItem("Decrement (-=)", VariableOp.DECREMENT)
        self._var_op_combo.addItem("Append String (+=)", VariableOp.APPEND)

        self._var_expr_edit: QLineEdit = QLineEdit()
        self._var_expr_edit.setPlaceholderText("e.g. 10, loop_index + 1, 'active'")

        hint = QLabel("Expressions support integers, floats, strings, and active variables.")
        hint.setStyleSheet("color: #8B949E; font-size: 10px;")

        layout.addRow("Variable Name:", self._var_name_edit)
        layout.addRow("Operation:", self._var_op_combo)
        layout.addRow("Value / Expr:", self._var_expr_edit)
        layout.addRow("", hint)
        self._stack.addWidget(self._page_set_var)

    def _build_if_else_page(self) -> None:
        self._page_if_else: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_if_else)

        self._if_condition_edit: QLineEdit = QLineEdit()
        self._if_condition_edit.setPlaceholderText("e.g. loop_index >= 3 and counter < 10")

        guide_label = QLabel(
            "<b>Supported Syntax:</b><br>"
            "• Comparisons: <code>==, !=, &lt;, &gt;, &lt;=, &gt;=</code><br>"
            "• Boolean Logic: <code>and, or, not</code><br>"
            "• Loop Variables: <code>loop_index, loop_iteration, loop_first, loop_last</code><br><br>"
            "<i>Indent child actions below this block in the timeline to run them on True.</i>"
        )
        guide_label.setStyleSheet(
            "color: #ABB2BF; font-size: 10px; background: #1E222B; padding: 6px; border-radius: 4px;"
        )
        guide_label.setTextFormat(Qt.TextFormat.RichText)

        layout.addRow("Condition:", self._if_condition_edit)
        layout.addRow("", guide_label)
        self._stack.addWidget(self._page_if_else)

    def _build_flow_control_page(self) -> None:
        self._page_flow_ctrl: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_flow_ctrl)

        self._flow_signal_combo: QComboBox = QComboBox()
        self._flow_signal_combo.addItem("Break Loop", FlowSignal.BREAK)
        self._flow_signal_combo.addItem("Continue Loop", FlowSignal.CONTINUE)
        self._flow_signal_combo.addItem("Abort / Exit Macro", FlowSignal.ABORT)
        self._flow_signal_combo.currentIndexChanged.connect(self._on_flow_signal_changed)

        self._flow_reason_edit: QLineEdit = QLineEdit()
        self._flow_reason_edit.setPlaceholderText("Optional reason logged on exit")

        layout.addRow("Signal Action:", self._flow_signal_combo)
        layout.addRow("Exit Message:", self._flow_reason_edit)
        self._stack.addWidget(self._page_flow_ctrl)

    def _on_flow_signal_changed(self) -> None:
        sig = _coerce_enum(self._flow_signal_combo.currentData(), FlowSignal)
        self._flow_reason_edit.setEnabled(sig == FlowSignal.ABORT)

    def _build_minigame_solver_page(self) -> None:
        self._page_solver: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_solver)

        self._solver_slot_combo: QComboBox = QComboBox()
        self._solver_slot_combo.addItem("Auto-Detect Position", RabbitSlot.AUTO)
        self._solver_slot_combo.addItem("Top Rabbit", RabbitSlot.TOP)
        self._solver_slot_combo.addItem("Left Rabbit", RabbitSlot.LEFT)
        self._solver_slot_combo.addItem("Right Rabbit (DADI_)", RabbitSlot.RIGHT)
        self._solver_slot_combo.addItem("Bottom Rabbit", RabbitSlot.BOTTOM)

        self._solver_name_edit: QLineEdit = QLineEdit()
        self._solver_name_edit.setPlaceholderText("DADI_")

        self._solver_autoclick_check: QCheckBox = QCheckBox("Auto-Click Best Plate")
        self._solver_autoclick_check.setChecked(True)

        self._solver_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._solver_timeout_spin.setRange(0.5, 30.0)
        self._solver_timeout_spin.setSuffix(" s")

        hint = QLabel(
            "<b>Strategy:</b> Evaluates accessible adjacent plates and clicks max mooncakes (1, 2, or 3)."
        )
        hint.setStyleSheet("color: #00E676; font-size: 10px;")
        hint.setTextFormat(Qt.TextFormat.RichText)

        layout.addRow("Player Slot:", self._solver_slot_combo)
        layout.addRow("Player Name:", self._solver_name_edit)
        layout.addRow("", self._solver_autoclick_check)
        layout.addRow("Timeout Limit:", self._solver_timeout_spin)
        layout.addRow("", hint)
        self._stack.addWidget(self._page_solver)

    def _build_mouse_move_page(self) -> None:
        self._page_move: QWidget = QWidget(self._stack)
        layout = QFormLayout(self._page_move)
        self._move_pick_btn = CoordinatePickButton("🎯 Drag / Pick Target Position")
        self._move_pick_btn.pick_requested.connect(self.request_coordinate_pick.emit)
        self._move_x_spin: QSpinBox = QSpinBox()
        self._move_x_spin.setRange(-32768, 32767)
        self._move_y_spin: QSpinBox = QSpinBox()
        self._move_y_spin.setRange(-32768, 32767)
        self._move_duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._move_duration_spin.setRange(0.0, 3600000.0)
        self._move_duration_spin.setSuffix(" ms")
        self._move_relative_check: QCheckBox = QCheckBox("Is Relative")
        layout.addRow("", self._move_pick_btn)
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
        self._btn_use_coords_check: QCheckBox = QCheckBox("Specify Target Coordinates")
        self._btn_use_coords_check.toggled.connect(self._on_btn_coords_toggled)
        self._btn_pick_btn = CoordinatePickButton("🎯 Drag / Pick Target Position")
        self._btn_pick_btn.pick_requested.connect(self.request_coordinate_pick.emit)
        self._btn_x_spin: QSpinBox = QSpinBox()
        self._btn_x_spin.setRange(-32768, 32767)
        self._btn_y_spin: QSpinBox = QSpinBox()
        self._btn_y_spin.setRange(-32768, 32767)
        layout.addRow("Button:", self._btn_button_combo)
        layout.addRow("State:", self._btn_state_combo)
        layout.addRow("", self._btn_use_coords_check)
        layout.addRow("", self._btn_pick_btn)
        layout.addRow("X Coordinate:", self._btn_x_spin)
        layout.addRow("Y Coordinate:", self._btn_y_spin)
        self._stack.addWidget(self._page_button)

    def _on_btn_coords_toggled(self, checked: bool) -> None:
        self._btn_x_spin.setEnabled(checked)
        self._btn_y_spin.setEnabled(checked)
        self._btn_pick_btn.setEnabled(checked)

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
        layout = QVBoxLayout(self._page_cv)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        preview_box = QGroupBox("Template Image & Source Region", self._page_cv)
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)
        self._cv_preview_img: QLabel = QLabel(preview_box)
        self._cv_preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cv_preview_img.setStyleSheet(
            "background-color: #12151A; border: 1px solid #282C34; border-radius: 4px; min-height: 85px;"
        )
        preview_layout.addWidget(self._cv_preview_img)
        self._cv_preview_meta: QLabel = QLabel("No template loaded", preview_box)
        self._cv_preview_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cv_preview_meta.setStyleSheet("color: #00E676; font-size: 11px; font-weight: bold;")
        preview_layout.addWidget(self._cv_preview_meta)
        self._cv_crop_meta: QLabel = QLabel("Crop Area: Unknown", preview_box)
        self._cv_crop_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cv_crop_meta.setStyleSheet("color: #8B949E; font-size: 10px;")
        preview_layout.addWidget(self._cv_crop_meta)

        btn_row = QHBoxLayout()
        self._cv_btn_recrop: QPushButton = QPushButton("✂ Re-capture Crop Area", preview_box)
        self._cv_btn_recrop.setStyleSheet(
            "background-color: #E65100; color: #FFFFFF; font-weight: bold; padding: 4px;"
        )
        self._cv_btn_recrop.clicked.connect(self.request_recrop_cv.emit)
        btn_row.addWidget(self._cv_btn_recrop)
        self._cv_btn_locate_crop: QPushButton = QPushButton("📍 Locate on Screen", preview_box)
        self._cv_btn_locate_crop.setStyleSheet(
            "background-color: #0277BD; color: #FFFFFF; font-weight: bold; padding: 4px;"
        )
        self._cv_btn_locate_crop.clicked.connect(self._on_locate_crop_clicked)
        btn_row.addWidget(self._cv_btn_locate_crop)
        preview_layout.addLayout(btn_row)
        layout.addWidget(preview_box)

        test_box = QGroupBox("Pre-Execution Verification", self._page_cv)
        test_layout = QVBoxLayout(test_box)
        test_layout.setContentsMargins(6, 6, 6, 6)
        self._cv_btn_test_match: QPushButton = QPushButton("🧪 Test Match on Screen", test_box)
        self._cv_btn_test_match.setStyleSheet("background-color: #00897B; font-weight: bold; padding: 6px;")
        self._cv_btn_test_match.clicked.connect(self._on_test_cv_clicked)
        test_layout.addWidget(self._cv_btn_test_match)
        self._cv_test_feedback: QLabel = QLabel("Ready to test live match", test_box)
        self._cv_test_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cv_test_feedback.setStyleSheet(
            "font-size: 10px; color: #8B949E; padding: 4px; border: 1px dashed #3E4451; border-radius: 4px;"
        )
        test_layout.addWidget(self._cv_test_feedback)
        layout.addWidget(test_box)

        form_layout = QFormLayout()
        form_layout.setContentsMargins(2, 2, 2, 2)
        self._cv_template_edit: QLineEdit = QLineEdit()
        self._cv_match_mode_combo: QComboBox = QComboBox()
        self._cv_match_mode_combo.addItem("Standard Grayscale", CvMatchMode.STANDARD)
        self._cv_match_mode_combo.addItem("Edge / Contour Matching", CvMatchMode.EDGE)
        self._cv_search_area_combo: QComboBox = QComboBox()
        self._cv_search_area_combo.addItem("Full Desktop Surface", 0)
        self._cv_search_area_combo.addItem("Near Crop (±50 px)", 50)
        self._cv_search_area_combo.addItem("Near Crop (±100 px)", 100)
        self._cv_search_area_combo.addItem("Near Crop (±200 px)", 200)
        self._cv_confidence_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._cv_confidence_spin.setRange(0.0, 1.0)
        self._cv_confidence_spin.setSingleStep(0.05)
        self._cv_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._cv_timeout_spin.setRange(0.1, 3600.0)
        self._cv_timeout_spin.setSuffix(" s")
        self._cv_policy_combo: QComboBox = QComboBox()
        self._cv_policy_combo.addItem("assert vision.wait_for()", CvFailurePolicy.ABORT)
        self._cv_policy_combo.addItem("if vision.exists() ... else: pass", CvFailurePolicy.SKIP)
        self._cv_policy_combo.addItem("if not vision.exists(): break", CvFailurePolicy.BREAK_LOOP)
        self._cv_comparison_combo: QComboBox = QComboBox()
        self._cv_comparison_combo.addItem("Target Appears", TriggerComparison.APPEARS)
        self._cv_comparison_combo.addItem("Target Disappears", TriggerComparison.DISAPPEARS)
        self._cv_mouse_action_combo: QComboBox = QComboBox()
        self._cv_mouse_action_combo.addItem("🎯 Click Target", CvMouseAction.CLICK)
        self._cv_mouse_action_combo.addItem("👆 Double-Click", CvMouseAction.DOUBLE_CLICK)
        self._cv_mouse_action_combo.addItem("🖱 Right-Click", CvMouseAction.RIGHT_CLICK)
        self._cv_mouse_action_combo.addItem("📍 Move Cursor Only", CvMouseAction.MOVE_ONLY)
        self._cv_mouse_action_combo.addItem("🚫 None (Check Only)", CvMouseAction.NONE)
        self._cv_mouse_action_combo.currentIndexChanged.connect(self._on_cv_mouse_action_changed)
        self._cv_offset_x_spin: QSpinBox = QSpinBox()
        self._cv_offset_x_spin.setRange(-2000, 2000)
        self._cv_offset_x_spin.setSuffix(" px")
        self._cv_offset_y_spin: QSpinBox = QSpinBox()
        self._cv_offset_y_spin.setRange(-2000, 2000)
        self._cv_offset_y_spin.setSuffix(" px")

        form_layout.addRow("Template File:", self._cv_template_edit)
        form_layout.addRow("Match Algorithm:", self._cv_match_mode_combo)
        form_layout.addRow("Search Surface:", self._cv_search_area_combo)
        form_layout.addRow("Flow Policy:", self._cv_policy_combo)
        form_layout.addRow("Condition:", self._cv_comparison_combo)
        form_layout.addRow("Target Action:", self._cv_mouse_action_combo)
        form_layout.addRow("Confidence:", self._cv_confidence_spin)
        form_layout.addRow("Timeout:", self._cv_timeout_spin)
        form_layout.addRow("Offset X:", self._cv_offset_x_spin)
        form_layout.addRow("Offset Y:", self._cv_offset_y_spin)
        layout.addLayout(form_layout)
        self._stack.addWidget(self._page_cv)

    def _build_cv_multi_trigger_page(self) -> None:
        self._page_cv_multi: QWidget = QWidget(self._stack)
        layout = QVBoxLayout(self._page_cv_multi)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        info_box = QGroupBox("Multi-Target Candidate Pool", self._page_cv_multi)
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(6, 6, 6, 6)
        info_layout.setSpacing(4)

        self._cv_multi_status_label: QLabel = QLabel("0 candidate targets in block", info_box)
        self._cv_multi_status_label.setStyleSheet("color: #00E676; font-size: 11px; font-weight: bold;")
        info_layout.addWidget(self._cv_multi_status_label)

        hint_label = QLabel(
            "Tip: Select any nested Action CV below this block in the timeline to edit its specific template, coordinates, and click behavior.",
            info_box,
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #8B949E; font-size: 10px;")
        info_layout.addWidget(hint_label)

        layout.addWidget(info_box)

        test_box = QGroupBox("Pre-Execution Verification", self._page_cv_multi)
        test_layout = QVBoxLayout(test_box)
        test_layout.setContentsMargins(6, 6, 6, 6)
        test_layout.setSpacing(4)

        self._cv_multi_btn_test: QPushButton = QPushButton("🧪 Test All Candidate Matches", test_box)
        self._cv_multi_btn_test.setStyleSheet("background-color: #00897B; font-weight: bold; padding: 6px;")
        self._cv_multi_btn_test.setToolTip("Evaluate all candidate targets simultaneously against the live screen")
        self._cv_multi_btn_test.clicked.connect(self._on_test_cv_multi_clicked)
        test_layout.addWidget(self._cv_multi_btn_test)

        self._cv_multi_test_feedback: QLabel = QLabel("Ready to test candidate pool", test_box)
        self._cv_multi_test_feedback.setWordWrap(True)
        self._cv_multi_test_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cv_multi_test_feedback.setStyleSheet(
            "font-size: 10px; color: #8B949E; padding: 4px; border: 1px dashed #3E4451; border-radius: 4px;"
        )
        test_layout.addWidget(self._cv_multi_test_feedback)

        layout.addWidget(test_box)

        form_layout = QFormLayout()
        form_layout.setContentsMargins(2, 2, 2, 2)

        self._cv_multi_strategy_combo: QComboBox = QComboBox()
        self._cv_multi_strategy_combo.addItem("First Match (Priority)", CvSelectionStrategy.FIRST_MATCH)
        self._cv_multi_strategy_combo.addItem("Best Confidence Across All", CvSelectionStrategy.BEST_CONFIDENCE)

        self._cv_multi_policy_combo: QComboBox = QComboBox()
        self._cv_multi_policy_combo.addItem("if vision.match_any() ... else: pass", CvFailurePolicy.SKIP)
        self._cv_multi_policy_combo.addItem("if not vision.match_any(): break", CvFailurePolicy.BREAK_LOOP)
        self._cv_multi_policy_combo.addItem("assert vision.match_any()", CvFailurePolicy.ABORT)

        self._cv_multi_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._cv_multi_timeout_spin.setRange(0.1, 3600.0)
        self._cv_multi_timeout_spin.setSuffix(" s")

        form_layout.addRow("Selection Strategy:", self._cv_multi_strategy_combo)
        form_layout.addRow("Flow Policy:", self._cv_multi_policy_combo)
        form_layout.addRow("Timeout Limit:", self._cv_multi_timeout_spin)

        layout.addLayout(form_layout)
        self._stack.addWidget(self._page_cv_multi)

    def _on_test_cv_multi_clicked(self) -> None:
        if not isinstance(self._current_action, CvMultiTriggerAction):
            return

        strat = (
            _coerce_enum(self._cv_multi_strategy_combo.currentData(), CvSelectionStrategy)
            or CvSelectionStrategy.FIRST_MATCH
        )
        pol = (
            _coerce_enum(self._cv_multi_policy_combo.currentData(), CvFailurePolicy)
            or CvFailurePolicy.SKIP
        )

        test_action = CvMultiTriggerAction(
            id=self._current_action.id,
            description=self._current_action.description,
            enabled=self._current_action.enabled,
            timeout_seconds=self._cv_multi_timeout_spin.value(),
            strategy=strat,
            failure_policy=pol,
            branches=self._current_action.branches,
            actions=self._current_action.actions,
        )

        self._cv_multi_test_feedback.setText("Scanning display surface for candidate pool...")
        self.request_test_cv.emit(test_action)

    def display_cv_multi_test_result(
        self,
        matched_branch: CvBranchCase | None,
        result: MatchResult | None,
    ) -> None:
        """Formats and renders visual multi-match feedback in the inspector card."""
        if (
            matched_branch is not None
            and result is not None
            and result.found
            and result.center is not None
        ):
            pct = result.confidence * 100.0
            self._cv_multi_test_feedback.setStyleSheet(
                "font-size: 10px; color: #00E676; font-weight: bold; padding: 4px; "
                "border: 1px solid #00E676; border-radius: 4px; background: rgba(0, 230, 118, 0.08);"
            )
            self._cv_multi_test_feedback.setText(
                f"✓ MATCHED: '{matched_branch.name}'!\nConfidence: {pct:.1f}%\n"
                f"Center: ({result.center[0]}, {result.center[1]})"
            )
        else:
            self._cv_multi_test_feedback.setStyleSheet(
                "font-size: 10px; color: #FF5252; font-weight: bold; padding: 4px; "
                "border: 1px solid #FF5252; border-radius: 4px; background: rgba(255, 82, 82, 0.08);"
            )
            self._cv_multi_test_feedback.setText(
                "✗ NO CANDIDATES MATCHED.\n"
                "Tip: Check template visibility or lower threshold."
            )

    def _build_loop_container_page(self) -> None:
        self._page_loop: QWidget = QWidget(self._stack)
        self._loop_layout: QFormLayout = QFormLayout(self._page_loop)
        self._loop_type_combo: QComboBox = QComboBox()
        self._loop_type_combo.addItem("for _ in range(N) [Count]", LoopType.COUNT)
        self._loop_type_combo.addItem("while True [Infinite]", LoopType.INFINITE)
        self._loop_type_combo.addItem("while elapsed < T [Duration]", LoopType.DURATION)
        self._loop_type_combo.addItem("while vision.exists [Condition]", LoopType.WHILE_CV)
        self._loop_type_combo.addItem("until vision.exists [Condition]", LoopType.UNTIL_CV)
        self._loop_type_combo.currentIndexChanged.connect(self._on_loop_type_changed)
        self._loop_iterations_spin: QSpinBox = QSpinBox()
        self._loop_iterations_spin.setRange(1, 1000000)
        self._loop_duration_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_duration_spin.setRange(0.1, 86400.0)
        self._loop_duration_spin.setSuffix(" s")
        self._loop_template_edit: QLineEdit = QLineEdit()
        self._loop_confidence_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_confidence_spin.setRange(0.0, 1.0)
        self._loop_timeout_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._loop_timeout_spin.setRange(0.1, 3600.0)
        self._loop_layout.addRow("Loop Type:", self._loop_type_combo)
        self._loop_layout.addRow("Iterations:", self._loop_iterations_spin)
        self._loop_layout.addRow("Duration:", self._loop_duration_spin)
        self._loop_layout.addRow("CV Template:", self._loop_template_edit)
        self._loop_layout.addRow("Confidence:", self._loop_confidence_spin)
        self._loop_layout.addRow("Timeout:", self._loop_timeout_spin)
        self._stack.addWidget(self._page_loop)

    def _on_loop_type_changed(self) -> None:
        selected_type = _coerce_enum(self._loop_type_combo.currentData(), LoopType)
        is_count = selected_type == LoopType.COUNT
        is_duration = selected_type == LoopType.DURATION
        is_cv = selected_type in (LoopType.WHILE_CV, LoopType.UNTIL_CV)
        self._loop_layout.setRowVisible(self._loop_iterations_spin, is_count)
        self._loop_layout.setRowVisible(self._loop_duration_spin, is_duration)
        self._loop_layout.setRowVisible(self._loop_template_edit, is_cv)
        self._loop_layout.setRowVisible(self._loop_confidence_spin, is_cv)
        self._loop_layout.setRowVisible(self._loop_timeout_spin, is_cv)

    def _on_locate_crop_clicked(self) -> None:
        if isinstance(self._current_action, CvTriggerAction):
            c = self._current_action
            if (
                c.crop_x is not None
                and c.crop_y is not None
                and c.crop_width is not None
                and c.crop_height is not None
            ):
                self.request_locate_crop.emit(c.crop_x, c.crop_y, c.crop_width, c.crop_height)

    def _on_cv_mouse_action_changed(self) -> None:
        action = _coerce_enum(self._cv_mouse_action_combo.currentData(), CvMouseAction)
        has_mouse = action is not None and action != CvMouseAction.NONE
        self._cv_offset_x_spin.setEnabled(has_mouse)
        self._cv_offset_y_spin.setEnabled(has_mouse)

    def _on_test_cv_clicked(self) -> None:
        if not isinstance(self._current_action, CvTriggerAction):
            return
        pol = _coerce_enum(self._cv_policy_combo.currentData(), CvFailurePolicy) or CvFailurePolicy.ABORT
        comp = _coerce_enum(self._cv_comparison_combo.currentData(), TriggerComparison) or TriggerComparison.APPEARS
        mouse_act = _coerce_enum(self._cv_mouse_action_combo.currentData(), CvMouseAction) or CvMouseAction.CLICK
        match_mode = _coerce_enum(self._cv_match_mode_combo.currentData(), CvMatchMode) or CvMatchMode.STANDARD
        search_padding = int(self._cv_search_area_combo.currentData() or 0)
        new_template_path: str = self._cv_template_edit.text().strip()
        retained_base64: str = (
            self._current_action.image_base64
            if not new_template_path or new_template_path == self._current_action.template_path
            else ""
        )
        test_action = CvTriggerAction(
            id=self._current_action.id,
            description=self._current_action.description,
            enabled=self._current_action.enabled,
            template_path=new_template_path,
            image_base64=retained_base64,
            confidence_threshold=self._cv_confidence_spin.value(),
            timeout_seconds=self._cv_timeout_spin.value(),
            comparison=comp,
            failure_policy=pol,
            mouse_action=mouse_act,
            offset_x=self._cv_offset_x_spin.value(),
            offset_y=self._cv_offset_y_spin.value(),
            crop_x=self._current_action.crop_x,
            crop_y=self._current_action.crop_y,
            crop_width=self._current_action.crop_width,
            crop_height=self._current_action.crop_height,
            match_mode=match_mode,
            search_roi_padding=search_padding,
        )
        self._cv_test_feedback.setText("Scanning display surface...")
        self.request_test_cv.emit(test_action)

    def display_cv_test_result(self, result: MatchResult, threshold: float) -> None:
        pct = result.confidence * 100.0
        thresh_pct = threshold * 100.0
        if result.found and result.center is not None:
            self._cv_test_feedback.setStyleSheet(
                "font-size: 10px; color: #00E676; font-weight: bold; padding: 4px; "
                "border: 1px solid #00E676; border-radius: 4px; background: rgba(0, 230, 118, 0.08);"
            )
            self._cv_test_feedback.setText(
                f"✓ MATCHED! Confidence: {pct:.1f}% (Min: {thresh_pct:.1f}%)\nCenter: ({result.center[0]}, {result.center[1]})"
            )
        else:
            self._cv_test_feedback.setStyleSheet(
                "font-size: 10px; color: #FF5252; font-weight: bold; padding: 4px; "
                "border: 1px solid #FF5252; border-radius: 4px; background: rgba(255, 82, 82, 0.08);"
            )
            self._cv_test_feedback.setText(
                f"✗ NOT FOUND. Peak Confidence: {pct:.1f}% (Required: {thresh_pct:.1f}%)"
            )

    def _update_cv_preview(self, action: CvTriggerAction) -> None:
        pixmap: QPixmap | None = None
        if action.image_base64.strip():
            try:
                cleaned = action.image_base64.strip()
                if cleaned.startswith("data:") and "," in cleaned:
                    cleaned = cleaned.split(",", 1)[1].strip()
                raw_bytes = base64.b64decode(cleaned)
                qimage = QImage.fromData(raw_bytes)
                if not qimage.isNull():
                    pixmap = QPixmap.fromImage(qimage)
            except Exception:
                pixmap = None

        if pixmap is None and action.template_path.strip():
            candidate_path = Path(action.template_path.strip())
            if candidate_path.is_file():
                pix = QPixmap(str(candidate_path))
                if not pix.isNull():
                    pixmap = pix

        if pixmap is not None:
            scaled = pixmap.scaled(200, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._cv_preview_img.setPixmap(scaled)
            source_desc = "In-Memory Embedded" if action.image_base64 else "File System"
            self._cv_preview_meta.setText(f"{pixmap.width()} × {pixmap.height()} px [{source_desc}]")
        else:
            self._cv_preview_img.setText("No Preview Available")
            self._cv_preview_meta.setText("Template image not found")

        if (
            action.crop_x is not None
            and action.crop_y is not None
            and action.crop_width is not None
            and action.crop_height is not None
        ):
            self._cv_crop_meta.setText(
                f"Original Crop: ({action.crop_x}, {action.crop_y}) [{action.crop_width}×{action.crop_height} px]"
            )
            self._cv_btn_locate_crop.setEnabled(True)
        else:
            self._cv_crop_meta.setText("Original Crop: Location not recorded")
            self._cv_btn_locate_crop.setEnabled(False)

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
            case SetVariableAction() as s:
                self._var_name_edit.setText(s.name)
                idx = self._var_op_combo.findData(s.operation)
                if idx >= 0:
                    self._var_op_combo.setCurrentIndex(idx)
                self._var_expr_edit.setText(s.expression)
                self._stack.setCurrentWidget(self._page_set_var)

            case IfElseContainerAction() as i:
                self._if_condition_edit.setText(i.condition)
                self._stack.setCurrentWidget(self._page_if_else)

            case FlowControlAction() as f:
                idx = self._flow_signal_combo.findData(f.signal)
                if idx >= 0:
                    self._flow_signal_combo.setCurrentIndex(idx)
                self._flow_reason_edit.setText(f.reason)
                self._flow_reason_edit.setEnabled(f.signal == FlowSignal.ABORT)
                self._stack.setCurrentWidget(self._page_flow_ctrl)

            case MouseMoveAction() as m:
                self._move_x_spin.setValue(m.x)
                self._move_y_spin.setValue(m.y)
                self._move_duration_spin.setValue(m.duration_ms)
                self._move_relative_check.setChecked(m.is_relative)
                self._stack.setCurrentWidget(self._page_move)

            case MouseButtonAction() as b:
                btn_idx = self._btn_button_combo.findData(b.button)
                if btn_idx >= 0:
                    self._btn_button_combo.setCurrentIndex(btn_idx)
                state_idx = self._btn_state_combo.findData(b.state)
                if state_idx >= 0:
                    self._btn_state_combo.setCurrentIndex(state_idx)
                has_coords = b.x is not None and b.y is not None
                self._btn_use_coords_check.setChecked(has_coords)
                self._btn_x_spin.setEnabled(has_coords)
                self._btn_y_spin.setEnabled(has_coords)
                self._btn_pick_btn.setEnabled(has_coords)
                self._btn_x_spin.setValue(b.x if b.x is not None else 0)
                self._btn_y_spin.setValue(b.y if b.y is not None else 0)
                self._stack.setCurrentWidget(self._page_button)

            case MouseScrollAction() as s:
                self._scroll_delta_spin.setValue(s.delta)
                self._scroll_horizontal_check.setChecked(s.horizontal)
                self._stack.setCurrentWidget(self._page_scroll)

            case KeyboardKeyAction() as k:
                self._key_vk_spin.setValue(k.vk_code)
                key_state_idx = self._key_state_combo.findData(k.state)
                if key_state_idx >= 0:
                    self._key_state_combo.setCurrentIndex(key_state_idx)
                self._key_name_edit.setText(k.key_name)
                self._stack.setCurrentWidget(self._page_key)

            case DelayAction() as d:
                self._delay_duration_spin.setValue(d.duration_ms)
                self._delay_jitter_spin.setValue(d.jitter_ms)
                self._stack.setCurrentWidget(self._page_delay)

            case CvTriggerAction() as c:
                self._cv_template_edit.setText(c.template_path)
                self._cv_confidence_spin.setValue(c.confidence_threshold)
                self._cv_timeout_spin.setValue(c.timeout_seconds)
                for i in range(self._cv_match_mode_combo.count()):
                    if self._cv_match_mode_combo.itemData(i) == c.match_mode:
                        self._cv_match_mode_combo.setCurrentIndex(i)
                        break
                for i in range(self._cv_policy_combo.count()):
                    if self._cv_policy_combo.itemData(i) == c.failure_policy:
                        self._cv_policy_combo.setCurrentIndex(i)
                        break
                for i in range(self._cv_comparison_combo.count()):
                    if self._cv_comparison_combo.itemData(i) == c.comparison:
                        self._cv_comparison_combo.setCurrentIndex(i)
                        break
                for i in range(self._cv_mouse_action_combo.count()):
                    if self._cv_mouse_action_combo.itemData(i) == c.mouse_action:
                        self._cv_mouse_action_combo.setCurrentIndex(i)
                        break
                self._cv_offset_x_spin.setValue(c.offset_x)
                self._cv_offset_y_spin.setValue(c.offset_y)
                self._on_cv_mouse_action_changed()
                self._update_cv_preview(c)
                self._stack.setCurrentWidget(self._page_cv)

            case CvMultiTriggerAction() as m:
                self._cv_multi_timeout_spin.setValue(m.timeout_seconds)
                for i in range(self._cv_multi_strategy_combo.count()):
                    if self._cv_multi_strategy_combo.itemData(i) == m.strategy:
                        self._cv_multi_strategy_combo.setCurrentIndex(i)
                        break
                for i in range(self._cv_multi_policy_combo.count()):
                    if self._cv_multi_policy_combo.itemData(i) == m.failure_policy:
                        self._cv_multi_policy_combo.setCurrentIndex(i)
                        break
                count = len(m.actions) if m.actions else len(m.branches)
                self._cv_multi_status_label.setText(f"{count} candidate targets in block")
                self._cv_multi_test_feedback.setStyleSheet(
                    "font-size: 10px; color: #8B949E; padding: 4px; border: 1px dashed #3E4451; border-radius: 4px;"
                )
                self._cv_multi_test_feedback.setText("Ready to test candidate pool")
                self._stack.setCurrentWidget(self._page_cv_multi)

            case LoopContainerAction() as lp:
                for i in range(self._loop_type_combo.count()):
                    if self._loop_type_combo.itemData(i) == lp.loop_type:
                        self._loop_type_combo.setCurrentIndex(i)
                        break
                self._loop_iterations_spin.setValue(lp.iterations)
                self._loop_duration_spin.setValue(lp.duration_seconds)
                self._loop_template_edit.setText(lp.template_path)
                self._loop_confidence_spin.setValue(lp.confidence_threshold)
                self._loop_timeout_spin.setValue(lp.timeout_seconds)
                self._on_loop_type_changed()
                self._stack.setCurrentWidget(self._page_loop)

            case MiniGameSolverAction() as g:
                idx = self._solver_slot_combo.findData(g.player_slot)
                if idx >= 0:
                    self._solver_slot_combo.setCurrentIndex(idx)
                self._solver_name_edit.setText(g.player_name)
                self._solver_autoclick_check.setChecked(g.auto_click)
                self._solver_timeout_spin.setValue(g.timeout_seconds)
                self._stack.setCurrentWidget(self._page_solver)

    def set_target_coordinates(self, x: int, y: int) -> None:
        if self._current_action is None:
            return
        if isinstance(self._current_action, MouseMoveAction):
            self._move_x_spin.setValue(x)
            self._move_y_spin.setValue(y)
            self._on_save_clicked()
        elif isinstance(self._current_action, MouseButtonAction):
            self._btn_use_coords_check.setChecked(True)
            self._btn_x_spin.setValue(x)
            self._btn_y_spin.setValue(y)
            self._on_save_clicked()

    def _on_save_clicked(self) -> None:
        if self._current_action is None or self._current_row < 0:
            return

        updated: ActionNode | None = None
        match self._current_action:
            case SetVariableAction() as s:
                op = _coerce_enum(self._var_op_combo.currentData(), VariableOp) or VariableOp.ASSIGN
                name_str = self._var_name_edit.text().strip() or "var"
                updated = SetVariableAction(
                    id=s.id,
                    description=s.description,
                    enabled=s.enabled,
                    name=name_str,
                    operation=op,
                    expression=self._var_expr_edit.text().strip() or "0",
                )
            case IfElseContainerAction() as i:
                updated = IfElseContainerAction(
                    id=i.id,
                    description=i.description,
                    enabled=i.enabled,
                    condition=self._if_condition_edit.text().strip() or "True",
                    then_actions=i.then_actions,
                    else_actions=i.else_actions,
                )
            case FlowControlAction() as f:
                sig = _coerce_enum(self._flow_signal_combo.currentData(), FlowSignal) or FlowSignal.BREAK
                updated = FlowControlAction(
                    id=f.id,
                    description=f.description,
                    enabled=f.enabled,
                    signal=sig,
                    reason=self._flow_reason_edit.text().strip(),
                )
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
                btn_item = _coerce_enum(self._btn_button_combo.currentData(), MouseButton)
                state_item = _coerce_enum(self._btn_state_combo.currentData(), ButtonState)
                if btn_item is not None and state_item is not None:
                    use_coords = self._btn_use_coords_check.isChecked()
                    updated = MouseButtonAction(
                        id=b.id,
                        description=b.description,
                        enabled=b.enabled,
                        button=btn_item,
                        state=state_item,
                        x=self._btn_x_spin.value() if use_coords else None,
                        y=self._btn_y_spin.value() if use_coords else None,
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
                kstate_item = _coerce_enum(self._key_state_combo.currentData(), KeyState)
                if kstate_item is not None:
                    new_vk: int = self._key_vk_spin.value()
                    new_scan: int = k.scan_code if new_vk == k.vk_code else 0
                    updated = KeyboardKeyAction(
                        id=k.id,
                        description=k.description,
                        enabled=k.enabled,
                        vk_code=new_vk,
                        scan_code=new_scan,
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
                pol = _coerce_enum(self._cv_policy_combo.currentData(), CvFailurePolicy) or CvFailurePolicy.ABORT
                comp = _coerce_enum(self._cv_comparison_combo.currentData(), TriggerComparison) or TriggerComparison.APPEARS
                mouse_act = _coerce_enum(self._cv_mouse_action_combo.currentData(), CvMouseAction) or CvMouseAction.CLICK
                match_mode = _coerce_enum(self._cv_match_mode_combo.currentData(), CvMatchMode) or CvMatchMode.STANDARD
                search_padding = int(self._cv_search_area_combo.currentData() or 0)
                new_template_path: str = self._cv_template_edit.text().strip()
                retained_base64: str = (
                    c.image_base64
                    if not new_template_path or new_template_path == c.template_path
                    else ""
                )
                updated = CvTriggerAction(
                    id=c.id,
                    description=c.description,
                    enabled=c.enabled,
                    template_path=new_template_path,
                    image_base64=retained_base64,
                    confidence_threshold=self._cv_confidence_spin.value(),
                    timeout_seconds=self._cv_timeout_spin.value(),
                    comparison=comp,
                    failure_policy=pol,
                    mouse_action=mouse_act,
                    offset_x=self._cv_offset_x_spin.value(),
                    offset_y=self._cv_offset_y_spin.value(),
                    crop_x=c.crop_x,
                    crop_y=c.crop_y,
                    crop_width=c.crop_width,
                    crop_height=c.crop_height,
                    match_mode=match_mode,
                    search_roi_padding=search_padding,
                )
            case CvMultiTriggerAction() as m:
                strat = _coerce_enum(self._cv_multi_strategy_combo.currentData(), CvSelectionStrategy) or CvSelectionStrategy.FIRST_MATCH
                pol = _coerce_enum(self._cv_multi_policy_combo.currentData(), CvFailurePolicy) or CvFailurePolicy.SKIP
                updated = CvMultiTriggerAction(
                    id=m.id,
                    description=m.description,
                    enabled=m.enabled,
                    timeout_seconds=self._cv_multi_timeout_spin.value(),
                    strategy=strat,
                    failure_policy=pol,
                    branches=m.branches,
                    actions=m.actions,
                )
            case LoopContainerAction() as lp:
                selected_type = _coerce_enum(self._loop_type_combo.currentData(), LoopType)
                if selected_type is not None:
                    updated = LoopContainerAction(
                        id=lp.id,
                        description=lp.description,
                        enabled=lp.enabled,
                        loop_type=selected_type,
                        iterations=self._loop_iterations_spin.value(),
                        duration_seconds=self._loop_duration_spin.value(),
                        template_path=self._loop_template_edit.text().strip(),
                        image_base64=lp.image_base64,
                        confidence_threshold=self._loop_confidence_spin.value(),
                        timeout_seconds=self._loop_timeout_spin.value(),
                        actions=lp.actions,
                    )
            case MiniGameSolverAction() as g:
                slot = _coerce_enum(self._solver_slot_combo.currentData(), RabbitSlot) or RabbitSlot.AUTO
                updated = MiniGameSolverAction(
                    id=g.id,
                    description=g.description,
                    enabled=g.enabled,
                    player_slot=slot,
                    player_name=self._solver_name_edit.text().strip() or "DADI_",
                    auto_click=self._solver_autoclick_check.isChecked(),
                    timeout_seconds=self._solver_timeout_spin.value(),
                )

        if updated is not None:
            self._current_action = updated
            self.action_updated.emit(self._current_row, updated)