# pyright: reportUntypedBaseClass=false
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import QObject, Signal

__all__: Final[list[str]] = ["PlaybackTelemetry", "TelemetryModel"]


@dataclass(frozen=True, slots=True)
class PlaybackTelemetry:
    """Snapshot of active execution metrics."""

    is_playing: bool = False
    is_recording: bool = False
    current_step: int = 0
    total_steps: int = 0
    iteration: int = 0
    total_iterations: int = 0
    elapsed_seconds: float = 0.0
    status_message: str = "Ready"


class TelemetryModel(QObject):
    """Observable Qt model managing execution telemetry."""

    telemetry_changed: Signal = Signal(PlaybackTelemetry)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current: PlaybackTelemetry = PlaybackTelemetry()

    @property
    def telemetry(self) -> PlaybackTelemetry:
        return self._current

    def update(self, telemetry: PlaybackTelemetry) -> None:
        self._current = telemetry
        self.telemetry_changed.emit(self._current)

    def reset(self) -> None:
        self.update(PlaybackTelemetry())