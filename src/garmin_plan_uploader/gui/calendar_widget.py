"""Calendar widget with month grid navigation."""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..garmin_client import get_workout_details
from ..workout_service import DeleteResult, ScheduledWorkout, WorkoutService
from .workers import DeleteWorkoutsWorker, FetchWorkoutsWorker, run_worker

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ICalExportDialog(QDialog):
    """Dialog for selecting iCal export options."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export to iCal")
        self.setMinimumWidth(350)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(
            "Export scheduled workouts to an iCal (.ics) file that can be "
            "imported into your calendar app (Apple Calendar, Google Calendar, etc.)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Date range selection
        range_group = QGroupBox("Date Range")
        range_layout = QVBoxLayout(range_group)

        self.range_group = QButtonGroup(self)

        self.month_radio = QRadioButton("This Month")
        self.month_radio.setChecked(True)
        self.range_group.addButton(self.month_radio, 0)
        range_layout.addWidget(self.month_radio)

        self.quarter_radio = QRadioButton("Next 3 Months")
        self.range_group.addButton(self.quarter_radio, 1)
        range_layout.addWidget(self.quarter_radio)

        self.year_radio = QRadioButton("Next Year")
        self.range_group.addButton(self.year_radio, 2)
        range_layout.addWidget(self.year_radio)

        layout.addWidget(range_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_date_range(self) -> tuple[date, date]:
        """Get the selected date range."""
        today = date.today()

        if self.month_radio.isChecked():
            start = today.replace(day=1)
            if today.month == 12:
                end = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif self.quarter_radio.isChecked():
            start = today
            end = today + timedelta(days=90)
        else:  # year
            start = today
            end = today + timedelta(days=365)

        return start, end


class WorkoutDetailsDialog(QDialog):
    """Dialog showing full workout details with steps."""

    def __init__(
        self,
        workouts: list[ScheduledWorkout],
        service: WorkoutService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.workouts = workouts
        self.service = service
        self.setWindowTitle("Workout Details")
        self.setMinimumSize(500, 400)
        self.resize(600, 500)

        self._setup_ui()
        self._load_first_workout()

    def _setup_ui(self) -> None:
        """Create the dialog UI."""
        layout = QVBoxLayout(self)

        # Date header
        if self.workouts:
            workout_date = self.workouts[0].date
            date_label = QLabel(workout_date.strftime("%A, %B %d, %Y"))
            date_label.setStyleSheet("font-size: 16px; font-weight: bold;")
            date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(date_label)

        # Splitter for workout list and details
        if len(self.workouts) > 1:
            splitter = QSplitter(Qt.Orientation.Horizontal)

            # Workout list (left side)
            self.workout_list = QListWidget()
            for w in self.workouts:
                item = QListWidgetItem(w.title)
                item.setData(Qt.ItemDataRole.UserRole, w)
                self.workout_list.addItem(item)
            self.workout_list.currentItemChanged.connect(self._on_workout_selected)
            splitter.addWidget(self.workout_list)

            # Details panel (right side)
            self.details_widget = QWidget()
            self.details_layout = QVBoxLayout(self.details_widget)
            splitter.addWidget(self.details_widget)

            splitter.setSizes([150, 450])
            layout.addWidget(splitter)
        else:
            # Single workout - just show details
            self.workout_list = None
            self.details_widget = QWidget()
            self.details_layout = QVBoxLayout(self.details_widget)
            layout.addWidget(self.details_widget)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _load_first_workout(self) -> None:
        """Load the first workout's details."""
        if self.workouts:
            if self.workout_list:
                self.workout_list.setCurrentRow(0)
            else:
                self._show_workout_details(self.workouts[0])

    def _on_workout_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle workout selection change."""
        if current:
            workout = current.data(Qt.ItemDataRole.UserRole)
            self._show_workout_details(workout)

    def _show_workout_details(self, workout: ScheduledWorkout) -> None:
        """Fetch and display workout details."""
        # Clear existing content
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Title
        title_label = QLabel(workout.title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.details_layout.addWidget(title_label)

        # Loading indicator
        loading_label = QLabel("Loading workout steps...")
        loading_label.setStyleSheet("opacity: 0.7; font-style: italic;")
        self.details_layout.addWidget(loading_label)

        # Fetch details in background (simple sync call for now)
        try:
            if workout.workout_id:
                details = get_workout_details(self.service.session, workout.workout_id)
                # Remove loading label from layout and delete it
                self.details_layout.removeWidget(loading_label)
                loading_label.deleteLater()
                self._display_workout_steps(details)
            else:
                loading_label.setText("No workout details available")
        except Exception as e:
            loading_label.setText(f"Error loading details: {e}")
            loading_label.setStyleSheet("color: #f44336;")

    def _display_workout_steps(self, details: dict) -> None:
        """Display the workout steps."""
        # Scroll area for steps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        # Get steps from workout
        steps = details.get("workoutSegments", [])
        if not steps:
            steps = details.get("steps", [])

        # Find the main segment with steps
        workout_steps = []
        for segment in steps:
            if "workoutSteps" in segment:
                workout_steps = segment["workoutSteps"]
                break

        if not workout_steps and isinstance(steps, list):
            workout_steps = steps

        if workout_steps:
            self._add_steps_to_layout(workout_steps, content_layout, indent=0)
        else:
            no_steps = QLabel("No steps found in workout")
            no_steps.setStyleSheet("color: palette(text); opacity: 0.6;")
            content_layout.addWidget(no_steps)

        content_layout.addStretch()
        scroll.setWidget(content)
        self.details_layout.addWidget(scroll)

    def _add_steps_to_layout(
        self,
        steps: list,
        layout: QVBoxLayout,
        indent: int = 0,
    ) -> None:
        """Recursively add steps to the layout."""
        for i, step in enumerate(steps, 1):
            step_widget = self._create_step_widget(step, i, indent)
            layout.addWidget(step_widget)

            # Handle repeat groups
            if step.get("type") == "RepeatGroupDTO" or "repeatSteps" in step:
                repeat_steps = step.get("repeatSteps", step.get("workoutSteps", []))
                if repeat_steps:
                    self._add_steps_to_layout(repeat_steps, layout, indent + 1)

    def _create_step_widget(self, step: dict, number: int, indent: int) -> QFrame:
        """Create a widget for a single step."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(128, 128, 128, 0.1);
                border: 1px solid palette(mid);
                border-radius: 4px;
                margin-left: {indent * 20}px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Step type and number
        step_type = step.get("stepType", {})
        if isinstance(step_type, dict):
            type_key = step_type.get("stepTypeKey", "unknown")
        else:
            type_key = str(step_type)

        # Check for repeat
        if step.get("type") == "RepeatGroupDTO" or "numberOfIterations" in step:
            repeat_count = step.get("numberOfIterations", 1)
            type_display = f"🔄 Repeat x{repeat_count}"
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(33, 150, 243, 0.2);
                    border: 1px solid rgba(33, 150, 243, 0.5);
                    border-radius: 4px;
                    margin-left: {indent * 20}px;
                    padding: 8px;
                }}
            """)
        else:
            # Map step types to display names and semi-transparent colors
            type_map = {
                "warmup": ("🔥 Warm Up", "rgba(255, 152, 0, 0.2)"),
                "cooldown": ("❄️ Cool Down", "rgba(33, 150, 243, 0.2)"),
                "interval": ("🏃 Run", "rgba(76, 175, 80, 0.2)"),
                "recovery": ("😮‍💨 Recover", "rgba(233, 30, 99, 0.15)"),
                "rest": ("⏸️ Rest", "rgba(128, 128, 128, 0.1)"),
                "other": ("📋 Other", "rgba(128, 128, 128, 0.1)"),
            }
            display_name, bg_color = type_map.get(
                type_key.lower(),
                (type_key.title(), "rgba(128, 128, 128, 0.1)")
            )
            type_display = f"{display_name}"
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border: 1px solid palette(mid);
                    border-radius: 4px;
                    margin-left: {indent * 20}px;
                    padding: 8px;
                }}
            """)

        header = QLabel(f"<b>{number}. {type_display}</b>")
        layout.addWidget(header)

        # Duration/Distance
        duration_info = self._format_duration(step)
        if duration_info:
            duration_label = QLabel(duration_info)
            layout.addWidget(duration_label)

        # Target (pace/HR zone)
        target_info = self._format_target(step)
        if target_info:
            target_label = QLabel(target_info)
            target_label.setStyleSheet("color: #2196f3; font-weight: 500;")
            layout.addWidget(target_label)

        # Notes
        notes = step.get("description") or step.get("notes")
        if notes:
            notes_label = QLabel(f"📝 {notes}")
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet("font-style: italic; opacity: 0.8;")
            layout.addWidget(notes_label)

        return frame

    def _format_duration(self, step: dict) -> str:
        """Format step duration for display."""
        end_condition = step.get("endCondition", {})
        if isinstance(end_condition, dict):
            condition_type = end_condition.get("conditionTypeKey", "")
        else:
            condition_type = ""

        # Time-based duration
        if "duration" in step or condition_type == "time":
            seconds = step.get("endConditionValue", 0)
            if not seconds:
                seconds = step.get("duration", {}).get("seconds", 0)
            if seconds:
                mins = int(seconds) // 60
                secs = int(seconds) % 60
                return f"⏱️ {mins}:{secs:02d}"

        # Distance-based duration
        if "distance" in step or condition_type == "distance":
            meters = step.get("endConditionValue", 0)
            if not meters:
                meters = step.get("distance", {}).get("meters", 0)
            if meters:
                if meters >= 1000:
                    return f"📏 {meters/1000:.1f} km"
                else:
                    return f"📏 {int(meters)} m"

        # Lap button
        if condition_type == "lap.button":
            return "🔘 Lap Button"

        return ""

    def _format_target(self, step: dict) -> str:
        """Format step target for display."""
        target = step.get("targetType", {})
        if isinstance(target, dict):
            target_type = target.get("workoutTargetTypeKey", "")
        else:
            target_type = ""

        # Heart rate zone
        if target_type == "heart.rate.zone" or "targetValueOne" in step:
            zone = step.get("zoneNumber") or step.get("targetValueOne")
            if zone:
                return f"❤️ Zone {int(zone)}"

        # Pace target
        if target_type == "pace.zone" or "targetPaceLow" in step:
            low = step.get("targetValueLow") or step.get("targetPaceLow")
            high = step.get("targetValueHigh") or step.get("targetPaceHigh")
            if low and high:
                # Convert m/s to min/km
                def mps_to_pace(mps):
                    if mps <= 0:
                        return "?"
                    pace_sec = 1000 / mps
                    mins = int(pace_sec) // 60
                    secs = int(pace_sec) % 60
                    return f"{mins}:{secs:02d}"

                return f"🎯 Pace: {mps_to_pace(high)} - {mps_to_pace(low)} /km"

        return ""


