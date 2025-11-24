"""Tests for domain models."""

import pytest
from garmin_plan_uploader.domain_models import (
    EndConditionType,
    ExecutableStep,
    HeartRateZoneTarget,
    LapButtonEndCondition,
    NoTarget,
    PaceTarget,
    RepeatStep,
    StepType,
    TargetType,
    TimeEndCondition,
    DistanceEndCondition,
    Workout,
    parse_distance_to_meters,
    parse_duration_to_seconds,
    parse_hr_zone,
    parse_pace_to_meters_per_second,
)


class TestParseDuration:
    """Tests for duration parsing."""

    def test_minutes_and_seconds(self):
        assert parse_duration_to_seconds("15:00") == 900
        assert parse_duration_to_seconds("2:30") == 150
        assert parse_duration_to_seconds("0:45") == 45

    def test_extended_minutes(self):
        assert parse_duration_to_seconds("225:00") == 13500

    def test_lap_button(self):
        assert parse_duration_to_seconds("lap-button") is None
        assert parse_duration_to_seconds("LAP-BUTTON") is None

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_duration_to_seconds("invalid")
        with pytest.raises(ValueError):
            parse_duration_to_seconds("15:60")  # Invalid seconds


class TestParseDistance:
    """Tests for distance parsing."""

    def test_kilometers(self):
        assert parse_distance_to_meters("2km") == 2000.0
        assert parse_distance_to_meters("5.5km") == 5500.0

    def test_meters(self):
        assert parse_distance_to_meters("1600m") == 1600.0
        assert parse_distance_to_meters("400m") == 400.0

    def test_miles(self):
        assert abs(parse_distance_to_meters("1mi") - 1609.344) < 0.01
        assert abs(parse_distance_to_meters("3mi") - 4828.032) < 0.01

    def test_yards(self):
        assert abs(parse_distance_to_meters("100yds") - 91.44) < 0.01

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_distance_to_meters("invalid")


class TestParsePace:
    """Tests for pace parsing."""

    def test_pace_range_per_km(self):
        min_speed, max_speed = parse_pace_to_meters_per_second("5:00-4:30")
        # 5:00/km = 300 sec/km = 1000/300 = 3.33 m/s
        # 4:30/km = 270 sec/km = 1000/270 = 3.70 m/s
        assert abs(min_speed - 3.333) < 0.01
        assert abs(max_speed - 3.704) < 0.01

    def test_pace_range_per_mile(self):
        min_speed, max_speed = parse_pace_to_meters_per_second("8:00-7:00mpm")
        # 8:00/mi = 480 sec/mi = 1609.344/480 = 3.35 m/s
        # 7:00/mi = 420 sec/mi = 1609.344/420 = 3.83 m/s
        assert abs(min_speed - 3.353) < 0.01
        assert abs(max_speed - 3.832) < 0.01


class TestParseHRZone:
    """Tests for heart rate zone parsing."""

    def test_valid_zones(self):
        assert parse_hr_zone("z1") == 1
        assert parse_hr_zone("z5") == 5
        assert parse_hr_zone("Z3") == 3

    def test_invalid_zone(self):
        with pytest.raises(ValueError):
            parse_hr_zone("z0")
        with pytest.raises(ValueError):
            parse_hr_zone("z6")


class TestExecutableStep:
    """Tests for ExecutableStep model."""

    def test_basic_step(self):
        step = ExecutableStep(
            step_type=StepType.WARMUP,
            step_type_keyword="warmup",
            end_condition=TimeEndCondition(duration_seconds=900),
            target=NoTarget(),
        )
        assert step.step_type == StepType.WARMUP
        assert step.is_cross_training is False

    def test_garmin_dict_warmup(self):
        step = ExecutableStep(
            step_type=StepType.WARMUP,
            step_type_keyword="warmup",
            end_condition=TimeEndCondition(duration_seconds=900),
        )
        result = step.to_garmin_dict(0)

        assert result["type"] == "ExecutableStepDTO"
        assert result["stepType"]["stepTypeId"] == 1
        assert result["stepType"]["stepTypeKey"] == "warmup"
        assert result["endCondition"]["conditionTypeId"] == EndConditionType.TIME
        assert result["endConditionValue"] == 900

    def test_cross_training_step(self):
        step = ExecutableStep(
            step_type=StepType.INTERVAL,
            step_type_keyword="other",
            end_condition=TimeEndCondition(duration_seconds=600),
            is_cross_training=True,
        )
        result = step.to_garmin_dict(0)

        assert result["description"] == "[CROSS TRAINING]"
        assert result["stepType"]["stepTypeId"] == 3  # Interval, not 6

    def test_hr_zone_target(self):
        step = ExecutableStep(
            step_type=StepType.INTERVAL,
            step_type_keyword="run",
            end_condition=TimeEndCondition(duration_seconds=120),
            target=HeartRateZoneTarget(zone=4),
        )
        result = step.to_garmin_dict(0)

        assert result["targetType"]["workoutTargetTypeId"] == TargetType.HEART_RATE_ZONE
        assert result["zoneNumber"] == 4


class TestRepeatStep:
    """Tests for RepeatStep model."""

    def test_basic_repeat(self):
        nested_steps = [
            ExecutableStep(
                step_type=StepType.INTERVAL,
                step_type_keyword="run",
                end_condition=TimeEndCondition(duration_seconds=120),
            ),
            ExecutableStep(
                step_type=StepType.RECOVER,
                step_type_keyword="recover",
                end_condition=TimeEndCondition(duration_seconds=90),
            ),
        ]
        repeat = RepeatStep(iterations=8, steps=nested_steps)

        assert repeat.iterations == 8
        assert len(repeat.steps) == 2

    def test_garmin_dict(self):
        nested_steps = [
            ExecutableStep(
                step_type=StepType.INTERVAL,
                step_type_keyword="run",
                end_condition=TimeEndCondition(duration_seconds=120),
            ),
        ]
        repeat = RepeatStep(iterations=4, steps=nested_steps)
        result = repeat.to_garmin_dict(1)

        assert result["type"] == "RepeatGroupDTO"
        assert result["numberOfIterations"] == 4
        assert result["stepType"]["stepTypeId"] == StepType.REPEAT
        assert len(result["workoutSteps"]) == 1


class TestWorkout:
    """Tests for Workout model."""

    def test_basic_workout(self):
        steps = [
            ExecutableStep(
                step_type=StepType.WARMUP,
                step_type_keyword="warmup",
                end_condition=TimeEndCondition(duration_seconds=900),
            ),
            ExecutableStep(
                step_type=StepType.COOLDOWN,
                step_type_keyword="cooldown",
                end_condition=LapButtonEndCondition(),
            ),
        ]
        workout = Workout(name="Test Workout", steps=steps)

        assert workout.name == "Test Workout"
        assert len(workout.steps) == 2

    def test_garmin_dict(self):
        steps = [
            ExecutableStep(
                step_type=StepType.WARMUP,
                step_type_keyword="warmup",
                end_condition=TimeEndCondition(duration_seconds=900),
            ),
        ]
        workout = Workout(name="10k Speed", steps=steps)
        result = workout.to_garmin_dict()

        assert result["workoutName"] == "10k Speed"
        assert result["sportType"]["sportTypeId"] == 1
        assert result["sportType"]["sportTypeKey"] == "running"
        assert len(result["workoutSegments"]) == 1
        assert len(result["workoutSegments"][0]["workoutSteps"]) == 1
