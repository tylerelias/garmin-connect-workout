"""Domain models for workout representation using Pydantic.

This module defines the data structures for representing workouts, steps,
targets, and training plans with strict validation.
"""

from __future__ import annotations

import re
from datetime import date
from enum import IntEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class StepType(IntEnum):
    """Garmin step type IDs."""

    WARMUP = 1
    COOLDOWN = 2
    INTERVAL = 3  # Used for run, interval, other (cross-training)
    RECOVER = 4
    REST = 5
    REPEAT = 6


class EndConditionType(IntEnum):
    """Garmin end condition type IDs."""

    LAP_BUTTON = 1
    TIME = 2
    DISTANCE = 3


class TargetType(IntEnum):
    """Garmin target type IDs."""

    NO_TARGET = 1
    HEART_RATE_ZONE = 4
    PACE = 6


class SportType(IntEnum):
    """Garmin sport type IDs."""

    RUNNING = 1
    CYCLING = 2
    OTHER = 3
    SWIMMING = 4


# Step type keyword mapping
STEP_TYPE_MAP: dict[str, StepType | None] = {
    "warmup": StepType.WARMUP,
    "cooldown": StepType.COOLDOWN,
    "run": StepType.INTERVAL,
    "interval": StepType.INTERVAL,
    "go": StepType.INTERVAL,
    "other": StepType.INTERVAL,  # Cross-training mapped to interval
    "stair": StepType.INTERVAL,  # Stair machine mapped to interval
    "recover": StepType.RECOVER,
    "recovery": StepType.RECOVER,
    "rest": StepType.REST,
    "repeat": StepType.REPEAT,
    "note": None,  # Notes are metadata, not actual steps
}

# Keywords that should be marked as cross-training
CROSS_TRAINING_KEYWORDS = {"other", "stair"}


def parse_duration_to_seconds(duration_str: str) -> int | None:
    """Parse duration string (mm:ss or mmm:ss) to seconds.

    Args:
        duration_str: Duration in format "mm:ss" or "mmm:ss" (e.g., "15:00", "225:00")

    Returns:
        Duration in seconds, or None if lap-button

    Raises:
        ValueError: If duration format is invalid
    """
    if duration_str.lower() == "lap-button":
        return None

    match = re.match(r"^(\d{1,3}):(\d{2})$", duration_str.strip())
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}. Expected mm:ss or mmm:ss")

    minutes = int(match.group(1))
    seconds = int(match.group(2))

    if seconds >= 60:
        raise ValueError(f"Invalid seconds value: {seconds}. Must be < 60")

    return minutes * 60 + seconds


def parse_distance_to_meters(distance_str: str) -> float:
    """Parse distance string to meters.

    Args:
        distance_str: Distance with unit (e.g., "2km", "5mi", "1600m", "100yds")

    Returns:
        Distance in meters

    Raises:
        ValueError: If distance format is invalid
    """
    distance_str = distance_str.strip().lower()

    # Match number (possibly decimal) followed by unit
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(km|mi|m|yds|yd|meters|miles|kilometers)$", distance_str)
    if not match:
        raise ValueError(f"Invalid distance format: {distance_str}")

    value = float(match.group(1))
    unit = match.group(2)

    # Convert to meters
    conversions = {
        "m": 1.0,
        "meters": 1.0,
        "km": 1000.0,
        "kilometers": 1000.0,
        "mi": 1609.344,
        "miles": 1609.344,
        "yd": 0.9144,
        "yds": 0.9144,
    }

    return value * conversions[unit]