class DayCell(QFrame):
    """A single day cell in the calendar grid."""

    clicked = Signal(object)  # date

    def __init__(
        self,
        cell_date: date | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.cell_date = cell_date
        self.workouts: list[ScheduledWorkout] = []

        self.setFrameShape(QFrame.Shape.Box)
        self.setMinimumSize(QSize(100, 80))
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self._setup_ui()
        self._update_style()

    def _setup_ui(self) -> None:
        """Create the cell UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Day number label
        self.day_label = QLabel("")
        self.day_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        font = QFont()
        font.setBold(True)
        self.day_label.setFont(font)
        layout.addWidget(self.day_label)

        # Workout labels container
        self.workout_container = QWidget()
        self.workout_layout = QVBoxLayout(self.workout_container)
        self.workout_layout.setContentsMargins(0, 0, 0, 0)
        self.workout_layout.setSpacing(1)
        layout.addWidget(self.workout_container)

        layout.addStretch()

        self._update_display()

    def _update_style(self) -> None:
        """Update cell styling based on state."""
        # Use semi-transparent colors that work in both light and dark mode
        if self.cell_date is None:
            self.setStyleSheet("background-color: rgba(128, 128, 128, 0.1); border: 1px solid palette(mid);")
        elif self.cell_date == date.today():
            self.setStyleSheet("background-color: rgba(33, 150, 243, 0.2); border: 2px solid #2196f3;")
        elif self.cell_date.weekday() >= 5:  # Weekend
            self.setStyleSheet("background-color: rgba(255, 193, 7, 0.15); border: 1px solid palette(mid);")
        else:
            self.setStyleSheet("background-color: palette(base); border: 1px solid palette(mid);")

    def _update_display(self) -> None:
        """Update the displayed content."""
        # Clear existing workout labels
        while self.workout_layout.count():
            item = self.workout_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.cell_date:
            self.day_label.setText(str(self.cell_date.day))

            # Add workout labels
            for workout in self.workouts[:3]:  # Show max 3
                label = QLabel(workout.title)
                label.setStyleSheet(
                    "background-color: #4caf50; color: white; "
                    "padding: 2px 4px; border-radius: 2px; font-size: 10px;"
                )
                label.setWordWrap(True)
                self.workout_layout.addWidget(label)

            # Show overflow indicator
            if len(self.workouts) > 3:
                more_label = QLabel(f"+{len(self.workouts) - 3} more")
                more_label.setStyleSheet("color: palette(text); opacity: 0.7; font-size: 10px;")
                self.workout_layout.addWidget(more_label)
        else:
            self.day_label.setText("")

    def set_date(self, cell_date: date | None) -> None:
        """Set the date for this cell."""
        self.cell_date = cell_date
        self.workouts = []
        self._update_style()
        self._update_display()

    def set_workouts(self, workouts: list[ScheduledWorkout]) -> None:
        """Set the workouts for this cell."""
        self.workouts = workouts
        self._update_display()

    def mousePressEvent(self, event) -> None:
        """Handle click on cell."""
        if self.cell_date and self.workouts:
            self.clicked.emit(self.cell_date)
        super().mousePressEvent(event)


class CalendarGrid(QWidget):
    """Month grid calendar with navigation."""

    workout_clicked = Signal(list)  # list[ScheduledWorkout]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._current_month = date.today().replace(day=1)
        self._cells: list[DayCell] = []
        self._workouts_by_date: dict[date, list[ScheduledWorkout]] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the calendar grid UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Navigation header
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self._on_prev_month)
        nav_layout.addWidget(self.prev_btn)

        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.month_label.setFont(font)
        nav_layout.addWidget(self.month_label, stretch=1)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._on_next_month)
        nav_layout.addWidget(self.next_btn)

        layout.addLayout(nav_layout)

        # Day headers
        header_layout = QHBoxLayout()
        for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = QFont()
            font.setBold(True)
            label.setFont(font)
            header_layout.addWidget(label)
        layout.addLayout(header_layout)

        # Calendar grid (6 rows x 7 columns)
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(2)

        for row in range(6):
            for col in range(7):
                cell = DayCell()
                cell.clicked.connect(self._on_cell_clicked)
                self._cells.append(cell)
                self.grid_layout.addWidget(cell, row, col)

        layout.addLayout(self.grid_layout)

        self._update_month_display()

    def _update_month_display(self) -> None:
        """Update the calendar to show the current month."""
        self.month_label.setText(
            self._current_month.strftime("%B %Y")
        )

        # Get calendar info for this month
        cal = calendar.Calendar(firstweekday=0)  # Monday first
        month_days = list(cal.itermonthdates(
            self._current_month.year,
            self._current_month.month,
        ))

        # Update cells
        for i, cell in enumerate(self._cells):
            if i < len(month_days):
                cell_date = month_days[i]
                # Only show days in current month
                if cell_date.month == self._current_month.month:
                    cell.set_date(cell_date)
                    cell.set_workouts(
                        self._workouts_by_date.get(cell_date, [])
                    )
                else:
                    cell.set_date(None)
            else:
                cell.set_date(None)

    def _on_prev_month(self) -> None:
        """Navigate to previous month."""
        if self._current_month.month == 1:
            self._current_month = self._current_month.replace(
                year=self._current_month.year - 1,
                month=12,
            )
        else:
            self._current_month = self._current_month.replace(
                month=self._current_month.month - 1,
            )
        self._update_month_display()

    def _on_next_month(self) -> None:
        """Navigate to next month."""
        if self._current_month.month == 12:
            self._current_month = self._current_month.replace(
                year=self._current_month.year + 1,
                month=1,
            )
        else:
            self._current_month = self._current_month.replace(
                month=self._current_month.month + 1,
            )
        self._update_month_display()

    def _on_cell_clicked(self, cell_date: date) -> None:
        """Handle cell click."""
        workouts = self._workouts_by_date.get(cell_date, [])
        if workouts:
            self.workout_clicked.emit(workouts)

    def set_workouts(self, workouts: list[ScheduledWorkout]) -> None:
        """Set the workouts to display."""
        self._workouts_by_date.clear()
        for workout in workouts:
            if workout.date not in self._workouts_by_date:
                self._workouts_by_date[workout.date] = []
            self._workouts_by_date[workout.date].append(workout)
        self._update_month_display()

    def go_to_date(self, target_date: date) -> None:
        """Navigate to show a specific date."""
        self._current_month = target_date.replace(day=1)
        self._update_month_display()


class CalendarWidget(QWidget):
    """Full calendar view with fetch and delete functionality."""

    def __init__(
        self,
        service: WorkoutService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self._workouts: list[ScheduledWorkout] = []
        self._worker = None
        self._thread = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the calendar widget UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Date range selection
        range_group = QGroupBox("View Range")
        range_layout = QHBoxLayout(range_group)

        # Quick range buttons
        self.month_btn = QPushButton("This Month")
        self.month_btn.clicked.connect(self._on_this_month)
        range_layout.addWidget(self.month_btn)

        self.quarter_btn = QPushButton("Next 3 Months")
        self.quarter_btn.clicked.connect(self._on_next_quarter)
        range_layout.addWidget(self.quarter_btn)

        self.year_btn = QPushButton("Next Year")
        self.year_btn.clicked.connect(self._on_next_year)
        range_layout.addWidget(self.year_btn)

        range_layout.addStretch()

        self.export_btn = QPushButton("📤 Export iCal")
        self.export_btn.clicked.connect(self._on_export_ical)
        range_layout.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self._on_refresh)
        range_layout.addWidget(self.refresh_btn)

        layout.addWidget(range_group)

        # Calendar grid
        self.calendar_grid = CalendarGrid()
        self.calendar_grid.workout_clicked.connect(self._on_workout_clicked)
        layout.addWidget(self.calendar_grid)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("opacity: 0.7;")
        layout.addWidget(self.status_label)

        # Action buttons
        button_layout = QHBoxLayout()

        self.delete_range_btn = QPushButton("Delete All in Range...")
        self.delete_range_btn.clicked.connect(self._on_delete_range)
        self.delete_range_btn.setEnabled(False)
        button_layout.addWidget(self.delete_range_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Load initial data
        self._on_this_month()

    def _on_this_month(self) -> None:
        """Load current month."""
        today = date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        self._fetch_range(start, end)

    def _on_next_quarter(self) -> None:
        """Load next 3 months."""
        today = date.today()
        start = today
        end = today + timedelta(days=90)
        self._fetch_range(start, end)

    def _on_next_year(self) -> None:
        """Load next year."""
        today = date.today()
        start = today
        end = today + timedelta(days=365)
        self._fetch_range(start, end)

    def _on_refresh(self) -> None:
        """Refresh current range."""
        if hasattr(self, "_last_start") and hasattr(self, "_last_end"):
            self._fetch_range(self._last_start, self._last_end)
        else:
            self._on_this_month()

    def _fetch_range(self, start: date, end: date) -> None:
        """Fetch workouts in date range."""
        self._last_start = start
        self._last_end = end

        self._set_loading(True)
        self.status_label.setText(f"Fetching workouts from {start} to {end}...")

        self._worker = FetchWorkoutsWorker(self.service, start, end)
        self._worker.success.connect(self._on_fetch_success)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.finished.connect(lambda: self._set_loading(False))

        self._thread = run_worker(self._worker)

    def _set_loading(self, loading: bool) -> None:
        """Update UI for loading state."""
        self.refresh_btn.setEnabled(not loading)
        self.month_btn.setEnabled(not loading)
        self.quarter_btn.setEnabled(not loading)
        self.year_btn.setEnabled(not loading)
        self.progress_bar.setVisible(loading)

        if loading:
            self.progress_bar.setRange(0, 0)  # Indeterminate

    def _on_fetch_success(self, workouts: list[ScheduledWorkout]) -> None:
        """Handle successful fetch."""
        self._workouts = workouts
        self.calendar_grid.set_workouts(workouts)
        self.status_label.setText(f"Found {len(workouts)} scheduled workouts")
        self.delete_range_btn.setEnabled(len(workouts) > 0)

        # Navigate to start of range
        if hasattr(self, "_last_start"):
            self.calendar_grid.go_to_date(self._last_start)

    def _on_fetch_error(self, error: str) -> None:
        """Handle fetch error."""
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: #f44336;")
        QMessageBox.critical(self, "Error", f"Failed to fetch workouts:\n\n{error}")

    def _on_workout_clicked(self, workouts: list[ScheduledWorkout]) -> None:
        """Show workout details when cell clicked."""
        if not workouts:
            return

        dialog = WorkoutDetailsDialog(workouts, self.service, self)
        dialog.exec()

    def _on_delete_range(self) -> None:
        """Delete all workouts in the current range."""
        if not self._workouts:
            return

        result = QMessageBox.warning(
            self,
            "Delete Workouts",
            f"Delete {len(self._workouts)} scheduled workouts?\n\n"
            f"This removes them from your calendar but keeps the workout templates.\n\n"
            f"This cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self._start_delete()

    def _start_delete(self) -> None:
        """Start deleting workouts."""
        self._set_loading(True)
        self.progress_bar.setRange(0, len(self._workouts))

        self._worker = DeleteWorkoutsWorker(self.service, self._workouts)
        self._worker.progress.connect(self._on_delete_progress)
        self._worker.success.connect(self._on_delete_success)
        self._worker.error.connect(self._on_delete_error)
        self._worker.finished.connect(lambda: self._set_loading(False))

        self._thread = run_worker(self._worker)

    def _on_delete_progress(self, current: int, total: int, message: str) -> None:
        """Update delete progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_delete_success(self, result: DeleteResult) -> None:
        """Handle delete completion."""
        self._workouts = []
        self.calendar_grid.set_workouts([])

        if result.cancelled:
            QMessageBox.information(
                self,
                "Cancelled",
                f"Deleted {result.deleted} of {result.total} workouts before cancellation.",
            )
        else:
            QMessageBox.information(
                self,
                "Delete Complete",
                f"Deleted {result.deleted} workouts from calendar.",
            )

        # Refresh
        self._on_refresh()

    def _on_delete_error(self, error: str) -> None:
        """Handle delete error."""
        QMessageBox.critical(self, "Error", f"Failed to delete workouts:\n\n{error}")

    def _on_export_ical(self) -> None:
        """Export workouts to iCal format."""
        dialog = ICalExportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        start, end = dialog.get_date_range()

        # Fetch workouts for the selected range
        self._set_loading(True)
        self.status_label.setText(f"Fetching workouts for export ({start} to {end})...")

        # Use a one-shot fetch for export
        self._export_start = start
        self._export_end = end

        # Store worker and thread as instance variables to prevent garbage collection
        self._export_worker = FetchWorkoutsWorker(self.service, start, end)
        self._export_worker.success.connect(self._on_export_fetch_success)
        self._export_worker.error.connect(self._on_export_fetch_error)
        self._export_worker.finished.connect(lambda: self._set_loading(False))

        self._export_thread = run_worker(self._export_worker)

    def _on_export_fetch_success(self, workouts: list[ScheduledWorkout]) -> None:
        """Handle successful fetch for export."""
        if not workouts:
            QMessageBox.information(
                self,
                "Export",
                "No scheduled workouts found in the selected date range.",
            )
            return

        # Fetch detailed workout info for each workout
        self.status_label.setText(f"Fetching workout details for {len(workouts)} workouts...")
        
        workout_details: dict[int, dict] = {}
        for i, workout in enumerate(workouts):
            if workout.workout_id:
                try:
                    details = get_workout_details(self.service.session, workout.workout_id)
                    workout_details[workout.workout_id] = details
                except Exception as e:
                    logger.warning(f"Failed to fetch details for workout {workout.workout_id}: {e}")
            
            # Update progress
            self.status_label.setText(f"Fetching workout details ({i + 1}/{len(workouts)})...")
            QApplication.processEvents()  # Keep UI responsive

        # Build iCal content
        ical_content = self._generate_ical(workouts, workout_details)

        # Save file
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save iCal File",
            f"garmin_workouts_{self._export_start.strftime('%Y%m%d')}_{self._export_end.strftime('%Y%m%d')}.ics",
            "iCal Files (*.ics);;All Files (*)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(ical_content)

                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Exported {len(workouts)} workouts to:\n{file_path}",
                )
                self.status_label.setText(f"Exported {len(workouts)} workouts to iCal")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to save file:\n\n{e}",
                )

    def _on_export_fetch_error(self, error: str) -> None:
        """Handle fetch error during export."""
        self.status_label.setText(f"Export failed: {error}")
        QMessageBox.critical(
            self,
            "Export Error",
            f"Failed to fetch workouts for export:\n\n{error}",
        )

    def _generate_ical(self, workouts: list[ScheduledWorkout], workout_details: dict[int, dict] | None = None) -> str:
        """Generate iCal content from workouts."""
        if workout_details is None:
            workout_details = {}
            
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Garmin Plan Uploader//Scheduled Workouts//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Garmin Scheduled Workouts",
        ]

        for workout in workouts:
            workout_date = workout.date
            uid = f"garmin-workout-{workout.workout_id or workout.calendar_id}@garmin-plan-uploader"

            # Get detailed info if available
            details = workout_details.get(workout.workout_id) if workout.workout_id else None

            # Escape special characters in summary and description
            summary = self._ical_escape(f"🏃 {workout.title}")
            description = self._ical_escape(self._workout_description(workout, details))

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z",
                f"DTSTART;VALUE=DATE:{workout_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(workout_date + timedelta(days=1)).strftime('%Y%m%d')}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    def _ical_escape(self, text: str) -> str:
        """Escape special characters for iCal format."""
        if not text:
            return ""
        # Escape backslashes, semicolons, commas, and newlines
        text = text.replace("\\", "\\\\")
        text = text.replace(";", "\\;")
        text = text.replace(",", "\\,")
        text = text.replace("\n", "\\n")
        return text

    def _workout_description(self, workout: ScheduledWorkout, details: dict | None = None) -> str:
        """Generate a description for the workout including steps."""
        parts = [workout.title, ""]

        # Try to get sport type from raw data or details
        sport_type = None
        if details:
            sport_type = details.get("sportType", {})
        if not sport_type:
            sport_type = workout.raw_data.get("sportType", {})
            
        if isinstance(sport_type, dict):
            sport_name = sport_type.get("sportTypeKey", "")
        else:
            sport_name = str(sport_type) if sport_type else ""
        
        if sport_name:
            parts.append(f"Sport: {sport_name.replace('_', ' ').title()}")
            parts.append("")

        # Add workout steps if we have details
        if details:
            steps = self._extract_workout_steps(details)
            if steps:
                parts.append("WORKOUT STEPS:")
                parts.append("-" * 20)
                for step_text in steps:
                    parts.append(step_text)
                parts.append("")

        return "\n".join(parts)

    def _extract_workout_steps(self, details: dict) -> list[str]:
        """Extract workout steps from details and format as text."""
        steps_text = []
        
        # Get steps from workout
        segments = details.get("workoutSegments", [])
        if not segments:
            segments = details.get("steps", [])

        # Find the main segment with steps
        workout_steps = []
        for segment in segments:
            if "workoutSteps" in segment:
                workout_steps = segment["workoutSteps"]
                break

        if not workout_steps and isinstance(segments, list):
            workout_steps = segments

        # Format each step
        for i, step in enumerate(workout_steps, 1):
            step_text = self._format_step_for_ical(step, i)
            if step_text:
                steps_text.append(step_text)
                
            # Handle repeat groups
            if step.get("type") == "RepeatGroupDTO" or "repeatSteps" in step:
                repeat_steps = step.get("repeatSteps", step.get("workoutSteps", []))
                for j, sub_step in enumerate(repeat_steps, 1):
                    sub_text = self._format_step_for_ical(sub_step, j, indent="  ")
                    if sub_text:
                        steps_text.append(sub_text)

        return steps_text

    def _format_step_for_ical(self, step: dict, number: int, indent: str = "") -> str:
        """Format a single step for iCal description."""
        # Get step type
        step_type = step.get("stepType", {})
        if isinstance(step_type, dict):
            type_key = step_type.get("stepTypeKey", "unknown")
        else:
            type_key = str(step_type)

        # Check for repeat
        if step.get("type") == "RepeatGroupDTO" or "numberOfIterations" in step:
            repeat_count = step.get("numberOfIterations", 1)
            return f"{indent}{number}. REPEAT x{repeat_count}:"

        # Map step types to display names
        type_map = {
            "warmup": "Warm Up",
            "cooldown": "Cool Down",
            "interval": "Run",
            "recovery": "Recovery",
            "rest": "Rest",
            "other": "Other",
        }
        type_display = type_map.get(type_key.lower(), type_key.title())

        # Build step description
        parts = [f"{indent}{number}. {type_display}"]

        # Duration/Distance
        duration_info = self._format_step_duration(step)
        if duration_info:
            parts.append(f"- {duration_info}")

        # Target (pace/HR zone)
        target_info = self._format_step_target(step)
        if target_info:
            parts.append(f"- {target_info}")

        return " ".join(parts)

    def _format_step_duration(self, step: dict) -> str:
        """Format step duration for text display."""
        end_condition = step.get("endCondition", {})
        if isinstance(end_condition, dict):
            condition_type = end_condition.get("conditionTypeKey", "")
        else:
            condition_type = ""

        # Time-based duration
        if "duration" in step or condition_type == "time":
            seconds = step.get("endConditionValue", 0)
            if not seconds:
                seconds = step.get("duration", {}).get("seconds", 0)
            if seconds:
                mins = int(seconds) // 60
                secs = int(seconds) % 60
                if secs:
                    return f"{mins}:{secs:02d}"
                return f"{mins} min"

        # Distance-based duration
        if "distance" in step or condition_type == "distance":
            meters = step.get("endConditionValue", 0)
            if not meters:
                meters = step.get("distance", {}).get("meters", 0)
            if meters:
                if meters >= 1000:
                    return f"{meters/1000:.1f} km"
                else:
                    return f"{int(meters)} m"

        # Lap button
        if condition_type == "lap.button":
            return "Lap Button"

        return ""

    def _format_step_target(self, step: dict) -> str:
        """Format step target for text display."""
        target = step.get("targetType", {})
        if isinstance(target, dict):
            target_type = target.get("workoutTargetTypeKey", "")
        else:
            target_type = ""

        # Heart rate zone
        if target_type == "heart.rate.zone" or "targetValueOne" in step:
            zone = step.get("zoneNumber") or step.get("targetValueOne")
            if zone:
                return f"HR Zone {int(zone)}"

        # Pace target
        if target_type == "pace.zone" or "targetPaceLow" in step:
            low = step.get("targetValueLow") or step.get("targetPaceLow")
            high = step.get("targetValueHigh") or step.get("targetPaceHigh")
            if low and high:
                # Convert m/s to min/km
                def mps_to_pace(mps):
                    if mps <= 0:
                        return "?"
                    pace_sec = 1000 / mps
                    mins = int(pace_sec) // 60
                    secs = int(pace_sec) % 60
                    return f"{mins}:{secs:02d}"

                return f"Pace: {mps_to_pace(high)} - {mps_to_pace(low)} /km"

        return ""
