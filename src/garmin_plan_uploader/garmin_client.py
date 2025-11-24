"""Garmin Connect client for workout upload and scheduling.

This module handles the conversion of Workout objects to Garmin API payloads
and the actual API calls to create and schedule workouts.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from .auth_manager import GarminSession
from .domain_models import Workout

logger = logging.getLogger(__name__)

# Rate limiting delay between API calls (seconds)
API_DELAY_SECONDS = 2.0


class GarminClientError(Exception):
    """Raised when a Garmin API call fails."""

    pass


class WorkoutUploadError(GarminClientError):
    """Raised when workout upload fails."""

    pass


class WorkoutScheduleError(GarminClientError):
    """Raised when workout scheduling fails."""

    pass


def upload_workout(session: GarminSession, workout: Workout) -> str:
    """Upload a workout to Garmin Connect.

    Args:
        session: Authenticated GarminSession
        workout: Workout object to upload

    Returns:
        The workout ID assigned by Garmin

    Raises:
        WorkoutUploadError: If upload fails
    """
    payload = workout.to_garmin_dict()

    logger.debug(f"Uploading workout: {workout.name}")
    logger.debug(f"Payload: {payload}")

    try:
        # Use the garth client directly for the POST request
        # The garminconnect library's upload_workout method may not exist
        # or have different signature, so we use garth directly
        response = session.garth.post(
            "connectapi",
            "/workout-service/workout",
            json=payload,
            api=True,
        )

        # Response should contain the workout with assigned ID
        if isinstance(response, dict):
            workout_id = response.get("workoutId")
            if workout_id:
                logger.info(f"Uploaded workout '{workout.name}' with ID: {workout_id}")
                return str(workout_id)

        # Try to extract from response if it's the workout object
        if hasattr(response, "json"):
            data = response.json()
            workout_id = data.get("workoutId")
            if workout_id:
                logger.info(f"Uploaded workout '{workout.name}' with ID: {workout_id}")
                return str(workout_id)

        raise WorkoutUploadError(f"No workout ID in response: {response}")

    except Exception as e:
        if isinstance(e, WorkoutUploadError):
            raise
        raise WorkoutUploadError(f"Failed to upload workout '{workout.name}': {e}") from e


def schedule_workout(session: GarminSession, workout_id: str, schedule_date: date) -> None:
    """Schedule a workout for a specific date.

    Args:
        session: Authenticated GarminSession
        workout_id: The Garmin workout ID to schedule
        schedule_date: The date to schedule the workout

    Raises:
        WorkoutScheduleError: If scheduling fails
    """
    # Format date as YYYY-MM-DD
    date_str = schedule_date.isoformat()

    logger.debug(f"Scheduling workout {workout_id} for {date_str}")

    try:
        # POST to /workout-service/schedule/{workout_id}
        url = f"/workout-service/schedule/{workout_id}"
        payload = {"date": date_str}

        response = session.garth.post(
            "connectapi",
            url,
            json=payload,
            api=True,
        )

        logger.info(f"Scheduled workout {workout_id} for {date_str}")

    except Exception as e:
        raise WorkoutScheduleError(
            f"Failed to schedule workout {workout_id} for {date_str}: {e}"
        ) from e


def upload_and_schedule(
    session: GarminSession,
    workout: Workout,
    schedule_date: date,
    *,
    delay: float = API_DELAY_SECONDS,
) -> str:
    """Upload a workout and schedule it for a specific date.

    This is the main function to use for adding workouts to the Garmin calendar.
    It handles rate limiting with delays between API calls.

    Args:
        session: Authenticated GarminSession
        workout: Workout object to upload
        schedule_date: Date to schedule the workout
        delay: Delay in seconds between API calls (default: 2.0)

    Returns:
        The workout ID assigned by Garmin

    Raises:
        WorkoutUploadError: If upload fails
        WorkoutScheduleError: If scheduling fails
    """
    # Upload the workout
    workout_id = upload_workout(session, workout)

    # Rate limiting delay
    if delay > 0:
        time.sleep(delay)

    # Schedule the workout
    schedule_workout(session, workout_id, schedule_date)

    # Another delay before next operation
    if delay > 0:
        time.sleep(delay)

    return workout_id


def delete_workout(session: GarminSession, workout_id: str) -> None:
    """Delete a workout from Garmin Connect.

    Args:
        session: Authenticated GarminSession
        workout_id: The workout ID to delete

    Raises:
        GarminClientError: If deletion fails
    """
    logger.debug(f"Deleting workout {workout_id}")

    try:
        url = f"/workout-service/workout/{workout_id}"
        session.garth.delete("connectapi", url, api=True)
        logger.info(f"Deleted workout {workout_id}")

    except Exception as e:
        raise GarminClientError(f"Failed to delete workout {workout_id}: {e}") from e


def get_existing_workouts(
    session: GarminSession,
    start: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get list of existing workouts from Garmin Connect.

    Args:
        session: Authenticated GarminSession
        start: Starting index for pagination
        limit: Maximum number of workouts to return

    Returns:
        List of workout dictionaries

    Raises:
        GarminClientError: If request fails
    """
    try:
        # Use the garminconnect client method if available
        return session.client.get_workouts(start=start, limit=limit)
    except Exception as e:
        raise GarminClientError(f"Failed to get workouts: {e}") from e


