from typing import override


class MacroSuiteError(Exception):
    """Base exception for all domain errors within the automation suite."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message

    @override
    def __str__(self) -> str:
        return self.message


class PlatformError(MacroSuiteError):
    """Base exception for native operating system bindings and input APIs."""

    def __init__(self, message: str, win32_error_code: int | None = None) -> None:
        super().__init__(message)
        self.win32_error_code: int | None = win32_error_code


class HookInstallationError(PlatformError):
    """Raised when an OS-level hook fails to register."""

    def __init__(self, hook_type: str, win32_error_code: int | None = None) -> None:
        super().__init__(
            f"Failed to install OS hook for {hook_type}",
            win32_error_code=win32_error_code,
        )
        self.hook_type: str = hook_type


class HookStarvationError(PlatformError):
    """Raised when the OS drops an input hook due to a low-level timeout threshold."""

    def __init__(self, timeout_ms: int) -> None:
        super().__init__(
            f"Low-level hook was dropped due to callback processing exceeding {timeout_ms}ms"
        )
        self.timeout_ms: int = timeout_ms


class InputSynthesisError(PlatformError):
    """Raised when SendInput or hardware event simulation fails to inject all inputs."""

    def __init__(
        self,
        expected_events: int,
        injected_events: int,
        win32_error_code: int | None = None,
    ) -> None:
        super().__init__(
            f"SendInput partial failure: injected {injected_events}/{expected_events} events",
            win32_error_code=win32_error_code,
        )
        self.expected_events: int = expected_events
        self.injected_events: int = injected_events


class TimerResolutionError(PlatformError):
    """Raised when timeBeginPeriod fails to configure system timer granularity."""

    def __init__(self, desired_resolution_ms: int) -> None:
        super().__init__(
            f"Failed to set multimedia timer resolution to {desired_resolution_ms}ms"
        )
        self.desired_resolution_ms: int = desired_resolution_ms


class ExecutionError(MacroSuiteError):
    """Base exception for runtime action execution and playback engine failures."""

    def __init__(self, message: str, action_id: str | None = None) -> None:
        super().__init__(message)
        self.action_id: str | None = action_id


class ExecutionAbortedError(ExecutionError):
    """Raised when an active playback sequence is aborted via a kill-switch or cancellation token."""

    def __init__(self, reason: str = "Hardware kill-switch triggered") -> None:
        super().__init__(f"Execution aborted: {reason}")
        self.reason: str = reason


class MacroTimeoutError(ExecutionError):
    """Raised when a deterministic delay or visual gate exceeds its timeout limit."""

    def __init__(
        self,
        action_id: str,
        timeout_seconds: float,
        peak_confidence: float | None = None,
        threshold: float | None = None,
    ) -> None:
        message = f"Action '{action_id}' timed out after {timeout_seconds:.3f}s"
        if peak_confidence is not None and threshold is not None:
            message += f" (peak confidence: {peak_confidence:.2f}, required threshold: {threshold:.2f})"
        super().__init__(message, action_id=action_id)
        self.timeout_seconds: float = timeout_seconds
        self.peak_confidence: float | None = peak_confidence
        self.threshold: float | None = threshold


class VisionError(MacroSuiteError):
    """Base exception for screen capture and image processing operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class FrameCaptureError(VisionError):
    """Raised when the desktop frame provider fails to acquire the screen surface."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Screen frame capture failed: {reason}")
        self.reason: str = reason


class TemplateMatchError(VisionError):
    """Raised when a template image is unreadable, corrupted, or has invalid dimensions."""

    def __init__(self, template_path: str, reason: str) -> None:
        super().__init__(f"Template processing error at '{template_path}': {reason}")
        self.template_path: str = template_path
        self.reason: str = reason


class SerializationError(MacroSuiteError):
    """Base exception for AST serialization and parsing failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SchemaVersionMismatchError(SerializationError):
    """Raised when a serialized macro file version is incompatible with the runtime engine."""

    def __init__(self, expected_version: str, actual_version: str) -> None:
        super().__init__(
            f"Incompatible AST schema: expected '{expected_version}', got '{actual_version}'"
        )
        self.expected_version: str = expected_version
        self.actual_version: str = actual_version
