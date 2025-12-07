"""Calendar grid widget for planning workouts across weeks."""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QColor, QDrag, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import BuilderStep, BuilderWorkout, Duration, DurationType, StepType

logger = logging.getLogger(__name__)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Color scheme for workout types
WORKOUT_COLORS = {
    "easy": QColor(76, 175, 80),      # Green
    "recovery": QColor(139, 195, 74),  # Light green
    "long": QColor(33, 150, 243),      # Blue
    "tempo": QColor(255, 152, 0),      # Orange
    "threshold": QColor(255, 152, 0),  # Orange
    "interval": QColor(244, 67, 54),   # Red
    "speed": QColor(244, 67, 54),      # Red
    "vo2": QColor(156, 39, 176),       # Purple
    "hill": QColor(121, 85, 72),       # Brown
    "fartlek": QColor(255, 193, 7),    # Amber
    "rest": QColor(158, 158, 158),     # Gray
    "default": QColor(0, 150, 136),    # Teal
}


def get_workout_color(workout: BuilderWorkout) -> QColor:
    """Get color based on workout name/type."""
    name_lower = workout.name.lower()
    for keyword, color in WORKOUT_COLORS.items():
        if keyword in name_lower:
            return color
    return WORKOUT_COLORS["default"]


def estimate_workout_duration(workout: BuilderWorkout) -> int:
    """Estimate total workout duration in minutes."""
    total_seconds = 0

    def process_step(step: BuilderStep, multiplier: int = 1) -> int:
        seconds = 0
        if step.step_type == StepType.REPEAT:
            for nested in step.nested_steps:
                seconds += process_step(nested, step.iterations)
        elif step.duration:
            if step.duration.type == DurationType.TIME:
                try:
                    parts = step.duration.value.split(":")
                    if len(parts) == 2:
                        seconds = int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 1:
                        seconds = int(parts[0]) * 60
                except ValueError:
                    pass
            elif step.duration.type == DurationType.KILOMETERS:
                # Estimate 6 min/km
                try:
                    km = float(step.duration.value)
                    seconds = int(km * 6 * 60)
                except ValueError:
                    pass
            elif step.duration.type == DurationType.MILES:
                # Estimate 10 min/mile
                try:
                    miles = float(step.duration.value)
                    seconds = int(miles * 10 * 60)
                except ValueError:
                    pass
        return seconds * multiplier

    for step in workout.steps:
        total_seconds += process_step(step)

    return total_seconds // 60


@dataclass
class WeekMeta:
    """Metadata for a training week."""
    label: str = ""  # e.g., "Base", "Build", "Peak", "Taper", "Recovery"
    notes: str = ""
    is_recovery_week: bool = False