def parse_pace_to_meters_per_second(pace_str: str) -> tuple[float, float]:
    """Parse pace string to meters per second range.

    Args:
        pace_str: Pace in format "mm:ss-mm:ss" optionally with "mpk" or "mpm" suffix
                  Default is minutes per kilometer if no suffix

    Returns:
        Tuple of (min_speed_mps, max_speed_mps) - note: slower pace = lower speed

    Raises:
        ValueError: If pace format is invalid
    """
    pace_str = pace_str.strip().lower()

    # Check for unit suffix
    is_per_mile = pace_str.endswith("mpm")
    if is_per_mile:
        pace_str = pace_str[:-3].strip()
    elif pace_str.endswith("mpk"):
        pace_str = pace_str[:-3].strip()

    # Match pace range: mm:ss-mm:ss
    match = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", pace_str)
    if not match:
        raise ValueError(f"Invalid pace format: {pace_str}. Expected mm:ss-mm:ss")

    # Parse slow pace (higher number = slower)
    slow_min = int(match.group(1))
    slow_sec = int(match.group(2))
    slow_total_sec = slow_min * 60 + slow_sec

    # Parse fast pace (lower number = faster)
    fast_min = int(match.group(3))
    fast_sec = int(match.group(4))
    fast_total_sec = fast_min * 60 + fast_sec

    # Distance per pace unit
    distance_per_unit = 1609.344 if is_per_mile else 1000.0  # meters

    # Convert pace (time per distance) to speed (distance per time)
    # Slower pace = lower speed, faster pace = higher speed
    if slow_total_sec > 0:
        min_speed_mps = distance_per_unit / slow_total_sec
    else:
        min_speed_mps = 0.0

    if fast_total_sec > 0:
        max_speed_mps = distance_per_unit / fast_total_sec
    else:
        max_speed_mps = 0.0

    return (min_speed_mps, max_speed_mps)


def parse_hr_zone(zone_str: str) -> int:
    """Parse heart rate zone string.

    Args:
        zone_str: Zone in format "z1" through "z5"

    Returns:
        Zone number (1-5)

    Raises:
        ValueError: If zone format is invalid
    """
    zone_str = zone_str.strip().lower()

    match = re.match(r"^z([1-5])$", zone_str)
    if not match:
        raise ValueError(f"Invalid HR zone: {zone_str}. Expected z1-z5")

    return int(match.group(1))


class NoTarget(BaseModel):
    """No target specified for step."""

    type: Literal["no_target"] = "no_target"

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.NO_TARGET,
                "workoutTargetTypeKey": "no.target",
            }
        }


class HeartRateZoneTarget(BaseModel):
    """Heart rate zone target."""

    type: Literal["hr_zone"] = "hr_zone"
    zone: int = Field(ge=1, le=5)

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
                "workoutTargetTypeKey": "heart.rate.zone",
            },
            "zoneNumber": self.zone,
        }


class PaceTarget(BaseModel):
    """Pace target with min/max speed."""

    type: Literal["pace"] = "pace"
    min_speed_mps: float = Field(gt=0, description="Minimum speed in meters per second")
    max_speed_mps: float = Field(gt=0, description="Maximum speed in meters per second")

    @model_validator(mode="after")
    def validate_speed_range(self) -> "PaceTarget":
        """Ensure min <= max speed."""
        if self.min_speed_mps > self.max_speed_mps:
            # Swap if in wrong order
            self.min_speed_mps, self.max_speed_mps = self.max_speed_mps, self.min_speed_mps
        return self

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.PACE,
                "workoutTargetTypeKey": "pace.zone",
            },
            "targetValueOne": self.min_speed_mps,
            "targetValueTwo": self.max_speed_mps,
        }


Target = Annotated[
    Union[NoTarget, HeartRateZoneTarget, PaceTarget],
    Field(discriminator="type"),
]


class TimeEndCondition(BaseModel):
    """End condition based on time duration."""

    type: Literal["time"] = "time"
    duration_seconds: int = Field(gt=0)

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "endCondition": {
                "conditionTypeKey": "time",
                "conditionTypeId": EndConditionType.TIME,
            },
            "endConditionValue": self.duration_seconds,
            "preferredEndConditionUnit": {"unitKey": "second"},
        }


class DistanceEndCondition(BaseModel):
    """End condition based on distance."""

    type: Literal["distance"] = "distance"
    distance_meters: float = Field(gt=0)

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "endCondition": {
                "conditionTypeKey": "distance",
                "conditionTypeId": EndConditionType.DISTANCE,
            },
            "endConditionValue": self.distance_meters,
            "preferredEndConditionUnit": {"unitKey": "meter"},
        }


