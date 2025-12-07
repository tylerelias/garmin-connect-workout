"""Service layer for workout operations.

This module provides a higher-level API for GUI and programmatic access,
with support for progress callbacks, cancellation, and structured results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .auth_manager import GarminSession
from .csv_parser import parse_training_plan
from .domain_models import Workout
from .garmin_client import (
    API_DELAY_SECONDS,
    GarminClientError,
    delete_scheduled_workout,
    delete_workout,
    download_activities_to_folder,
    download_planned_workouts_to_folder,
    get_all_workout_templates,
    get_scheduled_workouts_in_range,
    upload_and_schedule,
)

logger = logging.getLogger(__name__)


# Type aliases for callbacks
ProgressCallback = Callable[[int, int, str], None]  # (current, total, message)


@dataclass
class UploadResult:
    """Result of a batch upload operation."""

    total: int = 0
    uploaded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class DeleteResult:
    """Result of a batch delete operation."""

    total: int = 0
    deleted: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class DownloadResult:
    """Result of a download operation."""

    activities: int = 0
    files: int = 0
    total_distance_km: float = 0.0
    total_duration_hours: float = 0.0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass
class ScheduledWorkout:
    """Simplified representation of a scheduled workout."""

    calendar_id: int
    workout_id: int | None
    title: str
    date: date
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkoutTemplate:
    """Simplified representation of a workout template."""

    workout_id: int
    name: str
    sport_type: str
    raw_data: dict[str, Any] = field(default_factory=dict)


class WorkoutService:
    """High-level service for workout operations.

    This class wraps the low-level garmin_client functions and provides:
    - Progress callbacks for UI updates
    - Cancellation support via threading.Event
    - Structured result objects
    - Batch operations with error handling
    """

    def __init__(
        self,
        session: GarminSession,
        delay: float = API_DELAY_SECONDS,
    ):
        """Initialize the workout service.

        Args:
            session: Authenticated GarminSession
            delay: Delay between API calls (seconds)
        """
        self.session = session
        self.delay = delay

    def parse_csv(
        self,
        csv_path: Path | str,
        start_date: date,
    ) -> list[tuple[date, Workout]]:
        """Parse a CSV training plan.

        Args:
            csv_path: Path to CSV file
            start_date: Start date for the training plan (should be Monday)

        Returns:
            List of (date, Workout) tuples

        Raises:
            ValueError: If CSV parsing fails
        """
        return parse_training_plan(Path(csv_path), start_date)

    def upload_training_plan(
        self,
        workouts: list[tuple[date, Workout]],
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> UploadResult:
        """Upload a batch of workouts.

        Args:
            workouts: List of (date, Workout) tuples to upload
            progress_callback: Optional callback(current, total, message)
            cancel_event: Optional threading.Event to check for cancellation

        Returns:
            UploadResult with statistics
        """
        result = UploadResult(total=len(workouts))

        for i, (workout_date, workout) in enumerate(workouts):
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                result.cancelled = True
                break

            # Report progress
            if progress_callback:
                progress_callback(
                    i,
                    len(workouts),
                    f"Uploading: {workout.name} ({workout_date})",
                )

            try:
                upload_and_schedule(
                    self.session,
                    workout,
                    workout_date,
                    delay=self.delay,
                )
                result.uploaded += 1

            except Exception as e:
                result.failed += 1
                error_msg = f"{workout.name} ({workout_date}): {e}"
                result.errors.append(error_msg)
                logger.error(f"Upload failed: {error_msg}")

        # Final progress callback
        if progress_callback:
            progress_callback(
                result.uploaded,
                len(workouts),
                "Upload complete" if not result.cancelled else "Upload cancelled",
            )

        return result

    def get_scheduled_workouts(
        self,
        start_date: date,
        end_date: date,
    ) -> list[ScheduledWorkout]:
        """Get scheduled workouts in a date range.

        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)

        Returns:
            List of ScheduledWorkout objects
        """
        raw_workouts = get_scheduled_workouts_in_range(
            self.session,
            start_date,
            end_date,
        )

        workouts = []
        for item in raw_workouts:
            try:
                workout_date = date.fromisoformat(item.get("date", ""))
            except (ValueError, TypeError):
                continue

            workouts.append(
                ScheduledWorkout(
                    calendar_id=item.get("id", 0),
                    workout_id=item.get("workoutId"),
                    title=item.get("title", "Untitled"),
                    date=workout_date,
                    raw_data=item,
                )
            )

        return sorted(workouts, key=lambda w: w.date)

    def delete_scheduled_workouts(
        self,
        workouts: list[ScheduledWorkout],
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> DeleteResult:
        """Delete scheduled workouts from the calendar.

        Args:
            workouts: List of ScheduledWorkout objects to delete
            progress_callback: Optional callback(current, total, message)
            cancel_event: Optional threading.Event for cancellation

        Returns:
            DeleteResult with statistics
        """
        result = DeleteResult(total=len(workouts))

        for i, workout in enumerate(workouts):
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                result.cancelled = True
                break

            # Report progress
            if progress_callback:
                progress_callback(
                    i,
                    len(workouts),
                    f"Deleting: {workout.title} ({workout.date})",
                )

            try:
                delete_scheduled_workout(
                    self.session,
                    workout.calendar_id,
                    delay=self.delay,
                )
                result.deleted += 1

            except Exception as e:
                result.failed += 1
                error_msg = f"{workout.title} ({workout.date}): {e}"
                result.errors.append(error_msg)
                logger.error(f"Delete failed: {error_msg}")

        # Final progress callback
        if progress_callback:
            progress_callback(
                result.deleted,
                len(workouts),
                "Delete complete" if not result.cancelled else "Delete cancelled",
            )

        return result

    def get_workout_templates(
        self,
        name_contains: str | None = None,
    ) -> list[WorkoutTemplate]:
        """Get all workout templates from the library.

        Args:
            name_contains: Optional filter by name substring (case-insensitive)

        Returns:
            List of WorkoutTemplate objects
        """
        raw_templates = get_all_workout_templates(self.session)

        templates = []
        for item in raw_templates:
            name = item.get("workoutName", "Untitled")

            # Apply filter if provided
            if name_contains and name_contains.lower() not in name.lower():
                continue

            templates.append(
                WorkoutTemplate(
                    workout_id=item.get("workoutId", 0),
                    name=name,
                    sport_type=item.get("sportType", {}).get("sportTypeKey", "unknown"),
                    raw_data=item,
                )
            )

        return sorted(templates, key=lambda t: t.name.lower())

    def get_unused_templates(
        self,
        name_contains: str | None = None,
        lookahead_days: int = 730,
    ) -> tuple[list[WorkoutTemplate], list[WorkoutTemplate]]:
        """Get templates split into unused and scheduled.

        Args:
            name_contains: Optional filter by name substring
            lookahead_days: Days to look ahead for scheduled workouts

        Returns:
            Tuple of (unused_templates, scheduled_templates)
        """
        all_templates = self.get_workout_templates(name_contains)

        # Get scheduled workouts to check which templates are in use
        today = date.today()
        future_end = today + timedelta(days=lookahead_days)
        scheduled = get_scheduled_workouts_in_range(self.session, today, future_end)

        # Build set of workout IDs that are scheduled
        scheduled_workout_ids = {
            item.get("workoutId")
            for item in scheduled
            if item.get("workoutId")
        }

        unused = []
        scheduled_templates = []

        for template in all_templates:
            if template.workout_id in scheduled_workout_ids:
                scheduled_templates.append(template)
            else:
                unused.append(template)

        return unused, scheduled_templates

    def delete_templates(
        self,
        templates: list[WorkoutTemplate],
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> DeleteResult:
        """Delete workout templates from the library.

        Args:
            templates: List of WorkoutTemplate objects to delete
            progress_callback: Optional callback(current, total, message)
            cancel_event: Optional threading.Event for cancellation

        Returns:
            DeleteResult with statistics
        """
        result = DeleteResult(total=len(templates))

        for i, template in enumerate(templates):
            # Check for cancellation
            if cancel_event and cancel_event.is_set():
                result.cancelled = True
                break

            # Report progress
            if progress_callback:
                progress_callback(
                    i,
                    len(templates),
                    f"Deleting: {template.name}",
                )

            try:
                delete_workout(self.session, str(template.workout_id))
                result.deleted += 1

            except Exception as e:
                result.failed += 1
                error_msg = f"{template.name}: {e}"
                result.errors.append(error_msg)
                logger.error(f"Delete template failed: {error_msg}")

        # Final progress callback
        if progress_callback:
            progress_callback(
                result.deleted,
                len(templates),
                "Delete complete" if not result.cancelled else "Delete cancelled",
            )

        return result

    def download_activities(
        self,
        start_date: date,
        end_date: date,
        output_dir: Path,
        activity_type: str | None = None,
        include_planned: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> DownloadResult:
        """Download activities and optionally planned workouts.

        Args:
            start_date: Start of range
            end_date: End of range
            output_dir: Directory to save files
            activity_type: Optional filter (e.g., "running")
            include_planned: Also download scheduled workouts
            progress_callback: Optional callback for progress
            cancel_event: Optional cancellation event

        Returns:
            DownloadResult with statistics
        """
        result = DownloadResult()

        # Download completed activities
        stats = download_activities_to_folder(
            self.session,
            start_date,
            end_date,
            output_dir,
            activity_type=activity_type,
            delay=self.delay,
            progress_callback=progress_callback,
        )

        result.activities = stats.get("activities", 0)
        result.files = stats.get("files", 0)
        result.total_distance_km = stats.get("total_distance_m", 0) / 1000
        result.total_duration_hours = stats.get("total_duration_s", 0) / 3600
        result.errors.extend(stats.get("errors", []))

        # Download planned workouts if requested
        if include_planned:
            planned_stats = download_planned_workouts_to_folder(
                self.session,
                start_date,
                end_date,
                output_dir,
                delay=self.delay,
                progress_callback=progress_callback,
            )
            result.files += planned_stats.get("files", 0)
            result.errors.extend(planned_stats.get("errors", []))

        return result
