# pyright: reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false
from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.ast import (
    CvTriggerAction,
    DelayAction,
    KeyboardKeyAction,
    LoopContainerAction,
    MouseButtonAction,
    MouseMoveAction,
    MouseScrollAction,
)
from src.core.enums import (
    CvFailurePolicy,
    CvMouseAction,
    TriggerComparison,
)
from src.core.logging_config import get_qt_log_bridge
from src.core.serialization import MacroSerializer
from src.core.types import Point2D, Rect2D
from src.ui.bridge import UIBridge
from src.ui.models.action_model import ActionSequenceModel
from src.ui.models.telemetry_model import PlaybackTelemetry
from src.ui.views.coordinate_picker import CoordinatePickerOverlay
from src.ui.views.inspector_view import ActionInspectorView
from src.ui.views.roi_selector import RoiSelectorOverlay
from src.ui.views.timeline_view import TimelineView

__all__: Final[list[str]] = ["MainWindow"]


class MainWindow(QMainWindow):
    """Primary application workstation interface with integrated live operation logging console."""

    def __init__(
        self,
        bridge: UIBridge,
        model: ActionSequenceModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge: UIBridge = bridge
        self._model: ActionSequenceModel = model
        self._current_file_path: str | None = None

        self.setWindowTitle("Untitled Sequence - Desktop Automation Suite")
        self.resize(1200, 850)

        # Central Splitter Layout
        splitter: QSplitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._timeline: TimelineView = TimelineView(self._model, splitter)
        self._inspector: ActionInspectorView = ActionInspectorView(splitter)

        splitter.addWidget(self._timeline)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        self.setCentralWidget(splitter)

        # Screen Overlays (ROI Cropper & Coordinate Crosshair Dropper)
        self._roi_selector: RoiSelectorOverlay = RoiSelectorOverlay()
        self._roi_selector.roi_selected.connect(self._on_roi_captured)

        self._coord_picker: CoordinatePickerOverlay = CoordinatePickerOverlay()
        self._coord_picker.coordinate_selected.connect(self._on_coordinate_captured)

        # Status Bar
        self._status_bar: QStatusBar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Engine initialized. Emergency Kill-Switch active (F12).")

        self._build_toolbars()
        self._build_log_console_dock()
        self._wire_signals()

        # Connect global logging bridge to the live UI console
        get_qt_log_bridge().log_emitted.connect(self._append_log_entry)

    def _build_toolbars(self) -> None:
        toolbar: QToolBar = QToolBar("Main Controls", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # File actions
        self._act_new: QAction = QAction("New", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.setToolTip("Create new sequence (Ctrl+N)")
        self._act_new.triggered.connect(self._on_new)
        toolbar.addAction(self._act_new)

        self._act_open: QAction = QAction("Open", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.setToolTip("Open macro file (Ctrl+O)")
        self._act_open.triggered.connect(self._on_open)
        toolbar.addAction(self._act_open)

        self._act_save: QAction = QAction("Save", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.setToolTip("Save macro sequence (Ctrl+S)")
        self._act_save.triggered.connect(self._on_save)
        toolbar.addAction(self._act_save)

        self._act_save_as: QAction = QAction("Save As...", self)
        self._act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._act_save_as.setToolTip("Save macro sequence under new file path (Ctrl+Shift+S)")
        self._act_save_as.triggered.connect(self._on_save_as)
        toolbar.addAction(self._act_save_as)

        toolbar.addSeparator()

        # Engine Transport controls
        self._act_record: QAction = QAction("● Record (Ctrl+R)", self)
        self._act_record.setShortcut(QKeySequence("Ctrl+R"))
        self._act_record.setToolTip("Toggle hardware event recording (Ctrl+R)")
        self._act_record.triggered.connect(self._on_toggle_record)
        toolbar.addAction(self._act_record)

        self._act_play: QAction = QAction("▶ Play (F5)", self)
        self._act_play.setShortcut(QKeySequence("F5"))
        self._act_play.setToolTip("Execute active macro sequence (F5)")
        self._act_play.triggered.connect(self._on_play)
        toolbar.addAction(self._act_play)

        self._act_stop: QAction = QAction("⏹ Stop (F6)", self)
        self._act_stop.setShortcut(QKeySequence("F6"))
        self._act_stop.setToolTip("Abort active playback or recording (F6)")
        self._act_stop.triggered.connect(self._bridge.abort)
        toolbar.addAction(self._act_stop)

        toolbar.addSeparator()

        # Global Hotkey for CV Template capture (Ctrl+G, F7)
        self._act_capture_roi: QAction = QAction("Grab CV Template", self)
        self._act_capture_roi.setShortcuts([QKeySequence("Ctrl+G"), QKeySequence("F7")])
        self._act_capture_roi.setToolTip("Capture Region of Interest for visual template gate (Ctrl+G / F7)")
        self._act_capture_roi.triggered.connect(self._roi_selector.start_selection)
        toolbar.addAction(self._act_capture_roi)
        self.addAction(self._act_capture_roi)

        # Global Hotkey for Coordinate Drag/Pick (Ctrl+Shift+C, F8)
        self._act_pick_coord: QAction = QAction("Pick Coordinate", self)
        self._act_pick_coord.setShortcuts([QKeySequence("Ctrl+Shift+C"), QKeySequence("F8")])
        self._act_pick_coord.setToolTip("Drag or click crosshair to set action coordinates (Ctrl+Shift+C / F8)")
        self._act_pick_coord.triggered.connect(self._coord_picker.start_selection)
        toolbar.addAction(self._act_pick_coord)
        self.addAction(self._act_pick_coord)

        toolbar.addSeparator()

        # Log Console Visibility Toggle
        self._act_toggle_logs: QAction = QAction("📋 Operation Logs", self)
        self._act_toggle_logs.setCheckable(True)
        self._act_toggle_logs.setChecked(True)
        self._act_toggle_logs.setToolTip("Toggle Operation Log Console (Ctrl+L)")
        self._act_toggle_logs.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self._act_toggle_logs.toggled.connect(self._on_toggle_log_dock)
        toolbar.addAction(self._act_toggle_logs)

    def _build_log_console_dock(self) -> None:
        self._log_dock: QDockWidget = QDockWidget("Operation Logs & Diagnostics", self)
        self._log_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)

        dock_contents: QWidget = QWidget(self._log_dock)
        layout: QVBoxLayout = QVBoxLayout(dock_contents)
        layout.setContentsMargins(4, 4, 4, 4)

        # Control Bar
        ctrl_bar: QHBoxLayout = QHBoxLayout()
        self._chk_autoscroll: QCheckBox = QCheckBox("Auto-scroll", dock_contents)
        self._chk_autoscroll.setChecked(True)
        ctrl_bar.addWidget(self._chk_autoscroll)

        btn_clear_logs: QPushButton = QPushButton("Clear", dock_contents)
        btn_clear_logs.setFixedWidth(60)
        btn_clear_logs.clicked.connect(self._on_clear_logs)
        ctrl_bar.addWidget(btn_clear_logs)

        ctrl_bar.addStretch()
        layout.addLayout(ctrl_bar)

        # Log Output Text Area
        self._txt_log_output: QPlainTextEdit = QPlainTextEdit(dock_contents)
        self._txt_log_output.setReadOnly(True)
        self._txt_log_output.setMaximumBlockCount(2000)
        mono_font = QFont("Consolas", 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self._txt_log_output.setFont(mono_font)
        self._txt_log_output.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #111418;"
            "  color: #D4D4D4;"
            "  border: 1px solid #282C34;"
            "}"
        )
        layout.addWidget(self._txt_log_output)

        self._log_dock.setWidget(dock_contents)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)

    def _on_toggle_log_dock(self, visible: bool) -> None:
        self._log_dock.setVisible(visible)

    def _on_clear_logs(self) -> None:
        self._txt_log_output.clear()

    @Slot(str, str, str)
    def _append_log_entry(self, level: str, timestamp: str, message: str) -> None:
        """Appends color-coded log lines into the live console."""
        color_map: dict[str, str] = {
            "DEBUG": "#7F848E",
            "INFO": "#98C379",
            "WARNING": "#E5C07B",
            "ERROR": "#E06C75",
            "CRITICAL": "#FF3333",
        }
        color: str = color_map.get(level, "#D4D4D4")
        html_line: str = (
            f'<span style="color:#5C6370;">{timestamp}</span> '
            f'<b style="color:{color};">[{level:<5}]</b> '
            f'<span style="color:#ABB2BF;">{message}</span>'
        )
        self._txt_log_output.appendHtml(html_line)

        if self._chk_autoscroll.isChecked():
            cursor = self._txt_log_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._txt_log_output.setTextCursor(cursor)

    def _wire_signals(self) -> None:
        self._timeline.action_selected.connect(self._on_action_selected)
        self._timeline.status_message_requested.connect(self._status_bar.showMessage)

        self._inspector.action_updated.connect(self._on_action_updated)
        self._inspector.action_created.connect(self._on_action_created)
        self._inspector.request_cv_capture.connect(self._roi_selector.start_selection)
        self._inspector.request_coordinate_pick.connect(self._coord_picker.start_selection)

        self._bridge.recording_state_changed.connect(self._on_recording_changed)
        self._bridge.playback_state_changed.connect(self._on_playback_changed)
        self._bridge.telemetry_updated.connect(self._on_telemetry_updated)
        self._bridge.error_occurred.connect(self._on_error)

    @Slot(int, object)
    def _on_action_updated(self, row: int, updated: object) -> None:
        if isinstance(
            updated,
            (
                MouseMoveAction,
                MouseButtonAction,
                MouseScrollAction,
                KeyboardKeyAction,
                DelayAction,
                CvTriggerAction,
                LoopContainerAction,
            ),
        ):
            if self._model.update_action(row, updated):
                new_row = self._model.find_row_by_id(updated.id)
                if new_row >= 0:
                    self._timeline.select_row(new_row)
                    self._inspector.inspect(new_row, updated)
                self._status_bar.showMessage(
                    f"Updated action #{new_row + 1 if new_row >= 0 else row + 1} ({updated.action_type.value})."
                )

    @Slot(int)
    def _on_action_selected(self, row: int) -> None:
        action = self._model.get_action(row) if row >= 0 else None
        self._inspector.inspect(row, action)

    @Slot(object)
    def _on_action_created(self, action: object) -> None:
        if isinstance(
            action,
            (
                MouseMoveAction,
                MouseButtonAction,
                MouseScrollAction,
                KeyboardKeyAction,
                DelayAction,
                CvTriggerAction,
                LoopContainerAction,
            ),
        ):
            selected_rows = self._timeline.selected_rows()
            target_row = selected_rows[-1] if selected_rows else None
            new_row = self._model.insert_action(action, target_row=target_row)
            self._timeline.select_rows([new_row])
            self._inspector.inspect(new_row, action)
            self._status_bar.showMessage(f"Added {action.action_type.value} to sequence.")

    @Slot()
    def _on_new(self) -> None:
        self._model.clear()
        self._current_file_path = None
        self._timeline.clear_selection()
        self._inspector.inspect(-1, None)
        self._inspector.set_active_tab(1)
        self.setWindowTitle("Untitled Sequence - Desktop Automation Suite")
        self._status_bar.showMessage("New sequence created.")

    @Slot()
    def _on_open(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Macro Sequence", "", "JSON Files (*.json);;YAML Files (*.yaml *.yml);;All Files (*.*)"
        )
        if file_path:
            try:
                seq = MacroSerializer.load_from_file(file_path)
                self._model.set_sequence(seq)
                self._current_file_path = file_path
                self.setWindowTitle(f"{Path(file_path).name} - Desktop Automation Suite")
                self._status_bar.showMessage(f"Loaded: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load file: {e}")

    @Slot()
    def _on_save(self) -> None:
        if self._current_file_path:
            try:
                seq = self._model.to_macro_sequence()
                MacroSerializer.save_to_file(seq, self._current_file_path)
                self.setWindowTitle(f"{Path(self._current_file_path).name} - Desktop Automation Suite")
                self._status_bar.showMessage(f"Saved: {Path(self._current_file_path).name}")
                return
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")
                return
        self._on_save_as()

    @Slot()
    def _on_save_as(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Macro Sequence", "", "JSON Files (*.json);;YAML Files (*.yaml);;All Files (*.*)"
        )
        if file_path:
            try:
                seq = self._model.to_macro_sequence()
                MacroSerializer.save_to_file(seq, file_path)
                self._current_file_path = file_path
                self.setWindowTitle(f"{Path(file_path).name} - Desktop Automation Suite")
                self._status_bar.showMessage(f"Saved: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")

    @Slot()
    def _on_toggle_record(self) -> None:
        if self._bridge.is_recording:
            seq = self._bridge.stop_recording()
            if seq is not None:
                self._model.set_sequence(seq)
        else:
            self._bridge.start_recording()

    @Slot()
    def _on_play(self) -> None:
        seq = self._model.to_macro_sequence()
        if not seq.actions:
            self._status_bar.showMessage("Sequence is empty.")
            return
        self._bridge.start_playback(seq, repeat_count=1)

    @Slot(bool)
    def _on_recording_changed(self, active: bool) -> None:
        self._act_record.setText("⏹ Stop Recording (Ctrl+R)" if active else "● Record (Ctrl+R)")
        self._act_play.setEnabled(not active)
        self._status_bar.showMessage("● Recording inputs..." if active else "Recording finished.")

    @Slot(bool)
    def _on_playback_changed(self, active: bool) -> None:
        self._act_play.setEnabled(not active)
        self._act_record.setEnabled(not active)
        self._status_bar.showMessage("▶ Playing macro sequence..." if active else "Playback finished.")

    @Slot(PlaybackTelemetry)
    def _on_telemetry_updated(self, t: PlaybackTelemetry) -> None:
        if t.is_playing:
            self._status_bar.showMessage(
                f"Playing: Step {t.current_step}/{t.total_steps} (Iter {t.iteration}) | {t.elapsed_seconds:.1f}s"
            )

    @Slot(str)
    def _on_error(self, error: str) -> None:
        if "aborted" in error.lower() or "cancelled" in error.lower():
            self._status_bar.showMessage(f"Playback stopped: {error}")
            return
        QMessageBox.warning(self, "Execution Alert", error)
        self._status_bar.showMessage(f"Error: {error}")

    @Slot(Rect2D)
    def _on_roi_captured(self, roi: Rect2D) -> None:
        try:
            b64_str: str = self._bridge.capture_template_base64(roi)
            trigger_action = CvTriggerAction(
                image_base64=b64_str,
                confidence_threshold=0.8,
                timeout_seconds=10.0,
                comparison=TriggerComparison.APPEARS,
                failure_policy=CvFailurePolicy.ABORT,
                mouse_action=CvMouseAction.CLICK,  # Default to moving and clicking target center
                offset_x=0,
                offset_y=0,
            )
            selected_rows = self._timeline.selected_rows()
            target_row = selected_rows[-1] if selected_rows else None
            new_row = self._model.insert_action(trigger_action, target_row=target_row)
            self._timeline.select_rows([new_row])
            self._inspector.inspect(new_row, trigger_action)
            self._status_bar.showMessage(
                f"Visual click gate created ({roi.width}x{roi.height} px) targeting match center."
            )
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"Failed to grab template: {e}")

    @Slot(Point2D)
    def _on_coordinate_captured(self, point: Point2D) -> None:
        self._inspector.set_target_coordinates(point.x, point.y)
        self._status_bar.showMessage(f"Target coordinates set to ({point.x}, {point.y}).")