"""Template library widget for workout templates."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import BuilderWorkout, TemplateStore, WorkoutTemplateData

logger = logging.getLogger(__name__)


class TemplateLibraryWidget(QWidget):
    """Widget for browsing and managing workout templates."""

    template_selected = Signal(object)  # WorkoutTemplateData
    template_double_clicked = Signal(object)  # WorkoutTemplateData

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = TemplateStore()
        self._setup_ui()
        self._refresh_templates()

    def _setup_ui(self) -> None:
        """Create the template library UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QGroupBox("Template Library"))
        layout.addLayout(header_layout)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search templates...")
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setMinimumHeight(200)
        layout.addWidget(self.tree)

        # Buttons
        btn_layout = QHBoxLayout()

        self.use_btn = QPushButton("Use Template")
        self.use_btn.clicked.connect(self._on_use_clicked)
        self.use_btn.setEnabled(False)
        btn_layout.addWidget(self.use_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _refresh_templates(self, filter_text: str = "") -> None:
        """Refresh the template tree."""
        self.tree.clear()

        filter_lower = filter_text.lower()

        # Built-in templates
        builtin_item = QTreeWidgetItem(["📦 Built-in Templates"])
        builtin_item.setFlags(builtin_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = builtin_item.font(0)
        font.setBold(True)
        builtin_item.setFont(0, font)

        for template in self.store.get_builtin_templates():
            if filter_lower and filter_lower not in template.name.lower():
                continue
            item = QTreeWidgetItem([f"  {template.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, template)
            builtin_item.addChild(item)

        if builtin_item.childCount() > 0:
            self.tree.addTopLevelItem(builtin_item)
            builtin_item.setExpanded(True)

        # User templates
        user_templates = self.store.get_user_templates()
        if user_templates or not filter_text:
            user_item = QTreeWidgetItem(["👤 My Templates"])
            user_item.setFlags(user_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = user_item.font(0)
            font.setBold(True)
            user_item.setFont(0, font)

            for template in user_templates:
                if filter_lower and filter_lower not in template.name.lower():
                    continue
                item = QTreeWidgetItem([f"  {template.name}"])
                item.setData(0, Qt.ItemDataRole.UserRole, template)
                user_item.addChild(item)

            self.tree.addTopLevelItem(user_item)
            user_item.setExpanded(True)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._refresh_templates(text)

    def _get_selected_template(self) -> WorkoutTemplateData | None:
        """Get the currently selected template."""
        item = self.tree.currentItem()
        if item:
            return item.data(0, Qt.ItemDataRole.UserRole)
        return None

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item click."""
        template = item.data(0, Qt.ItemDataRole.UserRole)
        self.use_btn.setEnabled(template is not None)
        if template:
            self.template_selected.emit(template)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item double-click."""
        template = item.data(0, Qt.ItemDataRole.UserRole)
        if template:
            self.template_double_clicked.emit(template)

    def _on_use_clicked(self) -> None:
        """Handle use template button click."""
        template = self._get_selected_template()
        if template:
            self.template_double_clicked.emit(template)

    def _on_context_menu(self, pos) -> None:
        """Show context menu for templates."""
        item = self.tree.itemAt(pos)
        if not item:
            return

        template = item.data(0, Qt.ItemDataRole.UserRole)
        if not template:
            return

        menu = QMenu(self)

        use_action = menu.addAction("Use Template")
        use_action.triggered.connect(lambda: self.template_double_clicked.emit(template))

        if not template.is_builtin:
            menu.addSeparator()

            rename_action = menu.addAction("Rename...")
            rename_action.triggered.connect(lambda: self._rename_template(template))

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._delete_template(template))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _rename_template(self, template: WorkoutTemplateData) -> None:
        """Rename a user template."""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Template",
            "New name:",
            QLineEdit.EchoMode.Normal,
            template.name,
        )

        if ok and new_name.strip():
            if self.store.rename_template(template.name, new_name.strip()):
                self._refresh_templates(self.search_input.text())

    def _delete_template(self, template: WorkoutTemplateData) -> None:
        """Delete a user template."""
        result = QMessageBox.question(
            self,
            "Delete Template",
            f"Delete template '{template.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            if self.store.delete_template(template.name):
                self._refresh_templates(self.search_input.text())

    def save_template(self, workout: BuilderWorkout, name: str | None = None) -> bool:
        """Save a workout as a user template."""
        if name is None:
            name, ok = QInputDialog.getText(
                self,
                "Save Template",
                "Template name:",
                QLineEdit.EchoMode.Normal,
                workout.name,
            )
            if not ok or not name.strip():
                return False
            name = name.strip()

        # Check for existing
        existing = [t for t in self.store.get_user_templates() if t.name == name]
        if existing:
            result = QMessageBox.question(
                self,
                "Overwrite Template",
                f"Template '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return False

        template = WorkoutTemplateData(
            name=name,
            workout=workout.copy(),
            is_builtin=False,
        )
        self.store.save_template(template)
        self._refresh_templates(self.search_input.text())
        return True

    def refresh(self) -> None:
        """Refresh the template list."""
        self._refresh_templates(self.search_input.text())