class CalendarGridWidget(QWidget):
    """Widget for planning workouts on a weekly calendar grid."""

    workout_selected = Signal(int, int)  # week, day
    workout_double_clicked = Signal(int, int, object)  # week, day, BuilderWorkout

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._weeks: list[list[BuilderWorkout | None]] = []
        self._week_meta: list[WeekMeta] = []
        self._clipboard: BuilderWorkout | None = None
        self._drag_source: tuple[int, int] | None = None
        self._setup_ui()
        self._add_week()  # Start with one week

    def _setup_ui(self) -> None:
        """Create the calendar grid UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header with controls
        header_layout = QHBoxLayout()

        header_layout.addWidget(QLabel("📅 Training Plan"))
        header_layout.addStretch()

        self.quick_fill_btn = QPushButton("⚡ Quick Fill")
        self.quick_fill_btn.clicked.connect(self._on_quick_fill)
        header_layout.addWidget(self.quick_fill_btn)

        self.add_week_btn = QPushButton("+ Add Week")
        self.add_week_btn.clicked.connect(self._add_week)
        header_layout.addWidget(self.add_week_btn)

        self.remove_week_btn = QPushButton("- Remove Week")
        self.remove_week_btn.clicked.connect(self._remove_week)
        self.remove_week_btn.setEnabled(False)
        header_layout.addWidget(self.remove_week_btn)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.clicked.connect(self._clear_all)
        header_layout.addWidget(self.clear_all_btn)

        layout.addLayout(header_layout)

        # Table with extra columns for week info and summary
        self.table = QTableWidget()
        self.table.setColumnCount(10)  # Week + Label + 7 days + Summary
        self.table.setHorizontalHeaderLabels(["Wk", "Phase"] + DAYS + ["Total"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 30)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 70)
        for i in range(2, 9):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(9, 70)
        
        # Enable drag and drop
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.viewport().setAcceptDrops(True)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table)

        # Summary bar
        summary_layout = QHBoxLayout()
        
        self.summary_label = QLabel("0 weeks, 0 workouts")
        self.summary_label.setStyleSheet("opacity: 0.7;")
        summary_layout.addWidget(self.summary_label)
        
        summary_layout.addStretch()
        
        self.total_time_label = QLabel("Total: 0h 0min")
        self.total_time_label.setStyleSheet("font-weight: bold;")
        summary_layout.addWidget(self.total_time_label)
        
        layout.addLayout(summary_layout)

    def _add_week(self) -> None:
        """Add a new week to the calendar."""
        week_data: list[BuilderWorkout | None] = [None] * 7
        self._weeks.append(week_data)
        self._week_meta.append(WeekMeta())
        self._refresh_table()
        self.remove_week_btn.setEnabled(len(self._weeks) > 1)

    def _remove_week(self) -> None:
        """Remove the last week."""
        if len(self._weeks) > 1:
            self._weeks.pop()
            self._week_meta.pop()
            self._refresh_table()
            self.remove_week_btn.setEnabled(len(self._weeks) > 1)

    def _clear_all(self) -> None:
        """Clear all workouts."""
        result = QMessageBox.question(
            self,
            "Clear All",
            "Clear all workouts from the calendar?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            for week in self._weeks:
                for i in range(7):
                    week[i] = None
            self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        self.table.setRowCount(len(self._weeks))

        workout_count = 0
        total_plan_minutes = 0
        
        for week_idx, week in enumerate(self._weeks):
            meta = self._week_meta[week_idx] if week_idx < len(self._week_meta) else WeekMeta()
            week_minutes = 0
            
            # Week number
            week_item = QTableWidgetItem(str(week_idx + 1))
            week_item.setFlags(week_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            week_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = week_item.font()
            font.setBold(True)
            week_item.setFont(font)
            self.table.setItem(week_idx, 0, week_item)
            
            # Phase label
            phase_item = QTableWidgetItem(meta.label or "—")
            phase_item.setFlags(phase_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            phase_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if meta.is_recovery_week:
                phase_item.setForeground(QColor(76, 175, 80))  # Green for recovery
            self.table.setItem(week_idx, 1, phase_item)

            # Days
            for day_idx, workout in enumerate(week):
                if workout:
                    text = workout.name
                    workout_count += 1
                    duration = estimate_workout_duration(workout)
                    week_minutes += duration
                else:
                    text = ""

                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if workout:
                    color = get_workout_color(workout)
                    item.setBackground(color)
                    # Use white text for dark backgrounds
                    if color.lightness() < 128:
                        item.setForeground(Qt.GlobalColor.white)
                    else:
                        item.setForeground(Qt.GlobalColor.black)

                self.table.setItem(week_idx, day_idx + 2, item)
            
            # Week total
            hours = week_minutes // 60
            mins = week_minutes % 60
            total_item = QTableWidgetItem(f"{hours}h {mins}m")
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_item.setBackground(QColor(240, 240, 240))
            font = total_item.font()
            font.setBold(True)
            total_item.setFont(font)
            self.table.setItem(week_idx, 9, total_item)
            
            total_plan_minutes += week_minutes

        # Update summary
        self.summary_label.setText(f"{len(self._weeks)} weeks, {workout_count} workouts")
        total_hours = total_plan_minutes // 60
        total_mins = total_plan_minutes % 60
        self.total_time_label.setText(f"Total: {total_hours}h {total_mins}min")

    def _on_quick_fill(self) -> None:
        """Show quick fill dialog."""
        dialog = QuickFillDialog(len(self._weeks), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fills = dialog.get_fills()
            for week_idx, day_idx, workout in fills:
                if 0 <= week_idx < len(self._weeks):
                    self._weeks[week_idx][day_idx] = workout.copy()
            self._refresh_table()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Handle cell click."""
        if col == 1:  # Phase column - allow editing
            self._edit_week_meta(row)
        elif 2 <= col <= 8:  # Day columns
            self.workout_selected.emit(row, col - 2)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        """Handle cell double-click."""
        if 2 <= col <= 8:
            day_idx = col - 2
            workout = self._weeks[row][day_idx]
            self.workout_double_clicked.emit(row, day_idx, workout)

    def _edit_week_meta(self, week_idx: int) -> None:
        """Edit week metadata."""
        if week_idx >= len(self._week_meta):
            return
            
        dialog = WeekMetaDialog(self._week_meta[week_idx], week_idx + 1, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._week_meta[week_idx] = dialog.get_meta()
            self._refresh_table()

    def _on_context_menu(self, pos) -> None:
        """Show context menu for cells."""
        item = self.table.itemAt(pos)
        if not item:
            return

        row = item.row()
        col = item.column()

        if col < 2 or col > 8:  # Only day columns
            return

        day_idx = col - 2
        workout = self._weeks[row][day_idx]

        menu = QMenu(self)

        if workout:
            edit_action = menu.addAction("✏️ Edit Workout")
            edit_action.triggered.connect(
                lambda: self.workout_double_clicked.emit(row, day_idx, workout)
            )

            menu.addSeparator()

            copy_action = menu.addAction("📋 Copy")
            copy_action.triggered.connect(lambda: self._copy_workout(row, day_idx))

            dup_next_action = menu.addAction("📅 Duplicate to Next Week")
            dup_next_action.triggered.connect(lambda: self._duplicate_to_next_week(row, day_idx))

            menu.addSeparator()

            clear_action = menu.addAction("🗑️ Clear")
            clear_action.triggered.connect(lambda: self._clear_cell(row, day_idx))
        else:
            if self._clipboard:
                paste_action = menu.addAction("📋 Paste")
                paste_action.triggered.connect(lambda: self._paste_workout(row, day_idx))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_workout(self, week: int, day: int) -> None:
        """Copy workout to clipboard."""
        workout = self._weeks[week][day]
        if workout:
            self._clipboard = workout.copy()

    def _paste_workout(self, week: int, day: int) -> None:
        """Paste workout from clipboard."""
        if self._clipboard:
            self._weeks[week][day] = self._clipboard.copy()
            self._refresh_table()

    def _clear_cell(self, week: int, day: int) -> None:
        """Clear a cell."""
        self._weeks[week][day] = None
        self._refresh_table()

    def _duplicate_to_next_week(self, week: int, day: int) -> None:
        """Duplicate workout to the same day next week."""
        workout = self._weeks[week][day]
        if workout:
            next_week = week + 1
            if next_week >= len(self._weeks):
                self._add_week()
            self._weeks[next_week][day] = workout.copy()
            self._refresh_table()

    def set_workout(self, week: int, day: int, workout: BuilderWorkout | None) -> None:
        """Set a workout at a specific position."""
        while week >= len(self._weeks):
            self._add_week()
        self._weeks[week][day] = workout.copy() if workout else None
        self._refresh_table()

    def get_workout(self, week: int, day: int) -> BuilderWorkout | None:
        """Get workout at a specific position."""
        if 0 <= week < len(self._weeks) and 0 <= day < 7:
            return self._weeks[week][day]
        return None

    def get_all_workouts(self) -> list[list[BuilderWorkout | None]]:
        """Get all workouts."""
        return self._weeks

    def set_all_workouts(self, weeks: list[list[BuilderWorkout | None]]) -> None:
        """Set all workouts."""
        self._weeks = weeks
        # Ensure week_meta matches
        while len(self._week_meta) < len(self._weeks):
            self._week_meta.append(WeekMeta())
        self._refresh_table()
        self.remove_week_btn.setEnabled(len(self._weeks) > 1)

    def get_week_count(self) -> int:
        """Get number of weeks."""
        return len(self._weeks)

    def set_week_meta(self, week: int, meta: WeekMeta) -> None:
        """Set week metadata."""
        while week >= len(self._week_meta):
            self._week_meta.append(WeekMeta())
        self._week_meta[week] = meta
        self._refresh_table()

    def copy_week(self, source_week: int, target_week: int) -> None:
        """Copy all workouts from one week to another."""
        if 0 <= source_week < len(self._weeks):
            while target_week >= len(self._weeks):
                self._add_week()
            for day in range(7):
                workout = self._weeks[source_week][day]
                self._weeks[target_week][day] = workout.copy() if workout else None
            self._refresh_table()

    def to_csv(self) -> str:
        """Export calendar to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Week"] + DAYS)

        # Data
        for week_idx, week in enumerate(self._weeks):
            row = [str(week_idx + 1)]
            for workout in week:
                if workout:
                    row.append(workout.to_csv_cell())
                else:
                    row.append("")
            writer.writerow(row)

        return output.getvalue()


class WeekMetaDialog(QDialog):
    """Dialog for editing week metadata."""

    def __init__(self, meta: WeekMeta, week_num: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.meta = meta
        self.week_num = week_num
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"Week {self.week_num} Settings")
        self.setMinimumWidth(300)

        layout = QFormLayout(self)

        # Phase label
        self.label_combo = QComboBox()
        self.label_combo.setEditable(True)
        self.label_combo.addItems(["", "Base", "Build", "Peak", "Taper", "Recovery", "Race"])
        if self.meta.label:
            self.label_combo.setCurrentText(self.meta.label)
        layout.addRow("Phase:", self.label_combo)

        # Recovery week checkbox
        self.recovery_check = QCheckBox("Recovery Week (reduced volume)")
        self.recovery_check.setChecked(self.meta.is_recovery_week)
        layout.addRow(self.recovery_check)

        # Notes
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Notes for this week...")
        self.notes_edit.setPlainText(self.meta.notes)
        self.notes_edit.setMaximumHeight(80)
        layout.addRow("Notes:", self.notes_edit)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def get_meta(self) -> WeekMeta:
        return WeekMeta(
            label=self.label_combo.currentText(),
            notes=self.notes_edit.toPlainText(),
            is_recovery_week=self.recovery_check.isChecked(),
        )


class QuickFillDialog(QDialog):
    """Dialog for quickly filling workouts across weeks."""

    def __init__(self, num_weeks: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.num_weeks = num_weeks
        self._fills: list[tuple[int, int, BuilderWorkout]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Quick Fill")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Fill type
        type_group = QGroupBox("Fill Type")
        type_layout = QVBoxLayout(type_group)

        self.fill_type_combo = QComboBox()
        self.fill_type_combo.addItems([
            "Fill specific day across all weeks",
            "Add recovery week every N weeks",
            "Copy week to multiple weeks",
        ])
        self.fill_type_combo.currentIndexChanged.connect(self._on_fill_type_changed)
        type_layout.addWidget(self.fill_type_combo)

        layout.addWidget(type_group)

        # Settings (changes based on fill type)
        self.settings_group = QGroupBox("Settings")
        self.settings_layout = QFormLayout(self.settings_group)
        layout.addWidget(self.settings_group)

        # Day selection
        self.day_combo = QComboBox()
        for day in DAYS:
            self.day_combo.addItem(day)
        self.settings_layout.addRow("Day:", self.day_combo)

        # Workout selection
        self.workout_combo = QComboBox()
        from .models import TemplateStore
        store = TemplateStore()
        for template in store.get_all_templates():
            self.workout_combo.addItem(template.name, template.workout)
        self.settings_layout.addRow("Workout:", self.workout_combo)

        # Week range
        range_layout = QHBoxLayout()
        self.start_week_spin = QSpinBox()
        self.start_week_spin.setRange(1, max(1, self.num_weeks))
        self.start_week_spin.setValue(1)
        range_layout.addWidget(QLabel("From week:"))
        range_layout.addWidget(self.start_week_spin)

        self.end_week_spin = QSpinBox()
        self.end_week_spin.setRange(1, max(1, self.num_weeks))
        self.end_week_spin.setValue(self.num_weeks)
        range_layout.addWidget(QLabel("To:"))
        range_layout.addWidget(self.end_week_spin)
        range_layout.addStretch()

        self.settings_layout.addRow("Weeks:", range_layout)

        # Recovery week interval (hidden initially)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 8)
        self.interval_spin.setValue(4)
        self.interval_label = QLabel("Every N weeks:")
        self.settings_layout.addRow(self.interval_label, self.interval_spin)
        self.interval_label.setVisible(False)
        self.interval_spin.setVisible(False)

        # Preview
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._generate_preview)
        layout.addWidget(preview_btn)

        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("opacity: 0.7;")
        layout.addWidget(self.preview_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_fill_type_changed(self, index: int) -> None:
        """Update settings based on fill type."""
        is_recovery = index == 1
        self.interval_label.setVisible(is_recovery)
        self.interval_spin.setVisible(is_recovery)

    def _generate_preview(self) -> None:
        """Generate and show preview."""
        self._fills = []
        fill_type = self.fill_type_combo.currentIndex()
        
        day_idx = self.day_combo.currentIndex()
        workout = self.workout_combo.currentData()
        start = self.start_week_spin.value() - 1
        end = self.end_week_spin.value()

        if fill_type == 0:  # Fill specific day
            for week in range(start, end):
                self._fills.append((week, day_idx, workout))
            self.preview_label.setText(
                f"Will add {workout.name} to {DAYS[day_idx]} for weeks {start + 1}-{end}"
            )

        elif fill_type == 1:  # Recovery weeks
            interval = self.interval_spin.value()
            recovery_weeks = []
            for week in range(interval - 1, end, interval):
                if week >= start:
                    recovery_weeks.append(week + 1)
            self.preview_label.setText(
                f"Will mark weeks {', '.join(map(str, recovery_weeks))} as recovery weeks"
            )

        elif fill_type == 2:  # Copy week
            source = start
            for week in range(start + 1, end):
                self._fills.append((week, -1, None))  # Special marker
            self.preview_label.setText(
                f"Will copy week {source + 1} to weeks {source + 2}-{end}"
            )

    def get_fills(self) -> list[tuple[int, int, BuilderWorkout]]:
        """Get the fill operations."""
        return self._fills


class ProgressiveGeneratorDialog(QDialog):
    """Dialog for generating progressive workouts."""

    def __init__(
        self,
        base_workout: BuilderWorkout,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.base_workout = base_workout
        self.generated_workouts: list[tuple[int, int, BuilderWorkout]] = []  # (week, day, workout)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dialog UI."""
        self.setWindowTitle("Generate Progressive Workouts")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Base workout info
        info_group = QGroupBox("Base Workout")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(f"<b>{self.base_workout.name}</b>"))

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMaximumHeight(100)
        preview.setText(self.base_workout.to_csv_cell())
        info_layout.addWidget(preview)

        layout.addWidget(info_group)

        # Progression settings
        settings_group = QGroupBox("Progression Settings")
        settings_layout = QFormLayout(settings_group)

        # Find the first duration step for progression
        self._duration_step_index = -1
        for i, step in enumerate(self.base_workout.steps):
            if step.duration and step.duration.type == DurationType.TIME:
                self._duration_step_index = i
                break

        if self._duration_step_index >= 0:
            step = self.base_workout.steps[self._duration_step_index]
            settings_layout.addRow("Progressing:", QLabel(f"{step.step_type.value.capitalize()} step duration"))

            # Start duration
            self.start_duration = QSpinBox()
            self.start_duration.setRange(1, 300)
            self.start_duration.setSuffix(" min")
            # Parse current duration
            try:
                parts = step.duration.value.split(":")
                minutes = int(parts[0])
                self.start_duration.setValue(minutes)
            except (ValueError, IndexError):
                self.start_duration.setValue(30)
            settings_layout.addRow("Start Duration:", self.start_duration)

            # End duration
            self.end_duration = QSpinBox()
            self.end_duration.setRange(1, 300)
            self.end_duration.setSuffix(" min")
            self.end_duration.setValue(self.start_duration.value() + 30)
            settings_layout.addRow("End Duration:", self.end_duration)

            # Step increment
            self.increment = QSpinBox()
            self.increment.setRange(1, 60)
            self.increment.setSuffix(" min")
            self.increment.setValue(10)
            settings_layout.addRow("Increment:", self.increment)
        else:
            settings_layout.addRow(QLabel("No time-based duration step found to progress."))

        layout.addWidget(settings_group)

        # Schedule settings
        schedule_group = QGroupBox("Schedule")
        schedule_layout = QFormLayout(schedule_group)

        # Target day
        self.target_day = QComboBox()
        for day in DAYS:
            self.target_day.addItem(day)
        schedule_layout.addRow("Day of Week:", self.target_day)

        # Starting week
        self.start_week = QSpinBox()
        self.start_week.setRange(1, 52)
        self.start_week.setValue(1)
        schedule_layout.addRow("Starting Week:", self.start_week)

        layout.addWidget(schedule_group)

        # Preview button
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._generate_preview)
        layout.addWidget(preview_btn)

        # Preview table
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Week", "Day", "Workout"])
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.preview_table.setMinimumHeight(150)
        layout.addWidget(self.preview_table)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _generate_preview(self) -> None:
        """Generate and preview the workouts."""
        self.generated_workouts = []
        self.preview_table.setRowCount(0)

        if self._duration_step_index < 0:
            return

        start = self.start_duration.value()
        end = self.end_duration.value()
        inc = self.increment.value()
        day_idx = self.target_day.currentIndex()
        week_offset = self.start_week.value() - 1

        current = start
        week = 0

        while current <= end:
            # Create modified workout
            workout = self.base_workout.copy()
            workout.name = f"{self.base_workout.name} - {current}min"

            # Modify the duration step
            step = workout.steps[self._duration_step_index]
            step.duration = Duration(DurationType.TIME, f"{current}:00")

            self.generated_workouts.append((week + week_offset, day_idx, workout))

            # Add to preview table
            row = self.preview_table.rowCount()
            self.preview_table.insertRow(row)
            self.preview_table.setItem(row, 0, QTableWidgetItem(str(week + week_offset + 1)))
            self.preview_table.setItem(row, 1, QTableWidgetItem(DAYS[day_idx]))
            self.preview_table.setItem(row, 2, QTableWidgetItem(workout.name))

            current += inc
            week += 1

    def get_generated_workouts(self) -> list[tuple[int, int, BuilderWorkout]]:
        """Get the generated workouts (week, day, workout)."""
        return self.generated_workouts
