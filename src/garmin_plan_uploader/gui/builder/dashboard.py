"""Training load dashboard for visualizing training plan metrics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .models import BuilderWorkout

from .calendar_grid import estimate_workout_duration, WeekMeta

logger = logging.getLogger(__name__)


@dataclass
class WeekStats:
    """Statistics for a single training week."""

    week_number: int
    total_minutes: int
    workout_count: int
    is_recovery: bool = False
    phase_label: str = ""


class VolumeBarWidget(QWidget):
    """Widget displaying a vertical bar chart of weekly volume."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._week_stats: list[WeekStats] = []
        self._max_minutes: int = 0
        self.setMinimumHeight(180)
        self.setMinimumWidth(400)

    def set_data(self, week_stats: list[WeekStats]) -> None:
        """Set the weekly stats data."""
        self._week_stats = week_stats
        self._max_minutes = max((s.total_minutes for s in week_stats), default=1)
        if self._max_minutes == 0:
            self._max_minutes = 1
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the bar chart."""
        if not self._week_stats:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dimensions
        margin_left = 50
        margin_right = 20
        margin_top = 20
        margin_bottom = 40
        chart_width = self.width() - margin_left - margin_right
        chart_height = self.height() - margin_top - margin_bottom

        num_weeks = len(self._week_stats)
        if num_weeks == 0:
            return

        bar_width = max(15, min(40, chart_width // num_weeks - 5))
        bar_spacing = (chart_width - bar_width * num_weeks) // max(1, num_weeks - 1) if num_weeks > 1 else 0

        # Draw y-axis labels
        painter.setPen(QPen(self.palette().text().color(), 1))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        # Draw a few y-axis labels
        for i in range(5):
            y_val = i * self._max_minutes // 4
            y_pos = margin_top + chart_height - (y_val / self._max_minutes * chart_height)
            hours = y_val // 60
            mins = y_val % 60
            label = f"{hours}h" if mins == 0 else f"{hours}:{mins:02d}"
            painter.drawText(5, int(y_pos) + 4, label)

        # Draw bars
        for i, stats in enumerate(self._week_stats):
            x = margin_left + i * (bar_width + bar_spacing)
            bar_height = (stats.total_minutes / self._max_minutes) * chart_height
            y = margin_top + chart_height - bar_height

            # Choose color
            if stats.is_recovery:
                color = QColor(76, 175, 80)  # Green for recovery
            else:
                # Gradient based on load (blue to orange to red)
                load_ratio = stats.total_minutes / self._max_minutes
                if load_ratio < 0.5:
                    color = QColor(33, 150, 243)  # Blue - light
                elif load_ratio < 0.75:
                    color = QColor(255, 152, 0)  # Orange - moderate
                else:
                    color = QColor(244, 67, 54)  # Red - high

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawRect(int(x), int(y), int(bar_width), int(bar_height))

            # Week label
            painter.setPen(QPen(self.palette().text().color(), 1))
            painter.drawText(int(x), int(margin_top + chart_height + 15), f"W{stats.week_number}")

            # Volume label on top of bar
            if bar_height > 15:
                hours = stats.total_minutes // 60
                mins = stats.total_minutes % 60
                vol_text = f"{hours}h" if mins == 0 else f"{hours}:{mins:02d}"
                painter.drawText(int(x), int(y) - 5, vol_text)

        painter.end()


class DashboardWidget(QWidget):
    """Training load dashboard showing plan metrics and visualization."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._weeks: list[list["BuilderWorkout | None"]] = []
        self._week_meta: list[WeekMeta] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dashboard UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        title = QLabel("📊 Training Dashboard")
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # Summary cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        self.total_weeks_card = self._create_stat_card("Total Weeks", "0")
        cards_layout.addWidget(self.total_weeks_card)

        self.total_workouts_card = self._create_stat_card("Total Workouts", "0")
        cards_layout.addWidget(self.total_workouts_card)

        self.total_time_card = self._create_stat_card("Total Time", "0h 0m")
        cards_layout.addWidget(self.total_time_card)

        self.avg_weekly_card = self._create_stat_card("Avg. Weekly", "0h 0m")
        cards_layout.addWidget(self.avg_weekly_card)

        self.peak_week_card = self._create_stat_card("Peak Week", "-")
        cards_layout.addWidget(self.peak_week_card)

        layout.addLayout(cards_layout)

        # Volume chart
        chart_group = QGroupBox("Weekly Volume")
        chart_layout = QVBoxLayout(chart_group)

        self.volume_chart = VolumeBarWidget()
        chart_layout.addWidget(self.volume_chart)

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()
        legend_layout.addWidget(self._create_legend_item(QColor(33, 150, 243), "Light"))
        legend_layout.addWidget(self._create_legend_item(QColor(255, 152, 0), "Moderate"))
        legend_layout.addWidget(self._create_legend_item(QColor(244, 67, 54), "High"))
        legend_layout.addWidget(self._create_legend_item(QColor(76, 175, 80), "Recovery"))
        legend_layout.addStretch()
        chart_layout.addLayout(legend_layout)

        layout.addWidget(chart_group)

        # Phase breakdown
        phase_group = QGroupBox("Training Phases")
        phase_layout = QVBoxLayout(phase_group)
        self.phase_breakdown_label = QLabel("No phases defined.")
        self.phase_breakdown_label.setWordWrap(True)
        phase_layout.addWidget(self.phase_breakdown_label)
        layout.addWidget(phase_group)

        # Notes preview
        notes_group = QGroupBox("Week Notes")
        notes_layout = QVBoxLayout(notes_group)
        notes_scroll = QScrollArea()
        notes_scroll.setWidgetResizable(True)
        notes_scroll.setMaximumHeight(120)
        self.notes_content = QWidget()
        self.notes_layout = QVBoxLayout(self.notes_content)
        self.notes_layout.setSpacing(5)
        notes_scroll.setWidget(self.notes_content)
        notes_layout.addWidget(notes_scroll)
        layout.addWidget(notes_group)

        layout.addStretch()

    def _create_stat_card(self, label: str, value: str) -> QFrame:
        """Create a stats card widget."""
        card = QFrame()
        card.setFrameStyle(QFrame.Shape.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                border-radius: 8px;
                padding: 10px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)

        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        font = value_label.font()
        font.setPointSize(18)
        font.setBold(True)
        value_label.setFont(font)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_label)

        label_widget = QLabel(label)
        label_widget.setStyleSheet("opacity: 0.7;")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(label_widget)

        # Store reference to value label for updating
        card.value_label = value_label  # type: ignore

        return card

    def _create_legend_item(self, color: QColor, text: str) -> QWidget:
        """Create a legend item."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        color_box = QFrame()
        color_box.setFixedSize(16, 16)
        color_box.setStyleSheet(f"background-color: {color.name()}; border-radius: 3px;")
        layout.addWidget(color_box)

        label = QLabel(text)
        label.setStyleSheet("opacity: 0.8;")
        layout.addWidget(label)

        return widget

    def update_data(
        self,
        weeks: list[list["BuilderWorkout | None"]],
        week_meta: list[WeekMeta] | None = None,
    ) -> None:
        """Update the dashboard with new data."""
        self._weeks = weeks
        self._week_meta = week_meta or [WeekMeta() for _ in weeks]

        # Ensure meta matches weeks
        while len(self._week_meta) < len(self._weeks):
            self._week_meta.append(WeekMeta())

        # Calculate stats
        week_stats: list[WeekStats] = []
        total_minutes = 0
        total_workouts = 0
        peak_week = 0
        peak_minutes = 0

        for i, week in enumerate(self._weeks):
            meta = self._week_meta[i] if i < len(self._week_meta) else WeekMeta()
            week_minutes = 0
            week_workout_count = 0

            for workout in week:
                if workout:
                    week_workout_count += 1
                    week_minutes += estimate_workout_duration(workout)

            stats = WeekStats(
                week_number=i + 1,
                total_minutes=week_minutes,
                workout_count=week_workout_count,
                is_recovery=meta.is_recovery_week,
                phase_label=meta.label,
            )
            week_stats.append(stats)

            total_minutes += week_minutes
            total_workouts += week_workout_count

            if week_minutes > peak_minutes:
                peak_minutes = week_minutes
                peak_week = i + 1

        # Update cards
        self.total_weeks_card.value_label.setText(str(len(self._weeks)))  # type: ignore
        self.total_workouts_card.value_label.setText(str(total_workouts))  # type: ignore

        hours = total_minutes // 60
        mins = total_minutes % 60
        self.total_time_card.value_label.setText(f"{hours}h {mins}m")  # type: ignore

        if self._weeks:
            avg_minutes = total_minutes // len(self._weeks)
            avg_hours = avg_minutes // 60
            avg_mins = avg_minutes % 60
            self.avg_weekly_card.value_label.setText(f"{avg_hours}h {avg_mins}m")  # type: ignore
        else:
            self.avg_weekly_card.value_label.setText("0h 0m")  # type: ignore

        if peak_week > 0:
            peak_hours = peak_minutes // 60
            peak_mins = peak_minutes % 60
            self.peak_week_card.value_label.setText(f"W{peak_week}: {peak_hours}h {peak_mins}m")  # type: ignore
        else:
            self.peak_week_card.value_label.setText("-")  # type: ignore

        # Update chart
        self.volume_chart.set_data(week_stats)

        # Update phase breakdown
        phases: dict[str, int] = {}
        for meta in self._week_meta:
            if meta.label:
                phases[meta.label] = phases.get(meta.label, 0) + 1

        if phases:
            breakdown = " • ".join(f"{label}: {count}wk" for label, count in phases.items())
            self.phase_breakdown_label.setText(breakdown)
        else:
            self.phase_breakdown_label.setText("No phases defined. Click on 'Phase' column in calendar to add labels.")

        # Update notes preview
        # Clear existing notes
        while self.notes_layout.count() > 0:
            child = self.notes_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        notes_found = False
        for i, meta in enumerate(self._week_meta):
            if meta.notes:
                notes_found = True
                note_label = QLabel(f"<b>Week {i + 1}:</b> {meta.notes}")
                note_label.setWordWrap(True)
                self.notes_layout.addWidget(note_label)

        if not notes_found:
            self.notes_layout.addWidget(QLabel("No notes added yet."))

        self.notes_layout.addStretch()
