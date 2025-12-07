"""Templates widget for managing workout templates in Garmin library."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from ..workout_service import DeleteResult, WorkoutService, WorkoutTemplate
from .workers import DeleteTemplatesWorker, FetchTemplatesWorker, run_worker

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TemplatesWidget(QWidget):
    """Widget for managing workout templates."""

    def __init__(
        self,
        service: WorkoutService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self._unused_templates: list[WorkoutTemplate] = []
        self._scheduled_templates: list[WorkoutTemplate] = []
        self._worker = None
        self._thread = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the templates UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Filter group
        filter_group = QGroupBox("Filter Templates")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Name contains:"))
        self.name_filter_input = QLineEdit()
        self.name_filter_input.setPlaceholderText("e.g., 10K, Interval, Easy...")
        self.name_filter_input.setMinimumWidth(200)
        filter_layout.addWidget(self.name_filter_input)

        self.fetch_btn = QPushButton("🔍 Search")
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        filter_layout.addWidget(self.fetch_btn)

        filter_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Refresh All")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        filter_layout.addWidget(self.refresh_btn)

        layout.addWidget(filter_group)

        # Templates table
        self.templates_table = QTableWidget()
        self.templates_table.setColumnCount(4)
        self.templates_table.setHorizontalHeaderLabels([
            "Select", "Name", "Type", "Status"
        ])
        self.templates_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.templates_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.templates_table.setMinimumHeight(300)
        layout.addWidget(self.templates_table)

        # Summary labels
        summary_layout = QHBoxLayout()

        self.total_label = QLabel("Total: 0 templates")
        summary_layout.addWidget(self.total_label)

        self.unused_label = QLabel("Unused: 0")
        self.unused_label.setStyleSheet("color: #4caf50;")
        summary_layout.addWidget(self.unused_label)

        self.scheduled_label = QLabel("Scheduled: 0")
        self.scheduled_label.setStyleSheet("color: #ff9800;")
        summary_layout.addWidget(self.scheduled_label)

        self.selected_label = QLabel("Selected: 0")
        summary_layout.addWidget(self.selected_label)

        summary_layout.addStretch()

        layout.addLayout(summary_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("opacity: 0.7;")
        layout.addWidget(self.status_label)

        # Selection buttons
        selection_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All Unused")
        self.select_all_btn.clicked.connect(self._on_select_all_unused)
        self.select_all_btn.setEnabled(False)
        selection_layout.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._on_select_none)
        self.select_none_btn.setEnabled(False)
        selection_layout.addWidget(self.select_none_btn)

        selection_layout.addStretch()

        self.include_scheduled_checkbox = QCheckBox("Allow selecting scheduled templates")
        self.include_scheduled_checkbox.setToolTip(
            "⚠️ DANGEROUS: Deleting scheduled templates will orphan calendar entries"
        )
        self.include_scheduled_checkbox.stateChanged.connect(self._on_include_scheduled_changed)
        selection_layout.addWidget(self.include_scheduled_checkbox)

        layout.addLayout(selection_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        button_layout.addStretch()

        self.delete_btn = QPushButton("🗑️ Delete Selected")
        self.delete_btn.setMinimumHeight(40)
        self.delete_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #d32f2f; }"
            "QPushButton:disabled { background-color: rgba(128, 128, 128, 0.3); color: rgba(255, 255, 255, 0.5); }"
        )
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Load templates on first show
        self._on_refresh_clicked()

    def _on_fetch_clicked(self) -> None:
        """Fetch templates with current filter."""
        name_filter = self.name_filter_input.text().strip() or None
        self._fetch_templates(name_filter)

    def _on_refresh_clicked(self) -> None:
        """Refresh all templates."""
        self.name_filter_input.clear()
        self._fetch_templates(None)

    def _fetch_templates(self, name_contains: str | None) -> None:
        """Fetch templates from Garmin."""
        self._set_loading(True)
        self.status_label.setText("Fetching templates...")

        self._worker = FetchTemplatesWorker(self.service, name_contains)
        self._worker.success.connect(self._on_fetch_success)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._worker.finished.connect(lambda: self._set_loading(False))

        self._thread = run_worker(self._worker)

    def _set_loading(self, loading: bool) -> None:
        """Update UI for loading state."""
        self.fetch_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.delete_btn.setEnabled(not loading and self._get_selected_count() > 0)
        self.progress_bar.setVisible(loading)

        if loading:
            self.progress_bar.setRange(0, 0)

    def _on_fetch_success(
        self,
        unused: list[WorkoutTemplate],
        scheduled: list[WorkoutTemplate],
    ) -> None:
        """Handle successful fetch."""
        self._unused_templates = unused
        self._scheduled_templates = scheduled

        self._populate_table()

        total = len(unused) + len(scheduled)
        self.total_label.setText(f"Total: {total} templates")
        self.unused_label.setText(f"Unused: {len(unused)}")
        self.scheduled_label.setText(f"Scheduled: {len(scheduled)}")
        self.status_label.setText(f"Found {total} templates")

        self.select_all_btn.setEnabled(len(unused) > 0)
        self.select_none_btn.setEnabled(total > 0)

    def _on_fetch_error(self, error: str) -> None:
        """Handle fetch error."""
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: #f44336;")
        QMessageBox.critical(self, "Error", f"Failed to fetch templates:\n\n{error}")

    def _populate_table(self) -> None:
        """Populate the table with templates."""
        self.templates_table.setRowCount(0)

        include_scheduled = self.include_scheduled_checkbox.isChecked()

        # Add unused templates first
        for template in self._unused_templates:
            self._add_template_row(template, is_scheduled=False)

        # Add scheduled templates if checkbox is checked
        if include_scheduled:
            for template in self._scheduled_templates:
                self._add_template_row(template, is_scheduled=True)

        self._update_selected_count()

    def _add_template_row(self, template: WorkoutTemplate, is_scheduled: bool) -> None:
        """Add a template row to the table."""
        row = self.templates_table.rowCount()
        self.templates_table.insertRow(row)

        # Checkbox
        checkbox = QCheckBox()
        checkbox.stateChanged.connect(self._update_selected_count)
        checkbox_widget = QWidget()
        checkbox_layout = QHBoxLayout(checkbox_widget)
        checkbox_layout.addWidget(checkbox)
        checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.templates_table.setCellWidget(row, 0, checkbox_widget)

        # Store template reference
        checkbox.setProperty("template", template)
        checkbox.setProperty("is_scheduled", is_scheduled)

        # Name
        name_item = QTableWidgetItem(template.name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.templates_table.setItem(row, 1, name_item)

        # Sport type
        type_item = QTableWidgetItem(template.sport_type)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.templates_table.setItem(row, 2, type_item)

        # Status
        if is_scheduled:
            status_item = QTableWidgetItem("📅 Scheduled")
            status_item.setForeground(Qt.GlobalColor.darkYellow)
        else:
            status_item = QTableWidgetItem("✓ Unused")
            status_item.setForeground(Qt.GlobalColor.darkGreen)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.templates_table.setItem(row, 3, status_item)

    def _get_checkbox_at_row(self, row: int) -> QCheckBox | None:
        """Get the checkbox widget at a table row."""
        widget = self.templates_table.cellWidget(row, 0)
        if widget:
            return widget.findChild(QCheckBox)
        return None

    def _get_selected_templates(self) -> list[WorkoutTemplate]:
        """Get list of selected templates."""
        selected = []
        for row in range(self.templates_table.rowCount()):
            checkbox = self._get_checkbox_at_row(row)
            if checkbox and checkbox.isChecked():
                template = checkbox.property("template")
                if template:
                    selected.append(template)
        return selected

    def _get_selected_count(self) -> int:
        """Get count of selected templates."""
        return len(self._get_selected_templates())

    def _update_selected_count(self) -> None:
        """Update the selected count label."""
        count = self._get_selected_count()
        self.selected_label.setText(f"Selected: {count}")
        self.delete_btn.setEnabled(count > 0)

    def _on_select_all_unused(self) -> None:
        """Select all unused templates."""
        for row in range(self.templates_table.rowCount()):
            checkbox = self._get_checkbox_at_row(row)
            if checkbox:
                is_scheduled = checkbox.property("is_scheduled")
                if not is_scheduled:
                    checkbox.setChecked(True)

    def _on_select_none(self) -> None:
        """Deselect all templates."""
        for row in range(self.templates_table.rowCount()):
            checkbox = self._get_checkbox_at_row(row)
            if checkbox:
                checkbox.setChecked(False)

    def _on_include_scheduled_changed(self, state: int) -> None:
        """Handle include scheduled checkbox change."""
        if state == Qt.CheckState.Checked.value:
            result = QMessageBox.warning(
                self,
                "Warning",
                "Including scheduled templates is dangerous!\n\n"
                "Deleting a template that is scheduled on your calendar will\n"
                "orphan those calendar entries (they won't have workout data).\n\n"
                "Are you sure you want to include scheduled templates?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                self.include_scheduled_checkbox.setChecked(False)
                return

        self._populate_table()

    def _on_delete_clicked(self) -> None:
        """Delete selected templates."""
        selected = self._get_selected_templates()
        if not selected:
            return

        # Check if any scheduled templates are selected
        scheduled_count = sum(
            1 for t in selected
            if t in self._scheduled_templates
        )

        if scheduled_count > 0:
            msg = (
                f"You are about to delete {len(selected)} templates,\n"
                f"including {scheduled_count} SCHEDULED template(s)!\n\n"
                f"⚠️ This will orphan {scheduled_count} calendar entries.\n\n"
                f"This cannot be undone. Continue?"
            )
        else:
            msg = (
                f"Delete {len(selected)} unused workout templates?\n\n"
                f"This cannot be undone."
            )

        result = QMessageBox.warning(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self._start_delete(selected)

    def _start_delete(self, templates: list[WorkoutTemplate]) -> None:
        """Start deleting templates."""
        self._set_deleting(True)
        self.progress_bar.setRange(0, len(templates))

        self._worker = DeleteTemplatesWorker(self.service, templates)
        self._worker.progress.connect(self._on_delete_progress)
        self._worker.success.connect(self._on_delete_success)
        self._worker.error.connect(self._on_delete_error)
        self._worker.finished.connect(lambda: self._set_deleting(False))

        self._thread = run_worker(self._worker)

    def _set_deleting(self, deleting: bool) -> None:
        """Update UI for delete state."""
        self.fetch_btn.setEnabled(not deleting)
        self.refresh_btn.setEnabled(not deleting)
        self.select_all_btn.setEnabled(not deleting)
        self.select_none_btn.setEnabled(not deleting)
        self.delete_btn.setVisible(not deleting)
        self.cancel_btn.setVisible(deleting)
        self.progress_bar.setVisible(deleting)
        self.templates_table.setEnabled(not deleting)

    def _on_delete_progress(self, current: int, total: int, message: str) -> None:
        """Update delete progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_delete_success(self, result: DeleteResult) -> None:
        """Handle delete completion."""
        if result.cancelled:
            QMessageBox.information(
                self,
                "Cancelled",
                f"Deleted {result.deleted} of {result.total} templates before cancellation.",
            )
        elif result.failed > 0:
            QMessageBox.warning(
                self,
                "Delete Complete (with errors)",
                f"Deleted {result.deleted} templates.\n"
                f"Failed: {result.failed}\n\n"
                f"Errors:\n" + "\n".join(result.errors[:5]),
            )
        else:
            QMessageBox.information(
                self,
                "Delete Complete",
                f"Successfully deleted {result.deleted} templates.",
            )

        # Refresh the list
        self._on_refresh_clicked()

    def _on_delete_error(self, error: str) -> None:
        """Handle delete error."""
        QMessageBox.critical(self, "Error", f"Failed to delete templates:\n\n{error}")

    def _on_cancel_clicked(self) -> None:
        """Cancel the delete operation."""
        if self._worker:
            self._worker.cancel()
            self.status_label.setText("Cancelling...")
