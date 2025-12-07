"""Worker threads for running Garmin API operations without blocking the UI."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QThread, Signal

from ..auth_manager import AuthenticationError, GarminSession, MFARequiredError
from ..workout_service import (
    DeleteResult,
    DownloadResult,
    ScheduledWorkout,
    UploadResult,
    WorkoutService,
    WorkoutTemplate,
)

if TYPE_CHECKING:
    from ..domain_models import Workout

logger = logging.getLogger(__name__)


class LoginWorker(QObject):
    """Worker for handling login in a background thread."""

    # Signals
    finished = Signal()
    success = Signal(str)  # display_name
    mfa_required = Signal(object, str)  # garmin_client, mfa_context
    error = Signal(str)  # error message

    def __init__(
        self,
        session: GarminSession,
        email: str | None = None,
        password: str | None = None,
        force_new: bool = False,
    ):
        super().__init__()
        self.session = session
        self.email = email
        self.password = password
        self.force_new = force_new

    def run(self) -> None:
        """Execute login in background thread."""
        try:
            self.session.login(
                email=self.email,
                password=self.password,
                force_new_login=self.force_new,
            )
            display_name = self.session.get_display_name()
            self.success.emit(display_name)

        except MFARequiredError as e:
            self.mfa_required.emit(e.garmin_client, e.mfa_context)

        except AuthenticationError as e:
            self.error.emit(str(e))

        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")

        finally:
            self.finished.emit()


class MFAWorker(QObject):
    """Worker for completing MFA authentication."""

    finished = Signal()
    success = Signal(str)  # display_name
    error = Signal(str)  # error message

    def __init__(
        self,
        session: GarminSession,
        garmin_client: Any,
        mfa_context: str,
        mfa_code: str,
    ):
        super().__init__()
        self.session = session
        self.garmin_client = garmin_client
        self.mfa_context = mfa_context
        self.mfa_code = mfa_code

    def run(self) -> None:
        """Complete MFA in background thread."""
        try:
            self.session.complete_mfa(
                self.garmin_client,
                self.mfa_context,
                self.mfa_code,
            )
            display_name = self.session.get_display_name()
            self.success.emit(display_name)

        except AuthenticationError as e:
            self.error.emit(str(e))

        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")

        finally:
            self.finished.emit()


class FetchWorkoutsWorker(QObject):
    """Worker for fetching scheduled workouts."""

    finished = Signal()
    success = Signal(list)  # list[ScheduledWorkout]
    error = Signal(str)
    progress = Signal(str)  # status message

    def __init__(
        self,
        service: WorkoutService,
        start_date: date,
        end_date: date,
    ):
        super().__init__()
        self.service = service
        self.start_date = start_date
        self.end_date = end_date

    def run(self) -> None:
        """Fetch workouts in background thread."""
        try:
            self.progress.emit("Fetching scheduled workouts...")
            workouts = self.service.get_scheduled_workouts(
                self.start_date,
                self.end_date,
            )
            self.success.emit(workouts)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()


class UploadWorker(QObject):
    """Worker for uploading workouts."""

    finished = Signal()
    success = Signal(object)  # UploadResult
    error = Signal(str)
    progress = Signal(int, int, str)  # current, total, message

    def __init__(
        self,
        service: WorkoutService,
        workouts: list[tuple[date, "Workout"]],
    ):
        super().__init__()
        self.service = service
        self.workouts = workouts
        self.cancel_event = Event()

    def run(self) -> None:
        """Upload workouts in background thread."""
        try:
            result = self.service.upload_training_plan(
                self.workouts,
                progress_callback=self._on_progress,
                cancel_event=self.cancel_event,
            )
            self.success.emit(result)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        """Emit progress signal."""
        self.progress.emit(current, total, message)

    def cancel(self) -> None:
        """Request cancellation."""
        self.cancel_event.set()


class DeleteWorkoutsWorker(QObject):
    """Worker for deleting scheduled workouts."""

    finished = Signal()
    success = Signal(object)  # DeleteResult
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(
        self,
        service: WorkoutService,
        workouts: list[ScheduledWorkout],
    ):
        super().__init__()
        self.service = service
        self.workouts = workouts
        self.cancel_event = Event()

    def run(self) -> None:
        """Delete workouts in background thread."""
        try:
            result = self.service.delete_scheduled_workouts(
                self.workouts,
                progress_callback=self._on_progress,
                cancel_event=self.cancel_event,
            )
            self.success.emit(result)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)

    def cancel(self) -> None:
        self.cancel_event.set()


class FetchTemplatesWorker(QObject):
    """Worker for fetching workout templates."""

    finished = Signal()
    success = Signal(list, list)  # unused_templates, scheduled_templates
    error = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        service: WorkoutService,
        name_contains: str | None = None,
    ):
        super().__init__()
        self.service = service
        self.name_contains = name_contains

    def run(self) -> None:
        """Fetch templates in background thread."""
        try:
            self.progress.emit("Fetching workout templates...")
            unused, scheduled = self.service.get_unused_templates(
                name_contains=self.name_contains,
            )
            self.success.emit(unused, scheduled)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()


class DeleteTemplatesWorker(QObject):
    """Worker for deleting workout templates."""

    finished = Signal()
    success = Signal(object)  # DeleteResult
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(
        self,
        service: WorkoutService,
        templates: list[WorkoutTemplate],
    ):
        super().__init__()
        self.service = service
        self.templates = templates
        self.cancel_event = Event()

    def run(self) -> None:
        """Delete templates in background thread."""
        try:
            result = self.service.delete_templates(
                self.templates,
                progress_callback=self._on_progress,
                cancel_event=self.cancel_event,
            )
            self.success.emit(result)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)

    def cancel(self) -> None:
        self.cancel_event.set()


class DownloadWorker(QObject):
    """Worker for downloading activities."""

    finished = Signal()
    success = Signal(object)  # DownloadResult
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(
        self,
        service: WorkoutService,
        start_date: date,
        end_date: date,
        output_dir: Path,
        activity_type: str | None = None,
        include_planned: bool = False,
    ):
        super().__init__()
        self.service = service
        self.start_date = start_date
        self.end_date = end_date
        self.output_dir = output_dir
        self.activity_type = activity_type
        self.include_planned = include_planned
        self.cancel_event = Event()

    def run(self) -> None:
        """Download activities in background thread."""
        try:
            result = self.service.download_activities(
                self.start_date,
                self.end_date,
                self.output_dir,
                activity_type=self.activity_type,
                include_planned=self.include_planned,
                progress_callback=self._on_progress,
                cancel_event=self.cancel_event,
            )
            self.success.emit(result)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)

    def cancel(self) -> None:
        self.cancel_event.set()


def run_worker(worker: QObject) -> QThread:
    """Helper to run a worker in a QThread.

    Args:
        worker: Worker object with a run() method

    Returns:
        The QThread (already started)

    Usage:
        worker = LoginWorker(session, email, password)
        worker.success.connect(on_success)
        worker.error.connect(on_error)
        thread = run_worker(worker)
    """
    thread = QThread()
    worker.moveToThread(thread)

    # Connect thread start to worker run
    thread.started.connect(worker.run)

    # Clean up when finished
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread
