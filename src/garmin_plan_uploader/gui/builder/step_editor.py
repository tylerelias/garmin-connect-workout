"""Step editor widget for building workout steps."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import (
    BuilderStep,
    BuilderWorkout,
    Duration,
    DurationType,
    StepType,
    Target,
    TargetType,
)

logger = logging.getLogger(__name__)


class StepEditorWidget(QWidget):
    """Widget for editing a single workout step."""

    step_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the step editor UI."""
        layout = QFormLayout(self)
        layout.setSpacing(8)

        # Step type
        self.step_type_combo = QComboBox()
        for st in StepType:
            self.step_type_combo.addItem(st.value.capitalize(), st)
        self.step_type_combo.currentIndexChanged.connect(self._on_step_type_changed)
        layout.addRow("Step Type:", self.step_type_combo)

        # Duration section
        duration_layout = QHBoxLayout()
        self.duration_input = QLineEdit()
        self.duration_input.setPlaceholderText("e.g., 5:00 or 5")
        self.duration_input.setMaximumWidth(100)
        self.duration_input.textChanged.connect(self._emit_changed)
        duration_layout.addWidget(self.duration_input)

        self.duration_type_combo = QComboBox()
        self.duration_type_combo.addItem("Time (mm:ss)", DurationType.TIME)
        self.duration_type_combo.addItem("Kilometers", DurationType.KILOMETERS)
        self.duration_type_combo.addItem("Miles", DurationType.MILES)
        self.duration_type_combo.addItem("Meters", DurationType.METERS)
        self.duration_type_combo.addItem("Lap Button", DurationType.LAP_BUTTON)
        self.duration_type_combo.currentIndexChanged.connect(self._on_duration_type_changed)
        duration_layout.addWidget(self.duration_type_combo)
        duration_layout.addStretch()

        self.duration_widget = QWidget()
        self.duration_widget.setLayout(duration_layout)
        layout.addRow("Duration:", self.duration_widget)

        # Iterations (for repeat)
        self.iterations_spin = QSpinBox()
        self.iterations_spin.setRange(1, 99)
        self.iterations_spin.setValue(1)
        self.iterations_spin.valueChanged.connect(self._emit_changed)
        self.iterations_label = QLabel("Iterations:")
        layout.addRow(self.iterations_label, self.iterations_spin)

        # Target section
        target_group = QGroupBox("Target")
        target_layout = QVBoxLayout(target_group)

        # Target type radio buttons
        target_type_layout = QHBoxLayout()
        self.target_button_group = QButtonGroup(self)

        self.target_none_radio = QRadioButton("None")
        self.target_none_radio.setChecked(True)
        self.target_button_group.addButton(self.target_none_radio, 0)
        target_type_layout.addWidget(self.target_none_radio)

        self.target_hr_radio = QRadioButton("HR Zone")
        self.target_button_group.addButton(self.target_hr_radio, 1)
        target_type_layout.addWidget(self.target_hr_radio)

        self.target_pace_radio = QRadioButton("Pace")
        self.target_button_group.addButton(self.target_pace_radio, 2)
        target_type_layout.addWidget(self.target_pace_radio)

        target_type_layout.addStretch()
        target_layout.addLayout(target_type_layout)

        self.target_button_group.buttonClicked.connect(self._on_target_type_changed)

        # HR Zone selector
        hr_layout = QHBoxLayout()
        hr_layout.addWidget(QLabel("Zone:"))
        self.hr_zone_combo = QComboBox()
        for i in range(1, 6):
            self.hr_zone_combo.addItem(f"Zone {i}", i)
        self.hr_zone_combo.currentIndexChanged.connect(self._emit_changed)
        hr_layout.addWidget(self.hr_zone_combo)
        hr_layout.addStretch()

        self.hr_widget = QWidget()
        self.hr_widget.setLayout(hr_layout)
        target_layout.addWidget(self.hr_widget)

        # Pace range
        pace_layout = QHBoxLayout()
        pace_layout.addWidget(QLabel("Slow:"))
        self.pace_min_input = QLineEdit()
        self.pace_min_input.setPlaceholderText("5:30")
        self.pace_min_input.setMaximumWidth(60)
        self.pace_min_input.textChanged.connect(self._emit_changed)
        pace_layout.addWidget(self.pace_min_input)

        pace_layout.addWidget(QLabel("Fast:"))
        self.pace_max_input = QLineEdit()
        self.pace_max_input.setPlaceholderText("5:00")
        self.pace_max_input.setMaximumWidth(60)
        self.pace_max_input.textChanged.connect(self._emit_changed)
        pace_layout.addWidget(self.pace_max_input)

        self.pace_unit_combo = QComboBox()
        self.pace_unit_combo.addItem("min/km", "mpk")
        self.pace_unit_combo.addItem("min/mi", "mpm")
        self.pace_unit_combo.currentIndexChanged.connect(self._emit_changed)
        pace_layout.addWidget(self.pace_unit_combo)
        pace_layout.addStretch()

        self.pace_widget = QWidget()
        self.pace_widget.setLayout(pace_layout)
        target_layout.addWidget(self.pace_widget)

        layout.addRow(target_group)

        # Note
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Optional note for this step")
        self.note_input.textChanged.connect(self._emit_changed)
        layout.addRow("Note:", self.note_input)

        # Initial state
        self._on_step_type_changed()
        self._on_target_type_changed()

    def _emit_changed(self) -> None:
        """Emit step changed signal."""
        self.step_changed.emit()

    def _on_step_type_changed(self) -> None:
        """Handle step type change."""
        step_type = self.step_type_combo.currentData()
        is_repeat = step_type == StepType.REPEAT

        self.duration_widget.setVisible(not is_repeat)
        self.iterations_label.setVisible(is_repeat)
        self.iterations_spin.setVisible(is_repeat)

        self._emit_changed()

    def _on_duration_type_changed(self) -> None:
        """Handle duration type change."""
        duration_type = self.duration_type_combo.currentData()
        if duration_type == DurationType.LAP_BUTTON:
            self.duration_input.setEnabled(False)
            self.duration_input.setText("")
        else:
            self.duration_input.setEnabled(True)
            if duration_type == DurationType.TIME:
                self.duration_input.setPlaceholderText("e.g., 5:00")
            else:
                self.duration_input.setPlaceholderText("e.g., 5")

        self._emit_changed()

    def _on_target_type_changed(self) -> None:
        """Handle target type change."""
        self.hr_widget.setVisible(self.target_hr_radio.isChecked())
        self.pace_widget.setVisible(self.target_pace_radio.isChecked())
        self._emit_changed()

    def get_step(self) -> BuilderStep:
        """Get the current step configuration."""
        step_type = self.step_type_combo.currentData()

        # Duration
        duration = None
        if step_type != StepType.REPEAT:
            duration_type = self.duration_type_combo.currentData()
            if duration_type == DurationType.LAP_BUTTON:
                duration = Duration(DurationType.LAP_BUTTON, "")
            else:
                value = self.duration_input.text().strip()
                if value:
                    duration = Duration(duration_type, value)

        # Target
        if self.target_hr_radio.isChecked():
            target = Target(
                type=TargetType.HR_ZONE,
                hr_zone=self.hr_zone_combo.currentData(),
            )
        elif self.target_pace_radio.isChecked():
            target = Target(
                type=TargetType.PACE,
                pace_min=self.pace_min_input.text().strip(),
                pace_max=self.pace_max_input.text().strip(),
                pace_unit=self.pace_unit_combo.currentData(),
            )
        else:
            target = Target(type=TargetType.NONE)

        return BuilderStep(
            step_type=step_type,
            duration=duration,
            target=target,
            note=self.note_input.text().strip(),
            iterations=self.iterations_spin.value() if step_type == StepType.REPEAT else 1,
        )

    def set_step(self, step: BuilderStep) -> None:
        """Load a step into the editor."""
        # Block signals during load
        self.blockSignals(True)

        # Step type
        index = self.step_type_combo.findData(step.step_type)
        if index >= 0:
            self.step_type_combo.setCurrentIndex(index)

        # Duration
        if step.duration:
            index = self.duration_type_combo.findData(step.duration.type)
            if index >= 0:
                self.duration_type_combo.setCurrentIndex(index)
            self.duration_input.setText(step.duration.value)
        else:
            self.duration_type_combo.setCurrentIndex(0)
            self.duration_input.clear()

        # Iterations
        self.iterations_spin.setValue(step.iterations)

        # Target
        if step.target.type == TargetType.HR_ZONE:
            self.target_hr_radio.setChecked(True)
            if step.target.hr_zone:
                index = self.hr_zone_combo.findData(step.target.hr_zone)
                if index >= 0:
                    self.hr_zone_combo.setCurrentIndex(index)
        elif step.target.type == TargetType.PACE:
            self.target_pace_radio.setChecked(True)
            self.pace_min_input.setText(step.target.pace_min or "")
            self.pace_max_input.setText(step.target.pace_max or "")
            index = self.pace_unit_combo.findData(step.target.pace_unit)
            if index >= 0:
                self.pace_unit_combo.setCurrentIndex(index)
        else:
            self.target_none_radio.setChecked(True)

        # Note
        self.note_input.setText(step.note)

        self.blockSignals(False)
        self._on_step_type_changed()
        self._on_target_type_changed()

    def clear(self) -> None:
        """Clear the editor."""
        self.step_type_combo.setCurrentIndex(0)
        self.duration_input.clear()
        self.duration_type_combo.setCurrentIndex(0)
        self.iterations_spin.setValue(1)
        self.target_none_radio.setChecked(True)
        self.note_input.clear()
        self._on_step_type_changed()
        self._on_target_type_changed()


class WorkoutEditorWidget(QWidget):
    """Widget for editing a complete workout with steps list."""

    workout_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._steps: list[BuilderStep] = []
        self._nested_mode: bool = False
        self._parent_step_index: int = -1
        self._loading: bool = False  # Prevent recursion during load
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the workout editor UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Workout name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Workout Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Easy Run, Tempo, Intervals")
        self.name_input.textChanged.connect(self._emit_changed)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Steps list
        steps_group = QGroupBox("Steps")
        steps_layout = QVBoxLayout(steps_group)

        self.steps_list = QListWidget()
        self.steps_list.setMinimumHeight(120)
        self.steps_list.currentRowChanged.connect(self._on_step_selected)
        steps_layout.addWidget(self.steps_list)

        # Step list buttons
        step_btn_layout = QHBoxLayout()

        self.add_step_btn = QPushButton("+ Add Step")
        self.add_step_btn.clicked.connect(self._on_add_step)
        step_btn_layout.addWidget(self.add_step_btn)

        self.remove_step_btn = QPushButton("- Remove")
        self.remove_step_btn.clicked.connect(self._on_remove_step)
        self.remove_step_btn.setEnabled(False)
        step_btn_layout.addWidget(self.remove_step_btn)

        self.move_up_btn = QPushButton("↑ Up")
        self.move_up_btn.clicked.connect(self._on_move_up)
        self.move_up_btn.setEnabled(False)
        step_btn_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("↓ Down")
        self.move_down_btn.clicked.connect(self._on_move_down)
        self.move_down_btn.setEnabled(False)
        step_btn_layout.addWidget(self.move_down_btn)

        step_btn_layout.addStretch()

        self.edit_nested_btn = QPushButton("Edit Nested Steps")
        self.edit_nested_btn.clicked.connect(self._on_edit_nested)
        self.edit_nested_btn.setVisible(False)
        step_btn_layout.addWidget(self.edit_nested_btn)

        steps_layout.addLayout(step_btn_layout)

        # Nested mode indicator
        self.nested_indicator = QLabel()
        self.nested_indicator.setStyleSheet("color: #2196f3; font-weight: bold;")
        self.nested_indicator.setVisible(False)
        steps_layout.addWidget(self.nested_indicator)

        self.back_to_main_btn = QPushButton("← Back to Main Steps")
        self.back_to_main_btn.clicked.connect(self._on_back_to_main)
        self.back_to_main_btn.setVisible(False)
        steps_layout.addWidget(self.back_to_main_btn)

        layout.addWidget(steps_group)

        # Step editor
        editor_group = QGroupBox("Edit Step")
        editor_layout = QVBoxLayout(editor_group)

        self.step_editor = StepEditorWidget()
        self.step_editor.step_changed.connect(self._on_step_edited)
        editor_layout.addWidget(self.step_editor)

        layout.addWidget(editor_group)

        # Preview
        preview_group = QGroupBox("Preview (CSV Format)")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setStyleSheet("font-family: monospace;")
        preview_layout.addWidget(self.preview_text)

        layout.addWidget(preview_group)

    def _emit_changed(self) -> None:
        """Emit workout changed signal."""
        self._update_preview()
        self.workout_changed.emit()

    def _get_current_steps_list(self) -> list[BuilderStep]:
        """Get the current steps list (main or nested)."""
        if self._nested_mode and 0 <= self._parent_step_index < len(self._steps):
            return self._steps[self._parent_step_index].nested_steps
        return self._steps

    def _refresh_steps_list(self) -> None:
        """Refresh the steps list widget."""
        self.steps_list.clear()
        steps = self._get_current_steps_list()

        for i, step in enumerate(steps):
            text = self._format_step_display(step, i)
            item = QListWidgetItem(text)
            self.steps_list.addItem(item)

        self._update_buttons()

    def _format_step_display(self, step: BuilderStep, index: int) -> str:
        """Format a step for display in the list."""
        if step.step_type == StepType.REPEAT:
            nested_count = len(step.nested_steps)
            return f"{index + 1}. Repeat x{step.iterations} ({nested_count} steps)"

        parts = [f"{index + 1}. {step.step_type.value.capitalize()}"]

        if step.duration:
            parts.append(step.duration.to_csv())

        if step.target.type != TargetType.NONE:
            parts.append(step.target.to_csv())

        return " ".join(parts)

    def _update_buttons(self) -> None:
        """Update button states."""
        steps = self._get_current_steps_list()
        current = self.steps_list.currentRow()
        has_selection = current >= 0

        self.remove_step_btn.setEnabled(has_selection)
        self.move_up_btn.setEnabled(has_selection and current > 0)
        self.move_down_btn.setEnabled(has_selection and current < len(steps) - 1)

        # Show edit nested button only for repeat steps
        if has_selection and current < len(steps):
            step = steps[current]
            self.edit_nested_btn.setVisible(
                step.step_type == StepType.REPEAT and not self._nested_mode
            )
        else:
            self.edit_nested_btn.setVisible(False)

    def _on_step_selected(self, row: int) -> None:
        """Handle step selection."""
        if self._loading:
            return
        steps = self._get_current_steps_list()
        if 0 <= row < len(steps):
            self._loading = True
            self.step_editor.set_step(steps[row])
            self._loading = False
        self._update_buttons()

    def _on_add_step(self) -> None:
        """Add a new step."""
        steps = self._get_current_steps_list()
        new_step = self.step_editor.get_step()
        steps.append(new_step)
        self._refresh_steps_list()
        self.steps_list.setCurrentRow(len(steps) - 1)
        self._emit_changed()

    def _on_remove_step(self) -> None:
        """Remove the selected step."""
        steps = self._get_current_steps_list()
        current = self.steps_list.currentRow()
        if 0 <= current < len(steps):
            del steps[current]
            self._refresh_steps_list()
            if steps:
                self.steps_list.setCurrentRow(min(current, len(steps) - 1))
            self._emit_changed()

    def _on_move_up(self) -> None:
        """Move selected step up."""
        steps = self._get_current_steps_list()
        current = self.steps_list.currentRow()
        if current > 0:
            steps[current], steps[current - 1] = steps[current - 1], steps[current]
            self._refresh_steps_list()
            self.steps_list.setCurrentRow(current - 1)
            self._emit_changed()

    def _on_move_down(self) -> None:
        """Move selected step down."""
        steps = self._get_current_steps_list()
        current = self.steps_list.currentRow()
        if current < len(steps) - 1:
            steps[current], steps[current + 1] = steps[current + 1], steps[current]
            self._refresh_steps_list()
            self.steps_list.setCurrentRow(current + 1)
            self._emit_changed()

    def _on_step_edited(self) -> None:
        """Handle step editor changes."""
        if self._loading:
            return
        steps = self._get_current_steps_list()
        current = self.steps_list.currentRow()
        if 0 <= current < len(steps):
            edited_step = self.step_editor.get_step()
            # Preserve nested steps if this is a repeat
            if steps[current].step_type == StepType.REPEAT:
                edited_step.nested_steps = steps[current].nested_steps
            steps[current] = edited_step
            self._loading = True
            self._refresh_steps_list()
            self.steps_list.setCurrentRow(current)
            self._loading = False
            self._emit_changed()

    def _on_edit_nested(self) -> None:
        """Enter nested editing mode for a repeat step."""
        current = self.steps_list.currentRow()
        if current >= 0 and self._steps[current].step_type == StepType.REPEAT:
            self._nested_mode = True
            self._parent_step_index = current
            self.nested_indicator.setText(
                f"Editing nested steps for: Repeat x{self._steps[current].iterations}"
            )
            self.nested_indicator.setVisible(True)
            self.back_to_main_btn.setVisible(True)
            self.step_editor.clear()
            self._refresh_steps_list()

    def _on_back_to_main(self) -> None:
        """Exit nested editing mode."""
        self._nested_mode = False
        self._parent_step_index = -1
        self.nested_indicator.setVisible(False)
        self.back_to_main_btn.setVisible(False)
        self._refresh_steps_list()

    def _update_preview(self) -> None:
        """Update the CSV preview."""
        workout = self.get_workout()
        self.preview_text.setText(workout.to_csv_cell())

    def get_workout(self) -> BuilderWorkout:
        """Get the current workout."""
        return BuilderWorkout(
            name=self.name_input.text().strip() or "Untitled Workout",
            steps=self._steps.copy(),
        )

    def set_workout(self, workout: BuilderWorkout) -> None:
        """Load a workout into the editor."""
        self._loading = True
        self._steps = [s.copy() for s in workout.steps]
        self.name_input.setText(workout.name)
        self._nested_mode = False
        self._parent_step_index = -1
        self.nested_indicator.setVisible(False)
        self.back_to_main_btn.setVisible(False)
        self._refresh_steps_list()
        if self._steps:
            self.steps_list.setCurrentRow(0)
            self.step_editor.set_step(self._steps[0])
        self._loading = False
        self._update_preview()

    def clear(self) -> None:
        """Clear the editor."""
        self._loading = True
        self._steps = []
        self.name_input.clear()
        self._nested_mode = False
        self._parent_step_index = -1
        self.nested_indicator.setVisible(False)
        self.back_to_main_btn.setVisible(False)
        self.step_editor.clear()
        self._refresh_steps_list()
        self.preview_text.clear()
        self._loading = False
