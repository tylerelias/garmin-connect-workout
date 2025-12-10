"""CSV parser for training plan files.

This module parses CSV training plans in the Raistlfiren/garmin-csv-plan format,
handling the indentation-based workout syntax for nested repeat steps.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from .domain_models import (
    CROSS_TRAINING_KEYWORDS,
    STEP_TYPE_MAP,
    DistanceEndCondition,
    EndCondition,
    ExecutableStep,
    HeartRateZoneTarget,
    LapButtonEndCondition,
    NoTarget,
    PaceTarget,
    RepeatStep,
    StepType,
    Target,
    TimeEndCondition,
    Workout,
    WorkoutStep,
    parse_distance_to_meters,
    parse_duration_to_seconds,
    parse_hr_zone,
    parse_pace_to_meters_per_second,
)

logger = logging.getLogger(__name__)

# Day column names in order (Monday = 0)
DAY_COLUMNS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ParsedLine(NamedTuple):
    """A parsed line from workout text."""

    indent_level: int
    keyword: str
    value: str
    notes: str | None


class ParserError(Exception):
    """Raised when parsing fails."""

    pass


def get_indent_level(line: str) -> int:
    """Calculate the indentation level of a line.

    Each level is 2 spaces of indentation (after the leading "- ").

    Args:
        line: The line to analyze

    Returns:
        Indentation level (0 for top-level, 1 for first nested, etc.)
    """
    # Count leading spaces before "- "
    stripped = line.lstrip()
    leading_spaces = len(line) - len(stripped)

    # Each indent level is 2 spaces
    return leading_spaces // 2


def parse_line(line: str) -> ParsedLine | None:
    """Parse a single line of workout text.

    Args:
        line: Line like "- warmup: 15:00 @z2; some notes"

    Returns:
        ParsedLine tuple or None if line is empty/invalid
    """
    line = line.rstrip()
    if not line.strip():
        return None

    indent_level = get_indent_level(line)

    # Remove leading whitespace and dash
    content = line.lstrip()
    if content.startswith("- "):
        content = content[2:]
    elif content.startswith("-"):
        content = content[1:]

    # Split on first colon to get keyword
    if ":" not in content:
        return None

    keyword, rest = content.split(":", 1)
    keyword = keyword.strip().lower()
    rest = rest.strip()

    # Check for notes (after semicolon)
    notes = None
    if ";" in rest:
        rest, notes = rest.split(";", 1)
        rest = rest.strip()
        notes = notes.strip()

    return ParsedLine(
        indent_level=indent_level,
        keyword=keyword,
        value=rest,
        notes=notes,
    )


def parse_target(target_str: str) -> Target:
    """Parse a target string (after @).

    Args:
        target_str: Target like "z2", "4:30-5:00", "4:30-5:00mpk"

    Returns:
        Appropriate Target object
    """
    target_str = target_str.strip()

    # Heart rate zone: z1-z5
    if re.match(r"^z[1-5]$", target_str, re.IGNORECASE):
        zone = parse_hr_zone(target_str)
        return HeartRateZoneTarget(zone=zone)

    # Pace range: mm:ss-mm:ss with optional mpk/mpm suffix
    pace_pattern = r"^\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}(mpk|mpm)?$"
    if re.match(pace_pattern, target_str, re.IGNORECASE):
        min_speed, max_speed = parse_pace_to_meters_per_second(target_str)
        return PaceTarget(min_speed_mps=min_speed, max_speed_mps=max_speed)

    # Unknown target format - log warning and return no target
    logger.warning(f"Unknown target format: {target_str}, using no target")
    return NoTarget()


def parse_end_condition_and_target(value_str: str) -> tuple[EndCondition, Target]:
    """Parse the value part of a step line.

    Args:
        value_str: Value like "15:00 @z2" or "2km" or "lap-button"

    Returns:
        Tuple of (EndCondition, Target)
    """
    value_str = value_str.strip()

    # Check for target (after @)
    target: Target = NoTarget()
    if "@" in value_str:
        parts = value_str.split("@", 1)
        value_str = parts[0].strip()
        target = parse_target(parts[1])

    # Determine end condition type
    value_lower = value_str.lower()

    # Lap button
    if value_lower == "lap-button":
        return LapButtonEndCondition(), target

    # Time duration: mm:ss or mmm:ss
    time_pattern = r"^\d{1,3}:\d{2}$"
    if re.match(time_pattern, value_str):
        seconds = parse_duration_to_seconds(value_str)
        if seconds is None:
            return LapButtonEndCondition(), target
        return TimeEndCondition(duration_seconds=seconds), target

    # Distance: number + unit (km, mi, m, yds)
    distance_pattern = r"^\d+(?:\.\d+)?\s*(km|mi|m|yds|yd|meters|miles|kilometers)$"
    if re.match(distance_pattern, value_lower):
        meters = parse_distance_to_meters(value_str)
        return DistanceEndCondition(distance_meters=meters), target

    # Default to lap button if we can't parse
    logger.warning(f"Could not parse end condition: {value_str}, using lap button")
    return LapButtonEndCondition(), target


def parse_step(parsed_line: ParsedLine) -> ExecutableStep | None:
    """Parse a single step line into an ExecutableStep.

    Args:
        parsed_line: The parsed line data

    Returns:
        ExecutableStep or None if keyword unknown or is a note
    """
    keyword = parsed_line.keyword

    # Get step type from keyword
    if keyword not in STEP_TYPE_MAP:
        logger.warning(f"Unknown step keyword: {keyword}")
        return None

    step_type = STEP_TYPE_MAP[keyword]

    # Skip notes - they are metadata, not actual steps
    if step_type is None:
        logger.debug(f"Skipping note: {parsed_line.value}")
        return None

    # Don't parse repeat steps here (they're handled separately)
    if step_type == StepType.REPEAT:
        return None

    # Parse end condition and target
    end_condition, target = parse_end_condition_and_target(parsed_line.value)

    # Check if this is a cross-training step
    is_cross_training = keyword in CROSS_TRAINING_KEYWORDS

    return ExecutableStep(
        step_type=step_type,
        step_type_keyword=keyword,
        end_condition=end_condition,
        target=target,
        description=parsed_line.notes,
        is_cross_training=is_cross_training,
    )


def parse_workout_text(cell_content: str) -> Workout | None:
    """Parse a workout cell's text content into a Workout object.

    This handles the indentation-based syntax for nested repeat steps.

    Args:
        cell_content: Multi-line cell content like:
            running: 10k Speed
            - warmup: 15:00
            - repeat: 8
              - run: 2:00 @z4
              - recover: 1:30 @z1
            - cooldown: 15:00

    Returns:
        Workout object or None if parsing fails
    """
    if not cell_content or not cell_content.strip():
        return None

    lines = cell_content.strip().split("\n")
    if not lines:
        return None

    # First line is the workout header: "running: Workout Name"
    header_line = lines[0].strip()
    if ":" not in header_line:
        logger.warning(f"Invalid workout header (no colon): {header_line}")
        return None

    workout_type, workout_name = header_line.split(":", 1)
    workout_type = workout_type.strip().lower()
    workout_name = workout_name.strip()

    # Only support running workouts
    if workout_type != "running":
        logger.warning(f"Unsupported workout type: {workout_type}. Only 'running' is supported.")
        return None

    if not workout_name:
        workout_name = "Workout"

    # Parse the step lines
    step_lines = lines[1:]
    parsed_lines = []
    for line in step_lines:
        parsed = parse_line(line)
        if parsed:
            parsed_lines.append(parsed)

    if not parsed_lines:
        logger.warning(f"No valid steps found in workout: {workout_name}")
        return None

    # Build step tree using indentation
    steps = build_step_tree(parsed_lines)

    if not steps:
        logger.warning(f"Failed to build step tree for workout: {workout_name}")
        return None

    return Workout(
        name=workout_name,
        steps=steps,
    )


def build_step_tree(parsed_lines: list[ParsedLine]) -> list[WorkoutStep]:
    """Build a nested step structure from parsed lines based on indentation.

    Args:
        parsed_lines: List of ParsedLine objects

    Returns:
        List of WorkoutStep objects (ExecutableStep or RepeatStep)
    """
    if not parsed_lines:
        return []

    # Use a recursive approach with index tracking
    steps, _ = _build_steps_recursive(parsed_lines, 0, 0)
    return steps


def _build_steps_recursive(
    parsed_lines: list[ParsedLine],
    start_index: int,
    expected_indent: int,
) -> tuple[list[WorkoutStep], int]:
    """Recursively build steps at a given indentation level.

    Args:
        parsed_lines: All parsed lines
        start_index: Index to start processing from
        expected_indent: Expected indentation level for this group

    Returns:
        Tuple of (list of steps, next index to process)
    """
    steps: list[WorkoutStep] = []
    i = start_index

    while i < len(parsed_lines):
        line = parsed_lines[i]

        # If we hit a lower indent level, we're done with this group
        if line.indent_level < expected_indent:
            break

        # If indent is higher than expected, something is wrong
        if line.indent_level > expected_indent:
            logger.warning(
                f"Unexpected indentation at line {i}: expected {expected_indent}, got {line.indent_level}"
            )
            i += 1
            continue

        # Handle note lines - attach to previous step
        if line.keyword == "note":
            if steps:
                last_step = steps[-1]
                note_text = line.value.strip()
                # Remove surrounding quotes if present
                if note_text.startswith('"') and note_text.endswith('"') or note_text.startswith("'") and note_text.endswith("'"):
                    note_text = note_text[1:-1]

                if isinstance(last_step, ExecutableStep):
                    # Append to existing description or set new one
                    if last_step.description:
                        last_step.description = f"{last_step.description}\n{note_text}"
                    else:
                        last_step.description = note_text
                    logger.debug(f"Attached note to step: {note_text}")
                elif isinstance(last_step, RepeatStep):
                    # For repeat steps, attach note to the last nested step
                    if last_step.steps:
                        nested_last = last_step.steps[-1]
                        if isinstance(nested_last, ExecutableStep):
                            if nested_last.description:
                                nested_last.description = f"{nested_last.description}\n{note_text}"
                            else:
                                nested_last.description = note_text
                            logger.debug(f"Attached note to nested step: {note_text}")
            else:
                logger.warning(f"Note with no preceding step: {line.value}")
            i += 1
            continue

        # Handle repeat steps
        if line.keyword == "repeat":
            try:
                iterations = int(line.value.strip())
            except ValueError:
                logger.warning(f"Invalid repeat count: {line.value}")
                i += 1
                continue

            # Get nested steps at next indent level
            nested_steps, next_i = _build_steps_recursive(
                parsed_lines, i + 1, expected_indent + 1
            )

            if nested_steps:
                repeat_step = RepeatStep(iterations=iterations, steps=nested_steps)
                steps.append(repeat_step)

            i = next_i

        else:
            # Regular executable step
            step = parse_step(line)
            if step:
                steps.append(step)
            i += 1

    return steps, i


def parse_training_plan(
    csv_path: str | Path,
    start_date: date,
) -> list[tuple[date, Workout]]:
    """Parse a CSV training plan file.

    The CSV should have columns: WEEK, Monday, Tuesday, Wednesday, Thursday,
    Friday, Saturday, Sunday.

    Args:
        csv_path: Path to the CSV file
        start_date: The date for Week 1, Monday

    Returns:
        List of (date, Workout) tuples for all non-empty workout cells

    Raises:
        ParserError: If CSV format is invalid
        FileNotFoundError: If CSV file doesn't exist
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info(f"Parsing training plan from: {csv_path}")

    # Read CSV
    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    except Exception as e:
        raise ParserError(f"Failed to read CSV: {e}") from e

    # Normalize column names (strip whitespace, handle case variations)
    df.columns = df.columns.str.strip()

    # Check for required columns
    # WEEK column is optional - if not present, assume sequential weeks
    has_week_col = "WEEK" in df.columns or "Week" in df.columns

    # Map day columns (case-insensitive)
    day_col_map = {}
    for col in df.columns:
        col_lower = col.lower()
        for day in DAY_COLUMNS:
            if col_lower == day.lower():
                day_col_map[day] = col
                break

    if not day_col_map:
        raise ParserError(
            f"No day columns found. Expected some of: {DAY_COLUMNS}. Got: {list(df.columns)}"
        )

    logger.info(f"Found day columns: {list(day_col_map.keys())}")

    # Parse workouts
    result: list[tuple[date, Workout]] = []

    # Pre-compile day column map to avoid repeated lookups
    day_indices = {day_name: day_idx for day_idx, day_name in enumerate(DAY_COLUMNS) if day_name in day_col_map}

    for row_idx, row in df.iterrows():
        # Determine week number
        if has_week_col:
            week_col = "WEEK" if "WEEK" in df.columns else "Week"
            try:
                week_num = int(row[week_col])
            except (ValueError, TypeError):
                logger.warning(f"Invalid week number at row {row_idx}: {row.get(week_col)}")
                week_num = int(row_idx) + 1  # type: ignore
        else:
            week_num = int(row_idx) + 1  # type: ignore

        # Calculate base date for this week (Week 1 = start_date)
        week_offset = week_num - 1
        week_start = start_date + timedelta(weeks=week_offset)

        # Process each day column
        for day_name, day_idx in day_indices.items():
            col_name = day_col_map[day_name]
            cell_content = str(row.get(col_name, "")).strip()

            if not cell_content:
                continue

            # Calculate date for this cell
            workout_date = week_start + timedelta(days=day_idx)

            # Parse workout
            try:
                workout = parse_workout_text(cell_content)
                if workout:
                    result.append((workout_date, workout))
                    logger.debug(f"Parsed workout: {workout.name} for {workout_date}")
            except Exception as e:
                logger.error(
                    f"Failed to parse workout at Week {week_num}, {day_name}: {e}"
                )
                continue

    logger.info(f"Parsed {len(result)} workouts from training plan")
    return result
