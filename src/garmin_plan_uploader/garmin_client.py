"""Garmin Connect client for workout upload and scheduling.

This module handles the conversion of Workout objects to Garmin API payloads
and the actual API calls to create and schedule workouts.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

from .auth_manager import GarminSession
from .domain_models import Workout

logger = logging.getLogger(__name__)

# Rate limiting delay between API calls (seconds)
# Reduced from 2.0 to 1.0 for better performance while still preventing rate limiting
API_DELAY_SECONDS = 1.0


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

    # Single delay between upload and schedule (reduced from 2 delays)
    if delay > 0:
        time.sleep(delay)

    # Schedule the workout
    schedule_workout(session, workout_id, schedule_date)

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


def get_all_workout_templates(
    session: GarminSession,
    batch_size: int = 100,
) -> list[dict[str, Any]]:
    """Get ALL workout templates from the library (with pagination).

    This fetches all saved workout definitions, not scheduled instances.

    Args:
        session: Authenticated GarminSession
        batch_size: Number of workouts to fetch per request

    Returns:
        List of all workout dictionaries

    Raises:
        GarminClientError: If request fails
    """
    all_workouts: list[dict[str, Any]] = []
    start = 0

    while True:
        batch = get_existing_workouts(session, start=start, limit=batch_size)
        if not batch:
            break
        all_workouts.extend(batch)
        if len(batch) < batch_size:
            break
        start += batch_size

    return all_workouts


def delete_workout_templates(
    session: GarminSession,
    workout_ids: list[str | int],
    *,
    delay: float = API_DELAY_SECONDS,
) -> dict[str, Any]:
    """Delete multiple workout templates by ID.

    Args:
        session: Authenticated GarminSession
        workout_ids: List of workout IDs to delete
        delay: Delay between deletions for rate limiting

    Returns:
        Dictionary with deletion statistics:
        - "deleted": number successfully deleted
        - "failed": number that failed
        - "errors": list of error messages
    """
    stats: dict[str, Any] = {
        "deleted": 0,
        "failed": 0,
        "errors": [],
    }

    for workout_id in workout_ids:
        try:
            delete_workout(session, str(workout_id))
            stats["deleted"] += 1

            if delay > 0:
                time.sleep(delay)

        except GarminClientError as e:
            stats["failed"] += 1
            stats["errors"].append(f"Workout {workout_id}: {e}")
            logger.error(f"Failed to delete workout {workout_id}: {e}")

    return stats


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
    # Use a dict to deduplicate by calendar ID
    workouts_by_id: dict[int, dict[str, Any]] = {}

    # Iterate through each month in the range
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        try:
            items = get_calendar_items(session, current.year, current.month)

            # Filter for workout items within the date range
            for item in items:
                # Early exit if not a workout
                if item.get("itemType") != "workout":
                    continue

                item_date_str = item.get("date")
                if not item_date_str:
                    continue

                # Parse date once and cache the result
                try:
                    item_date = date.fromisoformat(item_date_str)
                except (ValueError, TypeError):
                    continue

                # Check date range
                if start_date <= item_date <= end_date:
                    # Deduplicate by calendar ID
                    calendar_id = item.get("id")
                    if calendar_id and calendar_id not in workouts_by_id:
                        workouts_by_id[calendar_id] = item

        except GarminClientError:
            logger.warning(f"Failed to get calendar for {current.year}-{current.month:02d}")

        # Move to next month using simpler logic
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

        # Only sleep if delay is configured (moved to caller responsibility for batch operations)
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


# =============================================================================
# Activity Download Functions
# =============================================================================


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Args:
        name: Original name (e.g., workout name)

    Returns:
        Sanitized string safe for filesystem use
    """
    # Replace problematic characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Replace multiple spaces/underscores with single underscore
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    # Remove leading/trailing underscores and spaces
    sanitized = sanitized.strip('_ ')
    # Limit length to avoid filesystem issues
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized or "unnamed"


def get_activities_in_range(
    session: GarminSession,
    start_date: date,
    end_date: date,
    activity_type: str | None = None,
) -> list[dict[str, Any]]:
    """Get completed activities within a date range.

    Args:
        session: Authenticated GarminSession
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        activity_type: Optional filter by activity type (e.g., "running", "cycling")

    Returns:
        List of activity dictionaries

    Raises:
        GarminClientError: If request fails
    """
    try:
        activities = session.client.get_activities_by_date(
            startdate=start_date.isoformat(),
            enddate=end_date.isoformat(),
            activitytype=activity_type,
        )
        return activities if activities else []
    except Exception as e:
        raise GarminClientError(f"Failed to get activities: {e}") from e