def find_workout_by_name(
    session: GarminSession,
    name: str,
) -> dict[str, Any] | None:
    """Find an existing workout by name.

    Args:
        session: Authenticated GarminSession
        name: Workout name to search for

    Returns:
        Workout dictionary if found, None otherwise
    """
    try:
        workouts = get_existing_workouts(session, limit=500)
        for workout in workouts:
            if workout.get("workoutName") == name:
                return workout
        return None
    except GarminClientError:
        return None


def get_calendar_items(
    session: GarminSession,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    """Get calendar items for a specific month.

    Args:
        session: Authenticated GarminSession
        year: Year (e.g., 2025)
        month: Month (1-12, but API uses 0-11 internally)

    Returns:
        List of calendar item dictionaries

    Raises:
        GarminClientError: If request fails
    """
    # Garmin API uses 0-indexed months (0=January, 11=December)
    api_month = month - 1

    try:
        url = f"/calendar-service/year/{year}/month/{api_month}"
        response = session.garth.connectapi(url)
        return response.get("calendarItems", [])
    except Exception as e:
        raise GarminClientError(f"Failed to get calendar items: {e}") from e


def get_scheduled_workouts_in_range(
    session: GarminSession,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Get all scheduled workouts within a date range.

    Args:
        session: Authenticated GarminSession
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        List of scheduled workout calendar items (deduplicated by calendar ID)

    Raises:
        GarminClientError: If request fails
    """
    from datetime import datetime

    # Use a dict to deduplicate by calendar ID
    workouts_by_id: dict[int, dict[str, Any]] = {}

    # Iterate through each month in the range
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        try:
            items = get_calendar_items(session, current.year, current.month)

            # Filter for workout items within the date range
            for item in items:
                if item.get("itemType") != "workout":
                    continue

                item_date_str = item.get("date")
                if not item_date_str:
                    continue

                item_date = date.fromisoformat(item_date_str)
                if start_date <= item_date <= end_date:
                    # Deduplicate by calendar ID
                    calendar_id = item.get("id")
                    if calendar_id and calendar_id not in workouts_by_id:
                        workouts_by_id[calendar_id] = item

        except GarminClientError:
            logger.warning(f"Failed to get calendar for {current.year}-{current.month:02d}")

        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return list(workouts_by_id.values())


def delete_scheduled_workout(
    session: GarminSession,
    calendar_id: int,
    *,
    delay: float = API_DELAY_SECONDS,
) -> None:
    """Delete a scheduled workout from the calendar.

    This removes the workout from the calendar but does NOT delete the
    underlying workout definition.

    Args:
        session: Authenticated GarminSession
        calendar_id: The calendar item ID (not the workout ID)
        delay: Delay after deletion for rate limiting

    Raises:
        GarminClientError: If deletion fails
    """
    logger.debug(f"Deleting scheduled workout with calendar ID: {calendar_id}")

    try:
        # DELETE the scheduled workout using session's garth client
        response = session.garth.request(
            "DELETE",
            "connectapi",
            f"/workout-service/schedule/{calendar_id}",
            api=True,
        )

        if response.status_code not in (200, 204):
            raise GarminClientError(
                f"Delete returned status {response.status_code}: {response.text}"
            )

        logger.info(f"Deleted scheduled workout {calendar_id}")

        if delay > 0:
            time.sleep(delay)

    except Exception as e:
        if isinstance(e, GarminClientError):
            raise
        raise GarminClientError(
            f"Failed to delete scheduled workout {calendar_id}: {e}"
        ) from e


def delete_scheduled_workouts_in_range(
    session: GarminSession,
    start_date: date,
    end_date: date,
    *,
    delay: float = API_DELAY_SECONDS,
) -> int:
    """Delete all scheduled workouts within a date range.

    Args:
        session: Authenticated GarminSession
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        delay: Delay between deletions for rate limiting

    Returns:
        Number of workouts deleted

    Raises:
        GarminClientError: If fetching or deletion fails
    """
    # Get all scheduled workouts in the range
    workouts = get_scheduled_workouts_in_range(session, start_date, end_date)

    if not workouts:
        logger.info(f"No scheduled workouts found between {start_date} and {end_date}")
        return 0

    logger.info(f"Found {len(workouts)} scheduled workouts to delete")

    deleted_count = 0
    for workout in workouts:
        calendar_id = workout.get("id")
        title = workout.get("title", "Untitled")
        workout_date = workout.get("date", "Unknown date")

        if not calendar_id:
            logger.warning(f"Workout '{title}' has no calendar ID, skipping")
            continue

        try:
            delete_scheduled_workout(session, calendar_id, delay=delay)
            deleted_count += 1
            logger.info(f"Deleted: {title} ({workout_date})")
        except GarminClientError as e:
            logger.error(f"Failed to delete '{title}' ({workout_date}): {e}")

    return deleted_count
