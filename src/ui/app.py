from __future__ import annotations

import sys
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from src.engine.orchestrator import MacroOrchestrator
from src.ui.bridge import UIBridge
from src.ui.models.action_model import ActionSequenceModel
from src.ui.views.main_window import MainWindow

__all__: Final[list[str]] = ["run_app"]


def _apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette: QPalette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 36))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 22, 26))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(36, 36, 42))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(42, 42, 48))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 150, 100))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)


def run_app() -> int:
    """Initializes the Qt application runtime, orchestration core, and primary view."""
    app: QApplication = QApplication(sys.argv)
    _apply_dark_theme(app)

    orchestrator: MacroOrchestrator = MacroOrchestrator()
    orchestrator.initialize()

    model: ActionSequenceModel = ActionSequenceModel()
    bridge: UIBridge = UIBridge(orchestrator=orchestrator)
    main_window: MainWindow = MainWindow(bridge=bridge, model=model)
    main_window.show()

    exit_code: int = app.exec()
    orchestrator.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(run_app())