class LapButtonEndCondition(BaseModel):
    """End condition based on lap button press."""

    type: Literal["lap_button"] = "lap_button"

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API format."""
        return {
            "endCondition": {
                "conditionTypeKey": "lap.button",
                "conditionTypeId": EndConditionType.LAP_BUTTON,
            },
            "endConditionValue": None,
        }


EndCondition = Annotated[
    Union[TimeEndCondition, DistanceEndCondition, LapButtonEndCondition],
    Field(discriminator="type"),
]


class ExecutableStep(BaseModel):
    """A single executable workout step (warmup, run, recover, cooldown, etc.)."""

    step_type: StepType
    step_type_keyword: str = Field(description="Original keyword from CSV (e.g., 'warmup', 'run')")
    end_condition: EndCondition
    target: Target = Field(default_factory=NoTarget)
    description: str | None = None
    is_cross_training: bool = False

    @field_validator("step_type_keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        """Ensure keyword is lowercase."""
        return v.lower().strip()

    def to_garmin_dict(self, step_order: int) -> dict:
        """Convert to Garmin API format.

        Args:
            step_order: The order of this step in the workout (0-indexed)

        Returns:
            Dictionary in Garmin ExecutableStepDTO format
        """
        # Map step type to Garmin key
        step_type_keys = {
            StepType.WARMUP: "warmup",
            StepType.COOLDOWN: "cooldown",
            StepType.INTERVAL: "interval",
            StepType.RECOVER: "recovery",
            StepType.REST: "rest",
        }

        # Build description with cross-training prefix if needed
        description = self.description or ""
        if self.is_cross_training:
            if description:
                description = f"[CROSS TRAINING] {description}"
            else:
                description = "[CROSS TRAINING]"

        result = {
            "type": "ExecutableStepDTO",
            "stepId": None,
            "stepOrder": step_order,
            "childStepId": None,
            "description": description if description else None,
            "stepType": {
                "stepTypeId": self.step_type,
                "stepTypeKey": step_type_keys.get(self.step_type, "interval"),
            },
        }

        # Add end condition
        result.update(self.end_condition.to_garmin_dict())

        # Add target
        result.update(self.target.to_garmin_dict())

        return result


class RepeatStep(BaseModel):
    """A repeat group containing nested steps."""

    step_type: Literal[StepType.REPEAT] = StepType.REPEAT
    iterations: int = Field(ge=1)
    steps: list[Union["ExecutableStep", "RepeatStep"]] = Field(min_length=1)

    def to_garmin_dict(self, step_order: int) -> dict:
        """Convert to Garmin API format.

        Args:
            step_order: The order of this step in the workout (0-indexed)

        Returns:
            Dictionary in Garmin RepeatGroupDTO format
        """
        # Build nested steps
        nested_steps = []
        for i, step in enumerate(self.steps):
            nested_steps.append(step.to_garmin_dict(i))

        return {
            "type": "RepeatGroupDTO",
            "stepId": None,
            "stepOrder": step_order,
            "childStepId": None,
            "numberOfIterations": self.iterations,
            "stepType": {
                "stepTypeId": StepType.REPEAT,
                "stepTypeKey": "repeat",
            },
            "workoutSteps": nested_steps,
        }


# Update forward reference
RepeatStep.model_rebuild()

WorkoutStep = Union[ExecutableStep, RepeatStep]


class Workout(BaseModel):
    """A complete workout with metadata and steps."""

    name: str = Field(min_length=1, max_length=255)
    sport_type: SportType = SportType.RUNNING
    steps: list[WorkoutStep] = Field(min_length=1)
    description: str | None = None

    def to_garmin_dict(self) -> dict:
        """Convert to Garmin API workout payload format.

        Returns:
            Dictionary ready to POST to Garmin workout API
        """
        # Build steps list
        workout_steps = []
        for i, step in enumerate(self.steps):
            workout_steps.append(step.to_garmin_dict(i))

        sport_type_keys = {
            SportType.RUNNING: "running",
            SportType.CYCLING: "cycling",
            SportType.OTHER: "other",
            SportType.SWIMMING: "swimming",
        }

        return {
            "sportType": {
                "sportTypeId": self.sport_type,
                "sportTypeKey": sport_type_keys.get(self.sport_type, "running"),
            },
            "workoutName": self.name,
            "description": self.description,
            "workoutSegments": [
                {
                    "segmentOrder": 1,
                    "sportType": {
                        "sportTypeId": self.sport_type,
                        "sportTypeKey": sport_type_keys.get(self.sport_type, "running"),
                    },
                    "workoutSteps": workout_steps,
                }
            ],
        }


class DayPlan(BaseModel):
    """A workout scheduled for a specific date."""

    date: date
    workout: Workout

    def __str__(self) -> str:
        return f"{self.date.isoformat()}: {self.workout.name}"
