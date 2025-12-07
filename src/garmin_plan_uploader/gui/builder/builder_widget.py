"""Main builder widget combining all builder components."""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QFormLayout,
    QDateEdit,
    QCheckBox,
    QGroupBox,
)

from .calendar_grid import CalendarGridWidget, ProgressiveGeneratorDialog, WeekMeta
from .dashboard import DashboardWidget
from .models import BuilderWorkout, WorkoutTemplateData
from .step_editor import WorkoutEditorWidget
from .template_library import TemplateLibraryWidget

logger = logging.getLogger(__name__)


class CSVPreviewDialog(QDialog):
    """Dialog for previewing CSV export."""

    def __init__(self, csv_content: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.csv_content = csv_content
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("CSV Preview")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Preview of CSV content:"))

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(self.csv_content)
        self.text_edit.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.text_edit)

        button_box = QDialogButtonBox()
        save_btn = button_box.addButton("Save As...", QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.clicked.connect(self.accept)
        cancel_btn = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_box)


class ExportOptionsDialog(QDialog):
    """Dialog for selecting export options."""

    def __init__(self, num_weeks: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.num_weeks = num_weeks
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Export Options")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Export format
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout(format_group)

        self.csv_radio = QCheckBox("CSV (for Garmin upload)")
        self.csv_radio.setChecked(True)
        format_layout.addWidget(self.csv_radio)

        self.ical_radio = QCheckBox("iCal (.ics) for calendar sync")
        format_layout.addWidget(self.ical_radio)

        self.pdf_radio = QCheckBox("PDF (printable plan) - Coming soon")
        self.pdf_radio.setEnabled(False)
        format_layout.addWidget(self.pdf_radio)

        layout.addWidget(format_group)

        # Date settings
        date_group = QGroupBox("Date Settings (for iCal)")
        date_layout = QFormLayout(date_group)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(date.today())
        self.start_date_edit.setCalendarPopup(True)
        date_layout.addRow("Start Date (Week 1 Monday):", self.start_date_edit)

        layout.addWidget(date_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def export_csv(self) -> bool:
        return self.csv_radio.isChecked()

    def export_ical(self) -> bool:
        return self.ical_radio.isChecked()

    def get_start_date(self) -> date:
        return self.start_date_edit.date().toPython()


class BuilderWidget(QWidget):
    """Main workout builder widget with template library, calendar, and editor."""

    # Signal to request switching to upload tab with a file
    export_and_upload = Signal(str)  # file path
    # Signal when export is ready for upload
    request_upload = Signal(str)  # CSV content

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._selected_week: int = 0
        self._selected_day: int = 0
        self._service = None  # WorkoutService, set after login
        self._sync_status: dict[tuple[int, int], str] = {}  # (week, day) -> status
        self._setup_ui()

    def set_service(self, service) -> None:
        """Set the workout service after login."""
        self._service = service
        self._update_sync_controls()

    def _update_sync_controls(self) -> None:
        """Update sync-related UI elements based on login state."""
        logged_in = self._service is not None
        self.sync_btn.setEnabled(logged_in)
        self.upload_btn.setEnabled(logged_in)
        if not logged_in:
            self.sync_btn.setToolTip("Login required to sync with Garmin")
            self.upload_btn.setToolTip("Login required to upload")
        else:
            self.sync_btn.setToolTip("Check sync status with Garmin")
            self.upload_btn.setToolTip("Upload plan to Garmin Connect")

    def _setup_ui(self) -> None:
        """Create the builder UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Toolbar
        toolbar_layout = QHBoxLayout()

        new_btn = QPushButton("📄 New")
        new_btn.clicked.connect(self._on_new)
        toolbar_layout.addWidget(new_btn)

        import_btn = QPushButton("📥 Import CSV")
        import_btn.clicked.connect(self._on_import_csv)
        toolbar_layout.addWidget(import_btn)

        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self._on_export)
        toolbar_layout.addWidget(export_btn)

        toolbar_layout.addStretch()

        # Sync and Upload buttons (require login)
        self.sync_btn = QPushButton("🔄 Check Sync")
        self.sync_btn.clicked.connect(self._on_check_sync)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setToolTip("Login required to sync with Garmin")
        toolbar_layout.addWidget(self.sync_btn)

        self.upload_btn = QPushButton("☁️ Upload to Garmin")
        self.upload_btn.clicked.connect(self._on_upload_to_garmin)
        self.upload_btn.setEnabled(False)
        self.upload_btn.setToolTip("Login required to upload")
        toolbar_layout.addWidget(self.upload_btn)

        toolbar_layout.addStretch()

        save_template_btn = QPushButton("💾 Save as Template")
        save_template_btn.clicked.connect(self._on_save_template)
        toolbar_layout.addWidget(save_template_btn)

        generate_btn = QPushButton("🔄 Generate Progressive")
        generate_btn.clicked.connect(self._on_generate_progressive)
        toolbar_layout.addWidget(generate_btn)

        add_to_calendar_btn = QPushButton("➕ Add to Calendar")
        add_to_calendar_btn.clicked.connect(self._on_add_to_calendar)
        toolbar_layout.addWidget(add_to_calendar_btn)

        layout.addLayout(toolbar_layout)

        # Tab widget for calendar vs dashboard view
        self.view_tabs = QTabWidget()
        self.view_tabs.setTabPosition(QTabWidget.TabPosition.South)

        # Calendar view (main content)
        calendar_container = QWidget()
        calendar_layout = QHBoxLayout(calendar_container)
        calendar_layout.setContentsMargins(0, 0, 0, 0)

        # Main content with splitter
        splitter = QSplitter()

        # Left panel: Template library
        self.template_library = TemplateLibraryWidget()
        self.template_library.template_double_clicked.connect(self._on_template_selected)
        self.template_library.setMinimumWidth(200)
        self.template_library.setMaximumWidth(300)
        splitter.addWidget(self.template_library)

        # Center panel: Calendar grid
        self.calendar_grid = CalendarGridWidget()
        self.calendar_grid.workout_selected.connect(self._on_calendar_selection)
        self.calendar_grid.workout_double_clicked.connect(self._on_calendar_double_click)
        self.calendar_grid.setMinimumWidth(400)
        splitter.addWidget(self.calendar_grid)

        # Right panel: Workout editor
        self.workout_editor = WorkoutEditorWidget()
        self.workout_editor.setMinimumWidth(350)
        splitter.addWidget(self.workout_editor)

        # Set splitter sizes
        splitter.setSizes([200, 500, 400])

        calendar_layout.addWidget(splitter)
        self.view_tabs.addTab(calendar_container, "📅 Calendar")

        # Dashboard view
        self.dashboard = DashboardWidget()
        self.view_tabs.addTab(self.dashboard, "📊 Dashboard")

        # Connect tab changes to refresh dashboard
        self.view_tabs.currentChanged.connect(self._on_view_tab_changed)

        layout.addWidget(self.view_tabs)

    def _on_new(self) -> None:
        """Create a new empty plan."""
        result = QMessageBox.question(
            self,
            "New Plan",
            "Create a new empty plan?\n\nThis will clear the current calendar.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.calendar_grid.set_all_workouts([[None] * 7])
            self.workout_editor.clear()

    def _on_view_tab_changed(self, index: int) -> None:
        """Handle view tab changes."""
        if index == 1:  # Dashboard tab
            self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        """Update the dashboard with current calendar data."""
        weeks = self.calendar_grid.get_all_workouts()
        week_meta = self.calendar_grid._week_meta  # Access internal meta
        self.dashboard.update_data(weeks, week_meta)

    def _on_import_csv(self) -> None:
        """Import a CSV training plan."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            self._import_csv_file(file_path)
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {file_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import CSV:\n\n{e}",
            )

    def _import_csv_file(self, file_path: str) -> None:
        """Parse and import a CSV file."""
        from ...csv_parser import parse_training_plan

        # Use existing parser to get workouts
        workouts = parse_training_plan(Path(file_path))

        if not workouts:
            raise ValueError("No workouts found in CSV")

        # Convert to builder format
        # We need to re-read the CSV to get the raw cell content
        weeks: list[list[BuilderWorkout | None]] = []

        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                week_data: list[BuilderWorkout | None] = [None] * 7

                for day_idx, day_name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
                    # Try different case variations
                    cell = None
                    for key in [day_name, day_name.lower(), day_name.upper()]:
                        if key in row and row[key].strip():
                            cell = row[key].strip()
                            break

                    if cell:
                        # Parse the cell to extract workout name
                        lines = cell.split("\n")
                        if lines:
                            first_line = lines[0].strip()
                            if ":" in first_line:
                                # Format: "running: Workout Name"
                                name = first_line.split(":", 1)[1].strip()
                            else:
                                name = first_line

                            # Create a simple BuilderWorkout with the name
                            # Full step parsing would require more complex logic
                            workout = BuilderWorkout(name=name)
                            # Store the raw CSV content for now
                            workout._raw_csv = cell
                            week_data[day_idx] = workout

                weeks.append(week_data)

        self.calendar_grid.set_all_workouts(weeks)

    def _on_export(self) -> None:
        """Show export options dialog."""
        num_weeks = self.calendar_grid.get_week_count()
        dialog = ExportOptionsDialog(num_weeks, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        exported_any = False

        # Export CSV
        if dialog.export_csv():
            if self._export_csv():
                exported_any = True

        # Export iCal
        if dialog.export_ical():
            start_date = dialog.get_start_date()
            if self._export_ical(start_date):
                exported_any = True

        if not exported_any:
            QMessageBox.information(
                self,
                "Export",
                "No files were exported.",
            )

    def _export_csv(self) -> bool:
        """Export the calendar to CSV."""
        csv_content = self.calendar_grid.to_csv()

        if not csv_content.strip():
            QMessageBox.warning(
                self,
                "Export",
                "No workouts to export.",
            )
            return False

        dialog = CSVPreviewDialog(csv_content, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save CSV",
                "training_plan.csv",
                "CSV Files (*.csv);;All Files (*)",
            )
            if file_path:
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    f.write(csv_content)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Saved to {file_path}",
                )
                return True
        return False

    def _export_ical(self, start_date: date) -> bool:
        """Export the calendar to iCal format."""
        weeks = self.calendar_grid.get_all_workouts()

        # Build iCal content
        ical_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Garmin Plan Uploader//Training Plan//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Training Plan",
        ]

        # Find the Monday of the start week
        days_since_monday = start_date.weekday()
        week_start = start_date - timedelta(days=days_since_monday)

        event_count = 0
        for week_idx, week in enumerate(weeks):
            for day_idx, workout in enumerate(week):
                if workout:
                    event_date = week_start + timedelta(weeks=week_idx, days=day_idx)
                    event_count += 1

                    # Create event
                    ical_lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:workout-{week_idx}-{day_idx}@garmin-plan-uploader",
                        f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z",
                        f"DTSTART:{event_date.strftime('%Y%m%d')}",
                        f"DTEND:{event_date.strftime('%Y%m%d')}",
                        f"SUMMARY:🏃 {workout.name}",
                        f"DESCRIPTION:{self._workout_to_description(workout)}",
                        "END:VEVENT",
                    ])

        ical_lines.append("END:VCALENDAR")

        if event_count == 0:
            QMessageBox.warning(
                self,
                "Export",
                "No workouts to export to iCal.",
            )
            return False

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save iCal",
            "training_plan.ics",
            "iCal Files (*.ics);;All Files (*)",
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(ical_lines))
            QMessageBox.information(
                self,
                "Export Complete",
                f"Saved {event_count} events to {file_path}",
            )
            return True
        return False

    def _workout_to_description(self, workout: BuilderWorkout) -> str:
        """Convert workout to plain text description for iCal."""
        from .calendar_grid import estimate_workout_duration

        lines = [workout.name]
        duration = estimate_workout_duration(workout)
        if duration > 0:
            lines.append(f"Duration: ~{duration} minutes")

        if workout.steps:
            lines.append("")
            lines.append("Steps:")
            for step in workout.steps:
                step_desc = f"- {step.step_type.value.capitalize()}"
                if step.duration:
                    step_desc += f" for {step.duration.value}"
                if step.target and step.target.value:
                    step_desc += f" @ {step.target.value}"
                lines.append(step_desc)

        return "\\n".join(lines)

    def _on_save_template(self) -> None:
        """Save current editor workout as a template."""
        workout = self.workout_editor.get_workout()
        if workout.is_empty():
            QMessageBox.warning(
                self,
                "Save Template",
                "Add some steps to the workout before saving as a template.",
            )
            return

        if self.template_library.save_template(workout):
            QMessageBox.information(
                self,
                "Template Saved",
                f"Template '{workout.name}' saved successfully.",
            )

    def _on_generate_progressive(self) -> None:
        """Open the progressive workout generator."""
        workout = self.workout_editor.get_workout()
        if workout.is_empty():
            QMessageBox.warning(
                self,
                "Generate Progressive",
                "Create a base workout first, then generate progressive versions.",
            )
            return

        dialog = ProgressiveGeneratorDialog(workout, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for week, day, gen_workout in dialog.get_generated_workouts():
                self.calendar_grid.set_workout(week, day, gen_workout)

    def _on_add_to_calendar(self) -> None:
        """Add the current editor workout to the selected calendar cell."""
        workout = self.workout_editor.get_workout()
        if workout.is_empty():
            QMessageBox.warning(
                self,
                "Add to Calendar",
                "Create a workout with steps before adding to the calendar.",
            )
            return

        self.calendar_grid.set_workout(
            self._selected_week,
            self._selected_day,
            workout,
        )

    def _on_template_selected(self, template: WorkoutTemplateData) -> None:
        """Handle template selection from library."""
        self.workout_editor.set_workout(template.workout.copy())

    def _on_calendar_selection(self, week: int, day: int) -> None:
        """Handle calendar cell selection."""
        self._selected_week = week
        self._selected_day = day

    def _on_calendar_double_click(
        self,
        week: int,
        day: int,
        workout: BuilderWorkout | None,
    ) -> None:
        """Handle calendar cell double-click."""
        self._selected_week = week
        self._selected_day = day
        if workout:
            self.workout_editor.set_workout(workout)

    def _on_check_sync(self) -> None:
        """Check sync status with Garmin Connect."""
        if not self._service:
            return

        # Get scheduled workouts from Garmin
        from PySide6.QtCore import QThread, Signal as QtSignal
        from PySide6.QtWidgets import QProgressDialog

        progress = QProgressDialog("Checking sync status...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        try:
            # Get the next 90 days of scheduled workouts from Garmin
            from datetime import date, timedelta

            start = date.today()
            end = start + timedelta(days=90)

            # This would need to call the Garmin API
            # For now, show a placeholder message
            progress.close()

            QMessageBox.information(
                self,
                "Sync Status",
                "Sync status checking is a preview feature.\n\n"
                "To upload your plan to Garmin:\n"
                "1. Click 'Upload to Garmin'\n"
                "2. Select a start date\n"
                "3. Your workouts will be scheduled on Garmin Connect",
            )
        except Exception as e:
            progress.close()
            logger.exception("Error checking sync status")
            QMessageBox.critical(
                self,
                "Sync Error",
                f"Failed to check sync status:\n\n{e}",
            )

    def _on_upload_to_garmin(self) -> None:
        """Upload the current plan directly to Garmin Connect."""
        if not self._service:
            return

        weeks = self.calendar_grid.get_all_workouts()
        workout_count = sum(1 for week in weeks for w in week if w)

        if workout_count == 0:
            QMessageBox.warning(
                self,
                "Upload",
                "No workouts to upload. Add workouts to the calendar first.",
            )
            return

        # Ask for start date
        dialog = UploadScheduleDialog(workout_count, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        start_date = dialog.get_start_date()

        # Export to CSV and signal for upload
        csv_content = self.calendar_grid.to_csv()

        # Save to temp file and emit signal
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(csv_content)
            temp_path = f.name

        # Emit signal to switch to upload tab
        self.export_and_upload.emit(temp_path)

        QMessageBox.information(
            self,
            "Ready for Upload",
            f"Plan exported with {workout_count} workouts.\n\n"
            f"Switch to the Upload tab to complete the upload process.",
        )


class UploadScheduleDialog(QDialog):
    """Dialog for selecting upload schedule."""

    def __init__(self, workout_count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.workout_count = workout_count
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Schedule Workouts")
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(
            f"<b>{self.workout_count} workouts</b> will be scheduled on Garmin Connect."
        )
        layout.addWidget(info_label)

        # Date settings
        form = QFormLayout()

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(date.today())
        self.start_date_edit.setCalendarPopup(True)
        form.addRow("Start Date (Week 1 Monday):", self.start_date_edit)

        layout.addLayout(form)

        # Note
        note_label = QLabel(
            "<i>Note: Workouts will be scheduled based on their day position "
            "in the calendar (Monday-Sunday).</i>"
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("opacity: 0.7;")
        layout.addWidget(note_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_start_date(self) -> date:
        return self.start_date_edit.date().toPython()
