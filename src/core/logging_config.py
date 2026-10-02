from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final, override

from PySide6.QtCore import QObject, Signal

__all__: Final[list[str]] = [
    "LOG_FORMAT",
    "QtLogBridge",
    "get_qt_log_bridge",
    "setup_logging",
]

LOG_FORMAT: Final[str] = (
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s"
)
LOG_DATE_FORMAT: Final[str] = "%H:%M:%S"


class QtLogBridge(QObject):
    """Thread-safe Qt signal emitter dispatching Python logging records to UI widgets."""

    log_emitted: Signal = Signal(str, str, str)  # (level, timestamp, message)


class _QtLogHandler(logging.Handler):
    """Logging handler redirecting records through the Qt signal event queue."""

    def __init__(self, bridge: QtLogBridge) -> None:
        super().__init__()
        self._bridge: QtLogBridge = bridge

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg: str = self.format(record)
            time_str: str = self.formatter.formatTime(record, LOG_DATE_FORMAT) if self.formatter else ""
            self._bridge.log_emitted.emit(record.levelname, time_str, msg)
        except Exception:
            self.handleError(record)


_GLOBAL_QT_LOG_BRIDGE: QtLogBridge = QtLogBridge()


def get_qt_log_bridge() -> QtLogBridge:
    """Returns the global Qt log bridge instance for UI subscription."""
    return _GLOBAL_QT_LOG_BRIDGE


def setup_logging(
    log_level: int = logging.INFO,
    log_file_path: Path | str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> QtLogBridge:
    """Configures root logging with console output, rotating file output, and Qt UI bridging."""
    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicate lines
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # 1. Console Stream Handler (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler (optional)
    if log_file_path is not None:
        resolved_path = Path(log_file_path).resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(resolved_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 3. Qt Signal Handler for GUI Streaming
    qt_handler = _QtLogHandler(_GLOBAL_QT_LOG_BRIDGE)
    qt_handler.setLevel(log_level)
    qt_handler.setFormatter(formatter)
    root_logger.addHandler(qt_handler)

    logging.getLogger("desktop_macro_suite").info(
        "Logging initialized at level %s.", logging.getLevelName(log_level)
    )

    return _GLOBAL_QT_LOG_BRIDGE