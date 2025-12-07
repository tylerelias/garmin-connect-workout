"""Upload widget with CSV preview and upload functionality."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..workout_service import UploadResult, WorkoutService
from .workers import UploadWorker, run_worker

if TYPE_CHECKING:
    from ..domain_models import Workout

logger = logging.getLogger(__name__)


class UploadWidget(QWidget):
    """Widget for uploading CSV training plans."""

    # Signals
    upload_started = Signal()
    upload_finished = Signal(object)  # UploadResult

    def __init__(
        self,
        service: WorkoutService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self._workouts: list[tuple[date, Workout]] = []
        self._worker = None
        self._thread = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the upload form UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # File selection group
        file_group = QGroupBox("Training Plan CSV")
        file_layout = QHBoxLayout(file_group)

        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Select a CSV file...")
        self.file_path_input.setReadOnly(True)
        file_layout.addWidget(self.file_path_input)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        file_layout.addWidget(self.browse_btn)

        layout.addWidget(file_group)

        # Date selection group
        date_group = QGroupBox("Start Date")
        date_layout = QHBoxLayout(date_group)

        date_label = QLabel("First day of Week 1 (should be Monday):")
        date_layout.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(date.today())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self._on_date_changed)
        date_layout.addWidget(self.date_edit)

        date_layout.addStretch()

        layout.addWidget(date_group)

        # Preview table
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Date", "Day", "Workout"])
        self.preview_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.preview_table.setMinimumHeight(200)
        preview_layout.addWidget(self.preview_table)

        self.preview_status = QLabel("")
        self.preview_status.setStyleSheet("opacity: 0.7;")
        preview_layout.addWidget(self.preview_status)

        layout.addWidget(preview_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Action buttons
        button_layout = QHBoxLayout()

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.clicked.connect(self._on_validate_clicked)
        self.validate_btn.setEnabled(False)
        button_layout.addWidget(self.validate_btn)

        button_layout.addStretch()

        self.upload_btn = QPushButton("Upload to Garmin")
        self.upload_btn.setMinimumHeight(40)
        self.upload_btn.setStyleSheet(
            "QPushButton { background-color: #2196f3; color: white; font-weight: bold; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1976d2; }"
            "QPushButton:disabled { background-color: rgba(128, 128, 128, 0.3); color: rgba(255, 255, 255, 0.5); }"
        )
        self.upload_btn.clicked.connect(self._on_upload_clicked)
        self.upload_btn.setEnabled(False)
        button_layout.addWidget(self.upload_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _on_browse_clicked(self) -> None:
        """Open file dialog to select CSV."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Training Plan CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )

        if file_path:
            self.file_path_input.setText(file_path)
            self._load_csv(Path(file_path))

    def _on_date_changed(self) -> None:
        """Reload CSV when date changes."""
        if self.file_path_input.text():
            self._load_csv(Path(self.file_path_input.text()))

    def _load_csv(self, csv_path: Path) -> None:
        """Load and parse CSV file."""
        try:
            start_date = self.date_edit.date().toPython()
            self._workouts = self.service.parse_csv(csv_path, start_date)
            self._update_preview()
            self.validate_btn.setEnabled(True)
            self.upload_btn.setEnabled(len(self._workouts) > 0)

        except Exception as e:
            logger.error(f"Failed to parse CSV: {e}")
            self._workouts = []
            self.preview_table.setRowCount(0)
            self.preview_status.setText(f"Error: {e}")
            self.preview_status.setStyleSheet("color: #f44336;")
            self.validate_btn.setEnabled(False)
            self.upload_btn.setEnabled(False)

    def _update_preview(self) -> None:
        """Update the preview table with parsed workouts."""
        self.preview_table.setRowCount(len(self._workouts))

        for row, (workout_date, workout) in enumerate(self._workouts):
            # Date
            date_item = QTableWidgetItem(workout_date.strftime("%Y-%m-%d"))
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.preview_table.setItem(row, 0, date_item)

            # Day of week
            day_item = QTableWidgetItem(workout_date.strftime("%A"))
            day_item.setFlags(day_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.preview_table.setItem(row, 1, day_item)

            # Workout name
            name_item = QTableWidgetItem(workout.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.preview_table.setItem(row, 2, name_item)

        # Update status
        self.preview_status.setText(f"Found {len(self._workouts)} workouts")
        self.preview_status.setStyleSheet("color: #4caf50;")

    def _on_validate_clicked(self) -> None:
        """Validate the CSV without uploading."""
        if not self._workouts:
            return

        # Show validation summary
        msg = f"Validation successful!\n\n"
        msg += f"Total workouts: {len(self._workouts)}\n"

        if self._workouts:
            first_date = self._workouts[0][0]
            last_date = self._workouts[-1][0]
            msg += f"Date range: {first_date} to {last_date}\n"

            # Count by day of week
            day_counts = {}
            for workout_date, _ in self._workouts:
                day_name = workout_date.strftime("%A")
                day_counts[day_name] = day_counts.get(day_name, 0) + 1

            msg += "\nWorkouts by day:\n"
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
                if day in day_counts:
                    msg += f"  {day}: {day_counts[day]}\n"

        QMessageBox.information(self, "Validation Result", msg)

    def _on_upload_clicked(self) -> None:
        """Start uploading workouts."""
        if not self._workouts:
            return

        # Confirm upload
        result = QMessageBox.question(
            self,
            "Confirm Upload",
            f"Upload {len(self._workouts)} workouts to Garmin Connect?\n\n"
            f"This will schedule them on your calendar.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self._start_upload()

    def _start_upload(self) -> None:
        """Start the upload process."""
        self._set_uploading(True)
        self.upload_started.emit()

        self._worker = UploadWorker(self.service, self._workouts)
        self._worker.progress.connect(self._on_upload_progress)
        self._worker.success.connect(self._on_upload_success)
        self._worker.error.connect(self._on_upload_error)
        self._worker.finished.connect(lambda: self._set_uploading(False))

        self._thread = run_worker(self._worker)

    def _set_uploading(self, uploading: bool) -> None:
        """Update UI for upload state."""
        self.browse_btn.setEnabled(not uploading)
        self.date_edit.setEnabled(not uploading)
        self.validate_btn.setEnabled(not uploading)
        self.upload_btn.setVisible(not uploading)
        self.cancel_btn.setVisible(uploading)
        self.progress_bar.setVisible(uploading)
        self.progress_label.setVisible(uploading)

        if uploading:
            self.progress_bar.setRange(0, len(self._workouts))
            self.progress_bar.setValue(0)

    def _on_upload_progress(self, current: int, total: int, message: str) -> None:
        """Update progress bar."""
        self.progress_bar.setValue(current)
        self.progress_label.setText(message)

    def _on_upload_success(self, result: UploadResult) -> None:
        """Handle upload completion."""
        self.upload_finished.emit(result)

        if result.cancelled:
            QMessageBox.information(
                self,
                "Upload Cancelled",
                f"Upload cancelled.\n\n"
                f"Uploaded: {result.uploaded} of {result.total} workouts",
            )
        elif result.failed > 0:
            QMessageBox.warning(
                self,
                "Upload Complete (with errors)",
                f"Upload completed with some errors.\n\n"
                f"Uploaded: {result.uploaded}\n"
                f"Failed: {result.failed}\n\n"
                f"Errors:\n" + "\n".join(result.errors[:5]),
            )
        else:
            QMessageBox.information(
                self,
                "Upload Complete",
                f"Successfully uploaded {result.uploaded} workouts to Garmin Connect!",
            )

    def _on_upload_error(self, error: str) -> None:
        """Handle upload error."""
        QMessageBox.critical(
            self,
            "Upload Failed",
            f"Failed to upload workouts:\n\n{error}",
        )

    def _on_cancel_clicked(self) -> None:
        """Cancel the upload."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")
