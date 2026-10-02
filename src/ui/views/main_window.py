# pyright: reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false
from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
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
    """Primary application workstation interface with clean transport and authoring split."""

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
        self.resize(1180, 750)

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
        self._wire_signals()

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

        # Global Hotkey for CV Template capture (Ctrl+G, F7)
        self._act_capture_roi: QAction = QAction("Grab CV Template", self)
        self._act_capture_roi.setShortcuts([QKeySequence("Ctrl+G"), QKeySequence("F7")])
        self._act_capture_roi.setToolTip("Capture Region of Interest for visual template gate (Ctrl+G / F7)")
        self._act_capture_roi.triggered.connect(self._roi_selector.start_selection)
        self.addAction(self._act_capture_roi)

        # Global Hotkey for Coordinate Drag/Pick (Ctrl+Shift+C, F8)
        self._act_pick_coord: QAction = QAction("Pick Desktop Coordinate", self)
        self._act_pick_coord.setShortcuts([QKeySequence("Ctrl+Shift+C"), QKeySequence("F8")])
        self._act_pick_coord.setToolTip("Drag or click crosshair to set action coordinates (Ctrl+Shift+C / F8)")
        self._act_pick_coord.triggered.connect(self._coord_picker.start_selection)
        self.addAction(self._act_pick_coord)

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
            self._model.append_action(action)
            new_row = self._model.rowCount() - 1
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
        self._status_bar.showMessage("New sequence created. Add actions from the Library on the right.")

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
            )
            self._model.append_action(trigger_action)
            new_row = self._model.rowCount() - 1
            self._timeline.select_rows([new_row])
            self._inspector.inspect(new_row, trigger_action)
            self._status_bar.showMessage(
                f"Visual gate added ({roi.width}x{roi.height} px)."
            )
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"Failed to grab template: {e}")

    @Slot(Point2D)
    def _on_coordinate_captured(self, point: Point2D) -> None:
        self._inspector.set_target_coordinates(point.x, point.y)
        self._status_bar.showMessage(f"Target coordinates set to ({point.x}, {point.y}).")