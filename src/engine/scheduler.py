from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Final

from src.core.ast import MacroSequence
from src.core.types import CancellationTokenProtocol, Milliseconds
from src.engine.playback_engine import MacroPlaybackEngine

__all__: Final[list[str]] = ["JobState", "MacroScheduler", "ScheduledJob"]


class JobState(enum.Enum):
    """Lifecycle states of a scheduled macro sequence playback job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class ScheduledJob:
    """Descriptor and state container for queued macro execution jobs."""

    id: str
    sequence: MacroSequence
    delay_ms: Milliseconds
    interval_ms: Milliseconds | None
    repeat_count: int
    remaining_runs: int
    scheduled_epoch: float
    state: JobState = JobState.PENDING
    last_error: str | None = None


class MacroScheduler:
    """Thread-safe background scheduler for delayed and recurring macro playback."""

    def __init__(
        self,
        playback_engine: MacroPlaybackEngine,
        cancellation_token: CancellationTokenProtocol | None = None,
    ) -> None:
        self._playback_engine: MacroPlaybackEngine = playback_engine
        self._token: CancellationTokenProtocol | None = cancellation_token
        self._lock: threading.Lock = threading.Lock()
        self._jobs: dict[str, ScheduledJob] = {}
        self._running: bool = False
        self._wake_event: threading.Event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        """Starts the scheduler background worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._wake_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="MacroSchedulerWorker",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self) -> None:
        """Stops the scheduler worker and waits for active job cycles to conclude."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._wake_event.set()

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None

    def schedule_once(
        self,
        sequence: MacroSequence,
        delay_ms: Milliseconds = 0.0,
    ) -> str:
        """Enqueues a one-time execution of the macro sequence after an optional delay."""
        job_id: str = str(uuid.uuid4())
        scheduled_epoch: float = time.monotonic() + (max(0.0, delay_ms) / 1000.0)

        job = ScheduledJob(
            id=job_id,
            sequence=sequence,
            delay_ms=delay_ms,
            interval_ms=None,
            repeat_count=1,
            remaining_runs=1,
            scheduled_epoch=scheduled_epoch,
            state=JobState.PENDING,
        )

        with self._lock:
            self._jobs[job_id] = job
            self._wake_event.set()

        return job_id

    def schedule_interval(
        self,
        sequence: MacroSequence,
        interval_ms: Milliseconds,
        repeat_count: int = 0,
        initial_delay_ms: Milliseconds = 0.0,
    ) -> str:
        """Enqueues a recurring macro execution. Set repeat_count <= 0 for indefinite recurrence."""
        if interval_ms <= 0.0:
            raise ValueError("interval_ms must be greater than zero")

        job_id: str = str(uuid.uuid4())
        scheduled_epoch: float = time.monotonic() + (
            max(0.0, initial_delay_ms) / 1000.0
        )

        job = ScheduledJob(
            id=job_id,
            sequence=sequence,
            delay_ms=initial_delay_ms,
            interval_ms=interval_ms,
            repeat_count=repeat_count,
            remaining_runs=repeat_count,
            scheduled_epoch=scheduled_epoch,
            state=JobState.PENDING,
        )

        with self._lock:
            self._jobs[job_id] = job
            self._wake_event.set()

        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """Cancels a pending or running job. Returns True if successfully cancelled."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.state in (JobState.PENDING, JobState.RUNNING):
                job.state = JobState.CANCELLED
                self._wake_event.set()
                return True
            return False

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Returns the descriptor of a given job, or None if not found."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[ScheduledJob]:
        """Returns snapshot copies of all registered scheduled jobs."""
        with self._lock:
            return list(self._jobs.values())

    def clear_completed_jobs(self) -> None:
        """Removes finished, cancelled, and failed jobs from the registry."""
        with self._lock:
            terminal_states: set[JobState] = {
                JobState.COMPLETED,
                JobState.CANCELLED,
                JobState.FAILED,
            }
            self._jobs = {
                k: v for k, v in self._jobs.items() if v.state not in terminal_states
            }

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    break

            if self._token is not None and self._token.is_cancelled():
                with self._lock:
                    for job in self._jobs.values():
                        if job.state == JobState.PENDING:
                            job.state = JobState.CANCELLED
                break

            now: float = time.monotonic()
            next_wake_delay: float = 1.0
            ready_jobs: list[ScheduledJob] = []

            with self._lock:
                for job in self._jobs.values():
                    if job.state == JobState.PENDING:
                        time_until: float = job.scheduled_epoch - now
                        if time_until <= 0.0:
                            job.state = JobState.RUNNING
                            ready_jobs.append(job)
                        elif time_until < next_wake_delay:
                            next_wake_delay = max(0.005, time_until)

            for job in ready_jobs:
                if self._token is not None and self._token.is_cancelled():
                    with self._lock:
                        job.state = JobState.CANCELLED
                    continue

                try:
                    self._playback_engine.play(job.sequence, repeat_count=1)
                    with self._lock:
                        job.remaining_runs -= 1
                        if job.interval_ms is not None and (
                            job.repeat_count <= 0 or job.remaining_runs > 0
                        ):
                            job.scheduled_epoch = time.monotonic() + (
                                job.interval_ms / 1000.0
                            )
                            job.state = JobState.PENDING
                        else:
                            job.state = JobState.COMPLETED
                except Exception as exc:
                    with self._lock:
                        job.state = JobState.FAILED
                        job.last_error = str(exc)

            if ready_jobs:
                continue

            _ = self._wake_event.wait(timeout=next_wake_delay)
            self._wake_event.clear()