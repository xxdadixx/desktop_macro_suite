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

from src.core.ast import CvTriggerAction
from src.core.serialization import MacroSerializer
from src.core.types import Rect2D
from src.ui.bridge import UIBridge
from src.ui.models.action_model import ActionSequenceModel
from src.ui.models.telemetry_model import PlaybackTelemetry
from src.ui.views.inspector_view import ActionInspectorView
from src.ui.views.roi_selector import RoiSelectorOverlay
from src.ui.views.timeline_view import TimelineView

__all__: Final[list[str]] = ["MainWindow"]


class MainWindow(QMainWindow):
    """Primary application workstation interface."""

    def __init__(
        self,
        bridge: UIBridge,
        model: ActionSequenceModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge: UIBridge = bridge
        self._model: ActionSequenceModel = model

        self.setWindowTitle("Desktop Automation Suite")
        self.resize(1100, 720)

        # Central Splitter Layout
        splitter: QSplitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._timeline: TimelineView = TimelineView(self._model, splitter)
        self._inspector: ActionInspectorView = ActionInspectorView(splitter)

        splitter.addWidget(self._timeline)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)

        # ROI Selector Tool Overlay
        self._roi_selector: RoiSelectorOverlay = RoiSelectorOverlay()
        self._roi_selector.roi_selected.connect(self._on_roi_captured)

        # Status Bar
        self._status_bar: QStatusBar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Engine initialized. Emergency Kill-Switch active (ESC).")

        self._build_toolbars()
        self._wire_signals()

    def _build_toolbars(self) -> None:
        toolbar: QToolBar = QToolBar("Main Controls", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # File actions
        self._act_new: QAction = QAction("New", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._on_new)
        toolbar.addAction(self._act_new)

        self._act_open: QAction = QAction("Open", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._on_open)
        toolbar.addAction(self._act_open)

        self._act_save: QAction = QAction("Save", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._on_save)
        toolbar.addAction(self._act_save)

        toolbar.addSeparator()

        # Engine controls
        self._act_record: QAction = QAction("Record (Ctrl+R)", self)
        self._act_record.setShortcut(QKeySequence("Ctrl+R"))
        self._act_record.triggered.connect(self._on_toggle_record)
        toolbar.addAction(self._act_record)

        self._act_play: QAction = QAction("Play (F5)", self)
        self._act_play.setShortcut(QKeySequence("F5"))
        self._act_play.triggered.connect(self._on_play)
        toolbar.addAction(self._act_play)

        self._act_stop: QAction = QAction("Stop/Abort (F6)", self)
        self._act_stop.setShortcut(QKeySequence("F6"))
        self._act_stop.triggered.connect(self._bridge.abort)
        toolbar.addAction(self._act_stop)

        toolbar.addSeparator()

        # CV Selector tool
        self._act_capture_roi: QAction = QAction("Grab CV Template", self)
        self._act_capture_roi.triggered.connect(self._roi_selector.start_selection)
        toolbar.addAction(self._act_capture_roi)

    def _wire_signals(self) -> None:
        self._timeline.action_selected.connect(self._on_action_selected)
        self._inspector.action_updated.connect(self._model.update_action)

        self._bridge.recording_state_changed.connect(self._on_recording_changed)
        self._bridge.playback_state_changed.connect(self._on_playback_changed)
        self._bridge.telemetry_updated.connect(self._on_telemetry_updated)
        self._bridge.error_occurred.connect(self._on_error)

    @Slot(int)
    def _on_action_selected(self, row: int) -> None:
        self._inspector.inspect(row, self._model.get_action(row))

    @Slot()
    def _on_new(self) -> None:
        self._model.clear()
        self._status_bar.showMessage("New sequence created.")

    @Slot()
    def _on_open(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Macro Sequence", "", "JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            try:
                seq = MacroSerializer.load_from_file(file_path)
                self._model.set_sequence(seq)
                self._status_bar.showMessage(f"Loaded: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load file: {e}")

    @Slot()
    def _on_save(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Macro Sequence", "", "JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            try:
                seq = self._model.to_macro_sequence()
                MacroSerializer.save_to_file(seq, file_path)
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
        self._act_record.setText("Stop Recording" if active else "Record (Ctrl+R)")
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
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Template Image", "template.png", "PNG Images (*.png)"
        )
        if file_path:
            try:
                self._bridge.save_template(roi, file_path)
                trigger_action = CvTriggerAction(
                    template_path=file_path,
                    confidence_threshold=0.8,
                    timeout_seconds=10.0,
                )
                self._model.append_action(trigger_action)
                self._status_bar.showMessage(f"Saved template and added visual gate: {Path(file_path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Template Error", f"Failed to grab template: {e}")