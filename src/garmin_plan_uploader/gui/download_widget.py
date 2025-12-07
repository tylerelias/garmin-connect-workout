"""Download widget for exporting activities from Garmin Connect."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..workout_service import DownloadResult, WorkoutService
from .workers import DownloadWorker, run_worker

logger = logging.getLogger(__name__)


class DownloadWidget(QWidget):
    """Widget for downloading activities from Garmin Connect."""

    # Signals
    download_started = Signal()
    download_finished = Signal(object)  # DownloadResult

    def __init__(
        self,
        service: WorkoutService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self._worker = None
        self._thread = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the download form UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Date range group
        date_group = QGroupBox("Date Range")
        date_layout = QHBoxLayout(date_group)

        date_layout.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(date.today() - timedelta(days=30))
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.start_date_edit)

        date_layout.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.end_date_edit)

        date_layout.addStretch()

        # Quick range buttons
        self.week_btn = QPushButton("Last Week")
        self.week_btn.clicked.connect(self._on_last_week)
        date_layout.addWidget(self.week_btn)

        self.month_btn = QPushButton("Last Month")
        self.month_btn.clicked.connect(self._on_last_month)
        date_layout.addWidget(self.month_btn)

        self.year_btn = QPushButton("Last Year")
        self.year_btn.clicked.connect(self._on_last_year)
        date_layout.addWidget(self.year_btn)

        layout.addWidget(date_group)

        # Filter group
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Activity Type:"))
        self.activity_type_combo = QComboBox()
        self.activity_type_combo.addItems([
            "All Activities",
            "running",
            "cycling",
            "swimming",
            "hiking",
            "walking",
            "strength_training",
            "yoga",
        ])
        self.activity_type_combo.setMinimumWidth(150)
        filter_layout.addWidget(self.activity_type_combo)

        filter_layout.addStretch()

        self.include_planned_checkbox = QCheckBox("Include scheduled workouts")
        self.include_planned_checkbox.setToolTip(
            "Also download FIT files for planned workouts on your calendar"
        )
        filter_layout.addWidget(self.include_planned_checkbox)

        layout.addWidget(filter_group)

        # Output folder group
        output_group = QGroupBox("Output Folder")
        output_layout = QHBoxLayout(output_group)

        self.output_path_input = QLineEdit()
        self.output_path_input.setPlaceholderText("Select output folder...")
        self.output_path_input.setReadOnly(True)
        output_layout.addWidget(self.output_path_input)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        output_layout.addWidget(self.browse_btn)

        layout.addWidget(output_group)

        # Info label
        self.info_label = QLabel(
            "Downloads will include:\n"
            "• JSON metadata for each activity\n"
            "• Original FIT files (as .zip)\n"
            "• GPX tracks for activities with GPS data"
        )
        self.info_label.setStyleSheet("opacity: 0.8;")
        layout.addWidget(self.info_label)

        # Progress section
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Action buttons
        button_layout = QHBoxLayout()

        button_layout.addStretch()

        self.download_btn = QPushButton("Download Activities")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.setStyleSheet(
            "QPushButton { background-color: #2196f3; color: white; font-weight: bold; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1976d2; }"
            "QPushButton:disabled { background-color: rgba(128, 128, 128, 0.3); color: rgba(255, 255, 255, 0.5); }"
        )
        self.download_btn.clicked.connect(self._on_download_clicked)
        button_layout.addWidget(self.download_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        layout.addStretch()

        # Set default output path
        self._update_default_output_path()

    def _update_default_output_path(self) -> None:
        """Update the default output path based on date range."""
        start = self.start_date_edit.date().toPython()
        end = self.end_date_edit.date().toPython()
        default_path = Path.cwd() / "workouts" / f"{start}_{end}"
        self.output_path_input.setText(str(default_path))

    def _on_last_week(self) -> None:
        """Set date range to last week."""
        today = date.today()
        self.start_date_edit.setDate(today - timedelta(days=7))
        self.end_date_edit.setDate(today)
        self._update_default_output_path()

    def _on_last_month(self) -> None:
        """Set date range to last month."""
        today = date.today()
        self.start_date_edit.setDate(today - timedelta(days=30))
        self.end_date_edit.setDate(today)
        self._update_default_output_path()

    def _on_last_year(self) -> None:
        """Set date range to last year."""
        today = date.today()
        self.start_date_edit.setDate(today - timedelta(days=365))
        self.end_date_edit.setDate(today)
        self._update_default_output_path()

    def _on_browse_clicked(self) -> None:
        """Open folder dialog."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(Path.cwd()),
        )
        if folder:
            self.output_path_input.setText(folder)

    def _on_download_clicked(self) -> None:
        """Start the download process."""
        output_path = self.output_path_input.text()
        if not output_path:
            QMessageBox.warning(
                self,
                "No Output Folder",
                "Please select an output folder.",
            )
            return

        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()

        if start_date > end_date:
            QMessageBox.warning(
                self,
                "Invalid Date Range",
                "Start date must be before end date.",
            )
            return

        # Get activity type filter
        activity_type = self.activity_type_combo.currentText()
        if activity_type == "All Activities":
            activity_type = None

        self._start_download(
            start_date,
            end_date,
            Path(output_path),
            activity_type,
            self.include_planned_checkbox.isChecked(),
        )

    def _start_download(
        self,
        start_date: date,
        end_date: date,
        output_dir: Path,
        activity_type: str | None,
        include_planned: bool,
    ) -> None:
        """Start the download in a background thread."""
        self._set_downloading(True)
        self.download_started.emit()

        self._worker = DownloadWorker(
            self.service,
            start_date,
            end_date,
            output_dir,
            activity_type=activity_type,
            include_planned=include_planned,
        )
        self._worker.progress.connect(self._on_download_progress)
        self._worker.success.connect(self._on_download_success)
        self._worker.error.connect(self._on_download_error)
        self._worker.finished.connect(lambda: self._set_downloading(False))

        self._thread = run_worker(self._worker)

    def _set_downloading(self, downloading: bool) -> None:
        """Update UI for download state."""
        self.start_date_edit.setEnabled(not downloading)
        self.end_date_edit.setEnabled(not downloading)
        self.activity_type_combo.setEnabled(not downloading)
        self.include_planned_checkbox.setEnabled(not downloading)
        self.browse_btn.setEnabled(not downloading)
        self.week_btn.setEnabled(not downloading)
        self.month_btn.setEnabled(not downloading)
        self.year_btn.setEnabled(not downloading)
        self.download_btn.setVisible(not downloading)
        self.cancel_btn.setVisible(downloading)
        self.progress_bar.setVisible(downloading)
        self.progress_label.setVisible(downloading)

        if downloading:
            self.progress_bar.setRange(0, 0)  # Indeterminate initially

    def _on_download_progress(self, current: int, total: int, message: str) -> None:
        """Update progress bar."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.progress_label.setText(message)

    def _on_download_success(self, result: DownloadResult) -> None:
        """Handle download completion."""
        self.download_finished.emit(result)

        if result.cancelled:
            QMessageBox.information(
                self,
                "Download Cancelled",
                f"Download cancelled.\n\n"
                f"Downloaded: {result.activities} activities\n"
                f"Files created: {result.files}",
            )
        elif result.errors:
            QMessageBox.warning(
                self,
                "Download Complete (with errors)",
                f"Download completed with some errors.\n\n"
                f"Activities: {result.activities}\n"
                f"Files: {result.files}\n"
                f"Distance: {result.total_distance_km:.1f} km\n"
                f"Duration: {result.total_duration_hours:.1f} hours\n\n"
                f"Errors:\n" + "\n".join(result.errors[:5]),
            )
        else:
            QMessageBox.information(
                self,
                "Download Complete",
                f"Successfully downloaded activities!\n\n"
                f"Activities: {result.activities}\n"
                f"Files created: {result.files}\n"
                f"Total distance: {result.total_distance_km:.1f} km\n"
                f"Total duration: {result.total_duration_hours:.1f} hours\n\n"
                f"Saved to: {self.output_path_input.text()}",
            )

    def _on_download_error(self, error: str) -> None:
        """Handle download error."""
        QMessageBox.critical(
            self,
            "Download Failed",
            f"Failed to download activities:\n\n{error}",
        )

    def _on_cancel_clicked(self) -> None:
        """Cancel the download."""
        if self._worker:
            self._worker.cancel()
            self.progress_label.setText("Cancelling...")
