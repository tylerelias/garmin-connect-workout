"""Tests for CSV parser."""

from datetime import date

import pytest
from garmin_plan_uploader.csv_parser import (
    ParsedLine,
    get_indent_level,
    parse_line,
    parse_target,
    parse_end_condition_and_target,
    parse_workout_text,
    build_step_tree,
)
from garmin_plan_uploader.domain_models import (
    ExecutableStep,
    HeartRateZoneTarget,
    NoTarget,
    PaceTarget,
    RepeatStep,
    StepType,
    TimeEndCondition,
    LapButtonEndCondition,
)


class TestGetIndentLevel:
    """Tests for indentation level detection."""

    def test_no_indent(self):
        assert get_indent_level("- warmup: 15:00") == 0

    def test_one_level_indent(self):
        assert get_indent_level("  - run: 2:00") == 1

    def test_two_level_indent(self):
        assert get_indent_level("    - run: 2:00") == 2


class TestParseLine:
    """Tests for line parsing."""

    def test_simple_step(self):
        result = parse_line("- warmup: 15:00")
        assert result is not None
        assert result.indent_level == 0
        assert result.keyword == "warmup"
        assert result.value == "15:00"
        assert result.notes is None

    def test_step_with_target(self):
        result = parse_line("- run: 2:00 @z4")
        assert result is not None
        assert result.keyword == "run"
        assert result.value == "2:00 @z4"

    def test_step_with_notes(self):
        result = parse_line("- run: 30:00; Keep it easy")
        assert result is not None
        assert result.keyword == "run"
        assert result.value == "30:00"
        assert result.notes == "Keep it easy"

    def test_indented_step(self):
        result = parse_line("  - run: 2:00 @z4")
        assert result is not None
        assert result.indent_level == 1
        assert result.keyword == "run"

    def test_empty_line(self):
        assert parse_line("") is None
        assert parse_line("   ") is None


class TestParseTarget:
    """Tests for target parsing."""

    def test_hr_zone(self):
        target = parse_target("z2")
        assert isinstance(target, HeartRateZoneTarget)
        assert target.zone == 2

    def test_pace_range(self):
        target = parse_target("5:00-4:30")
        assert isinstance(target, PaceTarget)
        assert target.min_speed_mps > 0
        assert target.max_speed_mps > target.min_speed_mps

    def test_unknown_target(self):
        target = parse_target("unknown")
        assert isinstance(target, NoTarget)


class TestParseEndConditionAndTarget:
    """Tests for combined end condition and target parsing."""

    def test_time_with_target(self):
        end_cond, target = parse_end_condition_and_target("15:00 @z2")
        assert isinstance(end_cond, TimeEndCondition)
        assert end_cond.duration_seconds == 900
        assert isinstance(target, HeartRateZoneTarget)
        assert target.zone == 2

    def test_lap_button(self):
        end_cond, target = parse_end_condition_and_target("lap-button")
        assert isinstance(end_cond, LapButtonEndCondition)
        assert isinstance(target, NoTarget)

    def test_time_no_target(self):
        end_cond, target = parse_end_condition_and_target("20:00")
        assert isinstance(end_cond, TimeEndCondition)
        assert end_cond.duration_seconds == 1200
        assert isinstance(target, NoTarget)


class TestParseWorkoutText:
    """Tests for full workout text parsing."""

    def test_simple_workout(self):
        text = """running: Easy Run
- warmup: 10:00
- run: 30:00 @z2
- cooldown: 5:00"""

        workout = parse_workout_text(text)
        assert workout is not None
        assert workout.name == "Easy Run"
        assert len(workout.steps) == 3

    def test_workout_with_repeat(self):
        text = """running: Intervals
- warmup: 15:00
- repeat: 8
  - run: 2:00 @z4
  - recover: 1:30 @z1
- cooldown: 15:00"""

        workout = parse_workout_text(text)
        assert workout is not None
        assert workout.name == "Intervals"
        assert len(workout.steps) == 3

        # Check repeat step
        repeat_step = workout.steps[1]
        assert isinstance(repeat_step, RepeatStep)
        assert repeat_step.iterations == 8
        assert len(repeat_step.steps) == 2

    def test_non_running_workout_ignored(self):
        text = """cycling: Bike Ride
- warmup: 10:00
- bike: 60:00"""

        workout = parse_workout_text(text)
        assert workout is None

    def test_empty_workout(self):
        assert parse_workout_text("") is None
        assert parse_workout_text("   ") is None


class TestBuildStepTree:
    """Tests for step tree building."""

    def test_flat_steps(self):
        lines = [
            ParsedLine(indent_level=0, keyword="warmup", value="10:00", notes=None),
            ParsedLine(indent_level=0, keyword="run", value="20:00", notes=None),
            ParsedLine(indent_level=0, keyword="cooldown", value="5:00", notes=None),
        ]
        steps = build_step_tree(lines)

        assert len(steps) == 3
        assert all(isinstance(s, ExecutableStep) for s in steps)

    def test_nested_repeat(self):
        lines = [
            ParsedLine(indent_level=0, keyword="repeat", value="4", notes=None),
            ParsedLine(indent_level=1, keyword="run", value="2:00", notes=None),
            ParsedLine(indent_level=1, keyword="recover", value="1:00", notes=None),
        ]
        steps = build_step_tree(lines)

        assert len(steps) == 1
        assert isinstance(steps[0], RepeatStep)
        assert steps[0].iterations == 4
        assert len(steps[0].steps) == 2