def get_activity_details(
    session: GarminSession,
    activity_id: int | str,
) -> dict[str, Any]:
    """Get detailed information about a specific activity.

    Args:
        session: Authenticated GarminSession
        activity_id: The activity ID

    Returns:
        Activity details dictionary

    Raises:
        GarminClientError: If request fails
    """
    try:
        return session.client.get_activity(activity_id)
    except Exception as e:
        raise GarminClientError(f"Failed to get activity {activity_id}: {e}") from e


def download_activity_file(
    session: GarminSession,
    activity_id: int | str,
    file_format: str = "ORIGINAL",
) -> bytes:
    """Download an activity file in the specified format.

    Args:
        session: Authenticated GarminSession
        activity_id: The activity ID
        file_format: Format to download: "ORIGINAL" (FIT), "TCX", "GPX", "KML", "CSV"

    Returns:
        Raw file bytes

    Raises:
        GarminClientError: If download fails
    """
    from garminconnect import Garmin

    try:
        # Map format strings to garminconnect enum
        format_map = {
            "ORIGINAL": Garmin.ActivityDownloadFormat.ORIGINAL,
            "FIT": Garmin.ActivityDownloadFormat.ORIGINAL,
            "TCX": Garmin.ActivityDownloadFormat.TCX,
            "GPX": Garmin.ActivityDownloadFormat.GPX,
            "KML": Garmin.ActivityDownloadFormat.KML,
            "CSV": Garmin.ActivityDownloadFormat.CSV,
        }
        dl_fmt = format_map.get(file_format.upper(), Garmin.ActivityDownloadFormat.ORIGINAL)
        return session.client.download_activity(activity_id, dl_fmt=dl_fmt)
    except Exception as e:
        raise GarminClientError(
            f"Failed to download activity {activity_id} as {file_format}: {e}"
        ) from e


def get_workout_details(
    session: GarminSession,
    workout_id: int | str,
) -> dict[str, Any]:
    """Get detailed information about a workout definition.

    Args:
        session: Authenticated GarminSession
        workout_id: The workout ID

    Returns:
        Workout details dictionary

    Raises:
        GarminClientError: If request fails
    """
    try:
        url = f"/workout-service/workout/{workout_id}"
        response = session.garth.connectapi(url)
        return response
    except Exception as e:
        raise GarminClientError(f"Failed to get workout {workout_id}: {e}") from e


def download_workout_file(
    session: GarminSession,
    workout_id: int | str,
) -> bytes:
    """Download a workout as a FIT file.

    Args:
        session: Authenticated GarminSession
        workout_id: The workout ID

    Returns:
        Raw FIT file bytes

    Raises:
        GarminClientError: If download fails
    """
    try:
        url = f"/workout-service/workout/FIT/{workout_id}"
        response = session.garth.get("connectapi", url, api=True)
        return response.content
    except Exception as e:
        raise GarminClientError(
            f"Failed to download workout {workout_id} as FIT: {e}"
        ) from e


def has_gps_data(activity: dict[str, Any]) -> bool:
    """Check if an activity has GPS/polyline data.

    Args:
        activity: Activity dictionary from Garmin API

    Returns:
        True if activity has GPS data
    """
    return activity.get("hasPolyline", False) or activity.get("startLatitude") is not None


