"""Data models for the workout builder."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# User config directory
CONFIG_DIR = Path.home() / ".config" / "garmin-plan-uploader"
TEMPLATES_FILE = CONFIG_DIR / "templates.json"


class StepType(Enum):
    """Workout step types."""
    WARMUP = "warmup"
    RUN = "run"
    RECOVER = "recover"
    COOLDOWN = "cooldown"
    REST = "rest"
    REPEAT = "repeat"


class DurationType(Enum):
    """Duration/distance types."""
    TIME = "time"  # mm:ss format
    KILOMETERS = "km"
    MILES = "mi"
    METERS = "m"
    LAP_BUTTON = "lap-button"


class TargetType(Enum):
    """Target types for steps."""
    NONE = "none"
    HR_ZONE = "hr_zone"
    PACE = "pace"


@dataclass
class Duration:
    """Represents a step duration or distance."""
    type: DurationType
    value: str  # "5:00" for time, "5" for distance

    def to_csv(self) -> str:
        """Convert to CSV format."""
        if self.type == DurationType.TIME:
            return self.value
        elif self.type == DurationType.LAP_BUTTON:
            return "lap-button"
        else:
            return f"{self.value}{self.type.value}"

    @classmethod
    def from_dict(cls, data: dict) -> Duration:
        return cls(
            type=DurationType(data["type"]),
            value=data["value"],
        )

    def to_dict(self) -> dict:
        return {"type": self.type.value, "value": self.value}


@dataclass
class Target:
    """Represents a step target (HR zone or pace)."""
    type: TargetType
    hr_zone: int | None = None  # 1-5
    pace_min: str | None = None  # "5:00" (slower)
    pace_max: str | None = None  # "4:30" (faster)
    pace_unit: str = "mpk"  # "mpk" or "mpm"

    def to_csv(self) -> str:
        """Convert to CSV format."""
        if self.type == TargetType.NONE:
            return ""
        elif self.type == TargetType.HR_ZONE:
            return f"@z{self.hr_zone}"
        elif self.type == TargetType.PACE:
            unit_suffix = "" if self.pace_unit == "mpk" else "mpm"
            return f"@{self.pace_min}-{self.pace_max}{unit_suffix}"
        return ""

    @classmethod
    def from_dict(cls, data: dict) -> Target:
        return cls(
            type=TargetType(data["type"]),
            hr_zone=data.get("hr_zone"),
            pace_min=data.get("pace_min"),
            pace_max=data.get("pace_max"),
            pace_unit=data.get("pace_unit", "mpk"),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "hr_zone": self.hr_zone,
            "pace_min": self.pace_min,
            "pace_max": self.pace_max,
            "pace_unit": self.pace_unit,
        }


@dataclass
class BuilderStep:
    """A single workout step in the builder."""
    step_type: StepType
    duration: Duration | None = None
    target: Target = field(default_factory=lambda: Target(TargetType.NONE))
    note: str = ""
    # For repeat steps
    iterations: int = 1
    nested_steps: list[BuilderStep] = field(default_factory=list)

    def to_csv_lines(self, indent: int = 0) -> list[str]:
        """Convert to CSV format lines."""
        lines = []
        prefix = "  " * indent + "- "

        if self.step_type == StepType.REPEAT:
            lines.append(f"{prefix}repeat: {self.iterations}")
            for nested in self.nested_steps:
                lines.extend(nested.to_csv_lines(indent + 1))
        else:
            duration_str = self.duration.to_csv() if self.duration else ""
            target_str = self.target.to_csv()

            step_line = f"{prefix}{self.step_type.value}: {duration_str}"
            if target_str:
                step_line += f" {target_str}"
            if self.note:
                step_line += f"; {self.note}"
            lines.append(step_line)

        return lines

    @classmethod
    def from_dict(cls, data: dict) -> BuilderStep:
        nested = [cls.from_dict(s) for s in data.get("nested_steps", [])]
        return cls(
            step_type=StepType(data["step_type"]),
            duration=Duration.from_dict(data["duration"]) if data.get("duration") else None,
            target=Target.from_dict(data["target"]) if data.get("target") else Target(TargetType.NONE),
            note=data.get("note", ""),
            iterations=data.get("iterations", 1),
            nested_steps=nested,
        )

    def to_dict(self) -> dict:
        return {
            "step_type": self.step_type.value,
            "duration": self.duration.to_dict() if self.duration else None,
            "target": self.target.to_dict(),
            "note": self.note,
            "iterations": self.iterations,
            "nested_steps": [s.to_dict() for s in self.nested_steps],
        }

    def copy(self) -> BuilderStep:
        """Create a deep copy."""
        return BuilderStep.from_dict(self.to_dict())


@dataclass
class BuilderWorkout:
    """A workout in the builder."""
    name: str
    steps: list[BuilderStep] = field(default_factory=list)
    sport_type: str = "running"

    def to_csv_cell(self) -> str:
        """Convert to CSV cell content."""
        lines = [f"{self.sport_type}: {self.name}"]
        for step in self.steps:
            lines.extend(step.to_csv_lines())
        return "\n".join(lines)

    def is_empty(self) -> bool:
        """Check if workout has no steps."""
        return len(self.steps) == 0

    @classmethod
    def from_dict(cls, data: dict) -> BuilderWorkout:
        steps = [BuilderStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            name=data["name"],
            steps=steps,
            sport_type=data.get("sport_type", "running"),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "sport_type": self.sport_type,
        }

    def copy(self) -> BuilderWorkout:
        """Create a deep copy."""
        return BuilderWorkout.from_dict(self.to_dict())


@dataclass
class WorkoutTemplateData:
    """A saved workout template."""
    name: str
    workout: BuilderWorkout
    tags: list[str] = field(default_factory=list)
    is_builtin: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> WorkoutTemplateData:
        return cls(
            name=data["name"],
            workout=BuilderWorkout.from_dict(data["workout"]),
            tags=data.get("tags", []),
            is_builtin=data.get("is_builtin", False),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "workout": self.workout.to_dict(),
            "tags": self.tags,
            "is_builtin": self.is_builtin,
        }


class TemplateStore:
    """Manages user workout templates."""

    def __init__(self):
        self._user_templates: list[WorkoutTemplateData] = []
        self._builtin_templates: list[WorkoutTemplateData] = self._create_builtins()
        self._load_user_templates()

    def _create_builtins(self) -> list[WorkoutTemplateData]:
        """Create built-in workout templates."""
        builtins = []

        # Easy Run
        easy_run = BuilderWorkout(
            name="Easy Run",
            steps=[
                BuilderStep(
                    step_type=StepType.RUN,
                    duration=Duration(DurationType.TIME, "45:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Easy Run", easy_run, ["base", "recovery"], True))

        # Recovery Run
        recovery = BuilderWorkout(
            name="Recovery Run",
            steps=[
                BuilderStep(
                    step_type=StepType.RUN,
                    duration=Duration(DurationType.TIME, "30:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                    note="Very easy. Conversational pace.",
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Recovery Run", recovery, ["recovery"], True))

        # Interval Workout
        intervals = BuilderWorkout(
            name="Interval Workout",
            steps=[
                BuilderStep(
                    step_type=StepType.WARMUP,
                    duration=Duration(DurationType.TIME, "15:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
                BuilderStep(
                    step_type=StepType.REPEAT,
                    iterations=6,
                    nested_steps=[
                        BuilderStep(
                            step_type=StepType.RUN,
                            duration=Duration(DurationType.TIME, "3:00"),
                            target=Target(TargetType.HR_ZONE, hr_zone=4),
                        ),
                        BuilderStep(
                            step_type=StepType.RECOVER,
                            duration=Duration(DurationType.TIME, "2:00"),
                            target=Target(TargetType.HR_ZONE, hr_zone=1),
                        ),
                    ],
                ),
                BuilderStep(
                    step_type=StepType.COOLDOWN,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Interval Workout", intervals, ["speed", "threshold"], True))

        # Tempo Run
        tempo = BuilderWorkout(
            name="Tempo Run",
            steps=[
                BuilderStep(
                    step_type=StepType.WARMUP,
                    duration=Duration(DurationType.TIME, "15:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
                BuilderStep(
                    step_type=StepType.RUN,
                    duration=Duration(DurationType.TIME, "20:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=3),
                    note="Comfortably hard. You can speak in short sentences.",
                ),
                BuilderStep(
                    step_type=StepType.COOLDOWN,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Tempo Run", tempo, ["threshold"], True))

        # Long Run
        long_run = BuilderWorkout(
            name="Long Run",
            steps=[
                BuilderStep(
                    step_type=StepType.RUN,
                    duration=Duration(DurationType.TIME, "90:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                    note="Steady effort. Stay fueled and hydrated.",
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Long Run", long_run, ["endurance"], True))

        # Hill Repeats
        hills = BuilderWorkout(
            name="Hill Repeats",
            steps=[
                BuilderStep(
                    step_type=StepType.WARMUP,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
                BuilderStep(
                    step_type=StepType.REPEAT,
                    iterations=8,
                    nested_steps=[
                        BuilderStep(
                            step_type=StepType.RUN,
                            duration=Duration(DurationType.TIME, "1:30"),
                            target=Target(TargetType.HR_ZONE, hr_zone=4),
                            note="6-8% incline. Power up!",
                        ),
                        BuilderStep(
                            step_type=StepType.RECOVER,
                            duration=Duration(DurationType.TIME, "2:00"),
                            target=Target(TargetType.HR_ZONE, hr_zone=1),
                            note="Jog back down.",
                        ),
                    ],
                ),
                BuilderStep(
                    step_type=StepType.COOLDOWN,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Hill Repeats", hills, ["strength", "hills"], True))

        # VO2 Max Intervals
        vo2max = BuilderWorkout(
            name="VO2 Max Intervals",
            steps=[
                BuilderStep(
                    step_type=StepType.WARMUP,
                    duration=Duration(DurationType.TIME, "15:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
                BuilderStep(
                    step_type=StepType.REPEAT,
                    iterations=5,
                    nested_steps=[
                        BuilderStep(
                            step_type=StepType.RUN,
                            duration=Duration(DurationType.TIME, "3:00"),
                            target=Target(TargetType.HR_ZONE, hr_zone=5),
                            note="Hard! Near max effort.",
                        ),
                        BuilderStep(
                            step_type=StepType.RECOVER,
                            duration=Duration(DurationType.TIME, "3:00"),
                            target=Target(TargetType.HR_ZONE, hr_zone=1),
                        ),
                    ],
                ),
                BuilderStep(
                    step_type=StepType.COOLDOWN,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("VO2 Max Intervals", vo2max, ["speed", "vo2max"], True))

        # Fartlek
        fartlek = BuilderWorkout(
            name="Fartlek",
            steps=[
                BuilderStep(
                    step_type=StepType.WARMUP,
                    duration=Duration(DurationType.TIME, "10:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                ),
                BuilderStep(
                    step_type=StepType.RUN,
                    duration=Duration(DurationType.TIME, "30:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=2),
                    note="Include 8-10 pickups of 30-60s by feel.",
                ),
                BuilderStep(
                    step_type=StepType.COOLDOWN,
                    duration=Duration(DurationType.TIME, "5:00"),
                    target=Target(TargetType.HR_ZONE, hr_zone=1),
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Fartlek", fartlek, ["speed", "fun"], True))

        # Strides (add-on)
        strides = BuilderWorkout(
            name="Strides",
            steps=[
                BuilderStep(
                    step_type=StepType.REPEAT,
                    iterations=5,
                    nested_steps=[
                        BuilderStep(
                            step_type=StepType.RUN,
                            duration=Duration(DurationType.TIME, "0:20"),
                            target=Target(TargetType.HR_ZONE, hr_zone=5),
                        ),
                        BuilderStep(
                            step_type=StepType.RECOVER,
                            duration=Duration(DurationType.TIME, "1:30"),
                            target=Target(TargetType.HR_ZONE, hr_zone=1),
                        ),
                    ],
                ),
            ],
        )
        builtins.append(WorkoutTemplateData("Strides", strides, ["speed", "addon"], True))

        return builtins

    def _load_user_templates(self) -> None:
        """Load user templates from disk."""
        if not TEMPLATES_FILE.exists():
            return

        try:
            with open(TEMPLATES_FILE) as f:
                data = json.load(f)
            self._user_templates = [
                WorkoutTemplateData.from_dict(t) for t in data.get("templates", [])
            ]
            logger.info(f"Loaded {len(self._user_templates)} user templates")
        except Exception as e:
            logger.error(f"Failed to load user templates: {e}")

    def _save_user_templates(self) -> None:
        """Save user templates to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = {"templates": [t.to_dict() for t in self._user_templates]}
            with open(TEMPLATES_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self._user_templates)} user templates")
        except Exception as e:
            logger.error(f"Failed to save user templates: {e}")

    def get_all_templates(self) -> list[WorkoutTemplateData]:
        """Get all templates (builtin + user)."""
        return self._builtin_templates + self._user_templates

    def get_builtin_templates(self) -> list[WorkoutTemplateData]:
        """Get built-in templates."""
        return self._builtin_templates.copy()

    def get_user_templates(self) -> list[WorkoutTemplateData]:
        """Get user templates."""
        return self._user_templates.copy()

    def save_template(self, template: WorkoutTemplateData) -> None:
        """Save a user template."""
        # Check for duplicate name
        for i, t in enumerate(self._user_templates):
            if t.name == template.name:
                self._user_templates[i] = template
                self._save_user_templates()
                return

        self._user_templates.append(template)
        self._save_user_templates()

    def delete_template(self, name: str) -> bool:
        """Delete a user template by name."""
        for i, t in enumerate(self._user_templates):
            if t.name == name:
                del self._user_templates[i]
                self._save_user_templates()
                return True
        return False

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """Rename a user template."""
        for t in self._user_templates:
            if t.name == old_name:
                t.name = new_name
                t.workout.name = new_name
                self._save_user_templates()
                return True
        return False