def download_activities_to_folder(
    session: GarminSession,
    start_date: date,
    end_date: date,
    output_dir: Path,
    activity_type: str | None = None,
    *,
    delay: float = API_DELAY_SECONDS,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Download all completed activities in a date range to a folder.

    For each activity, downloads:
    - JSON metadata file
    - FIT file (original data)
    - GPX file (if activity has GPS data, for outdoor activities)

    Args:
        session: Authenticated GarminSession
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        output_dir: Directory to save files
        activity_type: Optional filter by activity type
        delay: Delay between API calls for rate limiting
        progress_callback: Optional callback(current, total, activity_name) for progress updates

    Returns:
        Dictionary with download statistics:
        - "activities": number of activities downloaded
        - "files": total number of files created
        - "errors": list of error messages
        - "total_distance_m": total distance in meters
        - "total_duration_s": total duration in seconds

    Raises:
        GarminClientError: If fetching activities fails
    """
    # Create output directory
    activities_dir = output_dir / "activities"
    activities_dir.mkdir(parents=True, exist_ok=True)

    # Get activities
    activities = get_activities_in_range(session, start_date, end_date, activity_type)

    stats = {
        "activities": 0,
        "files": 0,
        "errors": [],
        "total_distance_m": 0.0,
        "total_duration_s": 0.0,
    }

    for i, activity in enumerate(activities):
        activity_id = activity.get("activityId")
        activity_name = activity.get("activityName", "Unnamed")
        activity_date = activity.get("startTimeLocal", "")[:10]  # YYYY-MM-DD

        if progress_callback:
            progress_callback(i, len(activities), activity_name)

        if not activity_id:
            stats["errors"].append(f"Activity missing ID: {activity_name}")
            continue

        # Create safe filename prefix
        safe_name = sanitize_filename(activity_name)
        file_prefix = f"{activity_date}_{safe_name}"
        
        # Check GPS data once upfront
        has_gps = has_gps_data(activity)

        try:
            # Save JSON metadata
            json_path = activities_dir / f"{file_prefix}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(activity, f, indent=2, ensure_ascii=False)
            stats["files"] += 1

            # Download FIT file
            try:
                fit_data = download_activity_file(session, activity_id, "ORIGINAL")
                # FIT downloads come as a zip, save as .zip
                fit_path = activities_dir / f"{file_prefix}.zip"
                with open(fit_path, "wb") as f:
                    f.write(fit_data)
                stats["files"] += 1
            except GarminClientError as e:
                stats["errors"].append(f"FIT download failed for {activity_name}: {e}")

            if delay > 0:
                time.sleep(delay)

            # Download GPX if activity has GPS data
            if has_gps:
                try:
                    gpx_data = download_activity_file(session, activity_id, "GPX")
                    gpx_path = activities_dir / f"{file_prefix}.gpx"
                    with open(gpx_path, "wb") as f:
                        f.write(gpx_data)
                    stats["files"] += 1
                    
                    # Only sleep after GPX download if it succeeded
                    if delay > 0:
                        time.sleep(delay)
                except GarminClientError as e:
                    stats["errors"].append(f"GPX download failed for {activity_name}: {e}")

            # Update statistics
            stats["activities"] += 1
            stats["total_distance_m"] += activity.get("distance", 0) or 0
            stats["total_duration_s"] += activity.get("duration", 0) or 0

        except Exception as e:
            stats["errors"].append(f"Error processing {activity_name}: {e}")
            logger.error(f"Error downloading activity {activity_name}: {e}")

    return stats


def download_planned_workouts_to_folder(
    session: GarminSession,
    start_date: date,
    end_date: date,
    output_dir: Path,
    *,
    delay: float = API_DELAY_SECONDS,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Download all scheduled (planned) workouts in a date range to a folder.

    For each scheduled workout, downloads:
    - JSON metadata file with full workout definition
    - FIT file for syncing to device

    Args:
        session: Authenticated GarminSession
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)
        output_dir: Directory to save files
        delay: Delay between API calls for rate limiting
        progress_callback: Optional callback(current, total, workout_name) for progress updates

    Returns:
        Dictionary with download statistics:
        - "workouts": number of workouts downloaded
        - "files": total number of files created
        - "errors": list of error messages

    Raises:
        GarminClientError: If fetching workouts fails
    """
    # Create output directory
    planned_dir = output_dir / "planned"
    planned_dir.mkdir(parents=True, exist_ok=True)

    # Get scheduled workouts
    scheduled = get_scheduled_workouts_in_range(session, start_date, end_date)

    stats = {
        "workouts": 0,
        "files": 0,
        "errors": [],
    }

    for i, item in enumerate(scheduled):
        workout_id = item.get("workoutId")
        workout_name = item.get("title", "Unnamed")
        workout_date = item.get("date", "unknown")

        if progress_callback:
            progress_callback(i, len(scheduled), workout_name)

        if not workout_id:
            stats["errors"].append(f"Scheduled workout missing workoutId: {workout_name}")
            continue

        # Create safe filename prefix
        safe_name = sanitize_filename(workout_name)
        file_prefix = f"{workout_date}_{safe_name}"

        try:
            # Get full workout details
            workout_details = get_workout_details(session, workout_id)

            if delay > 0:
                time.sleep(delay)

            # Save JSON metadata
            json_path = planned_dir / f"{file_prefix}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(workout_details, f, indent=2, ensure_ascii=False)
            stats["files"] += 1

            # Download FIT file
            try:
                fit_data = download_workout_file(session, workout_id)
                fit_path = planned_dir / f"{file_prefix}.fit"
                with open(fit_path, "wb") as f:
                    f.write(fit_data)
                stats["files"] += 1
            except GarminClientError as e:
                stats["errors"].append(f"FIT download failed for {workout_name}: {e}")

            if delay > 0:
                time.sleep(delay)

            stats["workouts"] += 1

        except Exception as e:
            stats["errors"].append(f"Error processing {workout_name}: {e}")
            logger.error(f"Error downloading workout {workout_name}: {e}")

    return stats
