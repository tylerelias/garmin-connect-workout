"""Main application window for Garmin Plan Uploader GUI."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..auth_manager import GarminSession
from ..workout_service import WorkoutService
from .builder import BuilderWidget
from .calendar_widget import CalendarWidget
from .download_widget import DownloadWidget
from .login_widget import LoginWidget
from .templates_widget import TemplatesWidget
from .upload_widget import UploadWidget

logger = logging.getLogger(__name__)

# Config directory for settings
CONFIG_DIR = Path.home() / ".config" / "garmin-plan-uploader"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# Available themes - macOS style
THEME_OPTIONS = ["Light", "Dark", "System"]
DEFAULT_THEME = "System"


def get_macos_light_stylesheet() -> str:
    """Return macOS-inspired light theme stylesheet."""
    return """
    QMainWindow, QWidget {
        background-color: #f5f5f7;
        color: #1d1d1f;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
        font-size: 14px;
    }
    
    QTabWidget::pane {
        border: 1px solid #d2d2d7;
        border-radius: 8px;
        background-color: #ffffff;
    }
    
    QTabBar::tab {
        background-color: #e8e8ed;
        color: #1d1d1f;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }
    
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #007aff;
    }
    
    QTabBar::tab:hover:!selected {
        background-color: #d1d1d6;
    }
    
    QPushButton {
        background-color: #007aff;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: 500;
    }
    
    QPushButton:hover {
        background-color: #0056b3;
    }
    
    QPushButton:pressed {
        background-color: #004494;
    }
    
    QPushButton:disabled {
        background-color: #c7c7cc;
        color: #8e8e93;
    }
    
    QPushButton[flat="true"], QPushButton:flat {
        background-color: transparent;
        color: #007aff;
    }
    
    QPushButton[flat="true"]:hover, QPushButton:flat:hover {
        background-color: rgba(0, 122, 255, 0.1);
    }
    
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #ffffff;
        border: 1px solid #d2d2d7;
        border-radius: 6px;
        padding: 6px 10px;
        color: #1d1d1f;
        selection-background-color: #007aff;
    }
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, 
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border: 2px solid #007aff;
    }
    
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #8e8e93;
    }
    
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        border: 1px solid #d2d2d7;
        border-radius: 6px;
        selection-background-color: #007aff;
    }
    
    QListWidget, QTreeWidget, QTableWidget, QTableView {
        background-color: #ffffff;
        border: 1px solid #d2d2d7;
        border-radius: 8px;
        alternate-background-color: #fafafa;
    }
    
    QListWidget::item, QTreeWidget::item {
        padding: 6px;
        border-radius: 4px;
    }
    
    QListWidget::item:selected, QTreeWidget::item:selected {
        background-color: #007aff;
        color: white;
    }
    
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
        background-color: #e8e8ed;
    }
    
    QHeaderView::section {
        background-color: #f5f5f7;
        color: #1d1d1f;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #d2d2d7;
        font-weight: 600;
    }
    
    QScrollBar:vertical {
        background-color: transparent;
        width: 12px;
        margin: 0;
    }
    
    QScrollBar::handle:vertical {
        background-color: #c7c7cc;
        border-radius: 6px;
        min-height: 30px;
        margin: 2px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: #8e8e93;
    }
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
        height: 0;
    }
    
    QScrollBar:horizontal {
        background-color: transparent;
        height: 12px;
        margin: 0;
    }
    
    QScrollBar::handle:horizontal {
        background-color: #c7c7cc;
        border-radius: 6px;
        min-width: 30px;
        margin: 2px;
    }
    
    QScrollBar::handle:horizontal:hover {
        background-color: #8e8e93;
    }
    
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
        width: 0;
    }
    
    QMenuBar {
        background-color: #f5f5f7;
        color: #1d1d1f;
        padding: 2px;
    }
    
    QMenuBar::item {
        padding: 6px 12px;
        border-radius: 4px;
    }
    
    QMenuBar::item:selected {
        background-color: #007aff;
        color: white;
    }
    
    QMenu {
        background-color: #ffffff;
        border: 1px solid #d2d2d7;
        border-radius: 8px;
        padding: 4px;
    }
    
    QMenu::item {
        padding: 8px 24px;
        border-radius: 4px;
    }
    
    QMenu::item:selected {
        background-color: #007aff;
        color: white;
    }
    
    QMenu::separator {
        height: 1px;
        background-color: #d2d2d7;
        margin: 4px 8px;
    }
    
    QStatusBar {
        background-color: #f5f5f7;
        color: #86868b;
        border-top: 1px solid #d2d2d7;
    }
    
    QGroupBox {
        font-weight: 600;
        border: 1px solid #d2d2d7;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 8px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        color: #1d1d1f;
    }
    
    QCheckBox, QRadioButton {
        color: #1d1d1f;
        spacing: 8px;
    }
    
    QCheckBox::indicator, QRadioButton::indicator {
        width: 18px;
        height: 18px;
    }
    
    QCheckBox::indicator:unchecked {
        border: 2px solid #c7c7cc;
        border-radius: 4px;
        background-color: #ffffff;
    }
    
    QCheckBox::indicator:checked {
        border: none;
        border-radius: 4px;
        background-color: #007aff;
    }
    
    QRadioButton::indicator:unchecked {
        border: 2px solid #c7c7cc;
        border-radius: 9px;
        background-color: #ffffff;
    }
    
    QRadioButton::indicator:checked {
        border: 5px solid #007aff;
        border-radius: 9px;
        background-color: #ffffff;
    }
    
    QProgressBar {
        border: none;
        border-radius: 4px;
        background-color: #e8e8ed;
        text-align: center;
        color: #1d1d1f;
    }
    
    QProgressBar::chunk {
        background-color: #007aff;
        border-radius: 4px;
    }
    
    QToolTip {
        background-color: #1d1d1f;
        color: #ffffff;
        border: none;
        border-radius: 4px;
        padding: 6px 10px;
    }
    
    QCalendarWidget {
        background-color: #ffffff;
    }
    
    QCalendarWidget QToolButton {
        color: #1d1d1f;
        background-color: transparent;
        border-radius: 4px;
        padding: 4px 8px;
    }
    
    QCalendarWidget QToolButton:hover {
        background-color: #e8e8ed;
    }
    
    QCalendarWidget QMenu {
        background-color: #ffffff;
    }
    
    QCalendarWidget QSpinBox {
        background-color: #ffffff;
        selection-background-color: #007aff;
    }
    
    QCalendarWidget QAbstractItemView:enabled {
        color: #1d1d1f;
        background-color: #ffffff;
        selection-background-color: #007aff;
        selection-color: white;
    }
    
    QCalendarWidget QAbstractItemView:disabled {
        color: #c7c7cc;
    }
    
    QLabel {
        color: #1d1d1f;
    }
    
    QDialog {
        background-color: #f5f5f7;
    }
    
    QSplitter::handle {
        background-color: #d2d2d7;
    }
    
    QSplitter::handle:horizontal {
        width: 1px;
    }
    
    QSplitter::handle:vertical {
        height: 1px;
    }
    """


def get_macos_dark_stylesheet() -> str:
    """Return macOS-inspired dark theme stylesheet."""
    return """
    QMainWindow, QWidget {
        background-color: #1c1c1e;
        color: #f5f5f7;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
        font-size: 14px;
    }
    
    QTabWidget::pane {
        border: 1px solid #38383a;
        border-radius: 8px;
        background-color: #2c2c2e;
    }
    
    QTabBar::tab {
        background-color: #3a3a3c;
        color: #f5f5f7;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }
    
    QTabBar::tab:selected {
        background-color: #2c2c2e;
        color: #0a84ff;
    }
    
    QTabBar::tab:hover:!selected {
        background-color: #48484a;
    }
    
    QPushButton {
        background-color: #0a84ff;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: 500;
    }
    
    QPushButton:hover {
        background-color: #409cff;
    }
    
    QPushButton:pressed {
        background-color: #0056b3;
    }
    
    QPushButton:disabled {
        background-color: #48484a;
        color: #636366;
    }
    
    QPushButton[flat="true"], QPushButton:flat {
        background-color: transparent;
        color: #0a84ff;
    }
    
    QPushButton[flat="true"]:hover, QPushButton:flat:hover {
        background-color: rgba(10, 132, 255, 0.2);
    }
    
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #2c2c2e;
        border: 1px solid #48484a;
        border-radius: 6px;
        padding: 6px 10px;
        color: #f5f5f7;
        selection-background-color: #0a84ff;
    }
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border: 2px solid #0a84ff;
    }
    
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #8e8e93;
    }
    
    QComboBox QAbstractItemView {
        background-color: #2c2c2e;
        border: 1px solid #48484a;
        border-radius: 6px;
        selection-background-color: #0a84ff;
    }
    
    QListWidget, QTreeWidget, QTableWidget, QTableView {
        background-color: #2c2c2e;
        border: 1px solid #48484a;
        border-radius: 8px;
        alternate-background-color: #323234;
    }
    
    QListWidget::item, QTreeWidget::item {
        padding: 6px;
        border-radius: 4px;
    }
    
    QListWidget::item:selected, QTreeWidget::item:selected {
        background-color: #0a84ff;
        color: white;
    }
    
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
        background-color: #3a3a3c;
    }
    
    QHeaderView::section {
        background-color: #2c2c2e;
        color: #f5f5f7;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #48484a;
        font-weight: 600;
    }
    
    QScrollBar:vertical {
        background-color: transparent;
        width: 12px;
        margin: 0;
    }
    
    QScrollBar::handle:vertical {
        background-color: #636366;
        border-radius: 6px;
        min-height: 30px;
        margin: 2px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: #8e8e93;
    }
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
        height: 0;
    }
    
    QScrollBar:horizontal {
        background-color: transparent;
        height: 12px;
        margin: 0;
    }
    
    QScrollBar::handle:horizontal {
        background-color: #636366;
        border-radius: 6px;
        min-width: 30px;
        margin: 2px;
    }
    
    QScrollBar::handle:horizontal:hover {
        background-color: #8e8e93;
    }
    
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
        background: none;
        width: 0;
    }
    
    QMenuBar {
        background-color: #1c1c1e;
        color: #f5f5f7;
        padding: 2px;
    }
    
    QMenuBar::item {
        padding: 6px 12px;
        border-radius: 4px;
    }
    
    QMenuBar::item:selected {
        background-color: #0a84ff;
        color: white;
    }
    
    QMenu {
        background-color: #2c2c2e;
        border: 1px solid #48484a;
        border-radius: 8px;
        padding: 4px;
    }
    
    QMenu::item {
        padding: 8px 24px;
        border-radius: 4px;
    }
    
    QMenu::item:selected {
        background-color: #0a84ff;
        color: white;
    }
    
    QMenu::separator {
        height: 1px;
        background-color: #48484a;
        margin: 4px 8px;
    }
    
    QStatusBar {
        background-color: #1c1c1e;
        color: #8e8e93;
        border-top: 1px solid #38383a;
    }
    
    QGroupBox {
        font-weight: 600;
        border: 1px solid #48484a;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 8px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        color: #f5f5f7;
    }
    
    QCheckBox, QRadioButton {
        color: #f5f5f7;
        spacing: 8px;
    }
    
    QCheckBox::indicator, QRadioButton::indicator {
        width: 18px;
        height: 18px;
    }
    
    QCheckBox::indicator:unchecked {
        border: 2px solid #636366;
        border-radius: 4px;
        background-color: #2c2c2e;
    }
    
    QCheckBox::indicator:checked {
        border: none;
        border-radius: 4px;
        background-color: #0a84ff;
    }
    
    QRadioButton::indicator:unchecked {
        border: 2px solid #636366;
        border-radius: 9px;
        background-color: #2c2c2e;
    }
    
    QRadioButton::indicator:checked {
        border: 5px solid #0a84ff;
        border-radius: 9px;
        background-color: #2c2c2e;
    }
    
    QProgressBar {
        border: none;
        border-radius: 4px;
        background-color: #3a3a3c;
        text-align: center;
        color: #f5f5f7;
    }
    
    QProgressBar::chunk {
        background-color: #0a84ff;
        border-radius: 4px;
    }
    
    QToolTip {
        background-color: #f5f5f7;
        color: #1d1d1f;
        border: none;
        border-radius: 4px;
        padding: 6px 10px;
    }
    
    QCalendarWidget {
        background-color: #2c2c2e;
    }
    
    QCalendarWidget QToolButton {
        color: #f5f5f7;
        background-color: transparent;
        border-radius: 4px;
        padding: 4px 8px;
    }
    
    QCalendarWidget QToolButton:hover {
        background-color: #3a3a3c;
    }
    
    QCalendarWidget QMenu {
        background-color: #2c2c2e;
    }
    
    QCalendarWidget QSpinBox {
        background-color: #2c2c2e;
        selection-background-color: #0a84ff;
    }
    
    QCalendarWidget QAbstractItemView:enabled {
        color: #f5f5f7;
        background-color: #2c2c2e;
        selection-background-color: #0a84ff;
        selection-color: white;
    }
    
    QCalendarWidget QAbstractItemView:disabled {
        color: #636366;
    }
    
    QLabel {
        color: #f5f5f7;
    }
    
    QDialog {
        background-color: #1c1c1e;
    }
    
    QSplitter::handle {
        background-color: #48484a;
    }
    
    QSplitter::handle:horizontal {
        width: 1px;
    }
    
    QSplitter::handle:vertical {
        height: 1px;
    }
    """


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply a theme to the application."""
    app.setStyle("Fusion")
    
    if theme == "System":
        # Try to detect system theme
        palette = app.palette()
        # Check if system is in dark mode by checking window color brightness
        window_color = palette.color(QPalette.ColorRole.Window)
        is_dark = window_color.lightness() < 128
        stylesheet = get_macos_dark_stylesheet() if is_dark else get_macos_light_stylesheet()
    elif theme == "Dark":
        stylesheet = get_macos_dark_stylesheet()
    else:  # Light
        stylesheet = get_macos_light_stylesheet()
    
    app.setStyleSheet(stylesheet)


def load_settings() -> dict:
    """Load settings from config file."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_settings(settings: dict) -> None:
    """Save settings to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.setWindowTitle("Garmin Plan Uploader")
        self.setMinimumSize(900, 700)

        # Initialize session (not logged in yet)
        self.session = GarminSession()
        self.service: WorkoutService | None = None
        
        # Load settings
        self.settings = load_settings()
        self.current_theme = self.settings.get("theme", DEFAULT_THEME)

        self._setup_ui()
        self._setup_menu()

    def _setup_ui(self) -> None:
        """Create the main UI layout."""
        # Central widget with stacked views
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Login page
        self.login_widget = LoginWidget(self.session)
        self.login_widget.login_success.connect(self._on_login_success)
        self.login_widget.login_started.connect(self._on_login_started)
        self.stacked_widget.addWidget(self.login_widget)

        # Main app page (shown after login)
        self.main_widget = QWidget()
        main_layout = QVBoxLayout(self.main_widget)

        # Tabs for different functions
        self.tabs = QTabWidget()

        # Builder tab (available offline - no login required)
        self.builder_widget = BuilderWidget()
        self.tabs.addTab(self.builder_widget, "🛠️ Builder")

        # Upload tab (placeholder until login)
        self.upload_tab = QWidget()
        self.tabs.addTab(self.upload_tab, "📤 Upload Plan")

        # Calendar tab (placeholder until login)
        self.calendar_tab = QWidget()
        self.tabs.addTab(self.calendar_tab, "📅 Calendar")

        # Download tab (placeholder until login)
        self.download_tab = QWidget()
        self.tabs.addTab(self.download_tab, "📥 Download")

        # Templates tab (placeholder until login)
        self.templates_tab = QWidget()
        self.tabs.addTab(self.templates_tab, "📚 Templates")

        main_layout.addWidget(self.tabs)
        self.stacked_widget.addWidget(self.main_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Not logged in")

        # User info in status bar
        self.user_label = QLabel("")
        self.status_bar.addPermanentWidget(self.user_label)

    def _setup_menu(self) -> None:
        """Create the menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        logout_action = QAction("&Logout", self)
        logout_action.triggered.connect(self._on_logout)
        file_menu.addAction(logout_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu (themes)
        view_menu = menu_bar.addMenu("&View")
        
        theme_menu = view_menu.addMenu("🎨 Theme")
        
        # Group for exclusive selection
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        
        # Add theme options
        for theme_name in THEME_OPTIONS:
            action = QAction(theme_name, self)
            action.setCheckable(True)
            action.setChecked(theme_name == self.current_theme)
            action.triggered.connect(
                lambda checked, t=theme_name: self._on_theme_changed(t)
            )
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _on_theme_changed(self, theme_name: str) -> None:
        """Handle theme selection."""
        if theme_name in THEME_OPTIONS:
            try:
                apply_theme(self.app, theme_name)
                self.current_theme = theme_name
                self.settings["theme"] = theme_name
                save_settings(self.settings)
                self.status_bar.showMessage(f"Theme changed to {theme_name}", 3000)
            except Exception as e:
                logger.error(f"Failed to apply theme: {e}")
                QMessageBox.warning(
                    self,
                    "Theme Error",
                    f"Failed to apply theme: {e}",
                )

    def _on_login_started(self) -> None:
        """Handle login start."""
        self.status_bar.showMessage("Logging in...")

    def _on_login_success(self, display_name: str) -> None:
        """Handle successful login."""
        logger.info(f"Login successful: {display_name}")

        # Create service with authenticated session
        self.service = WorkoutService(self.session)

        # Connect builder widget to service
        self.builder_widget.set_service(self.service)

        # Connect builder's upload signal
        self.builder_widget.export_and_upload.connect(self._on_builder_upload)

        # Replace placeholder tabs with real widgets
        self._setup_upload_tab()
        self._setup_calendar_tab()
        self._setup_download_tab()
        self._setup_templates_tab()

        # Switch to main view
        self.stacked_widget.setCurrentWidget(self.main_widget)

        # Update status
        self.status_bar.showMessage("Connected to Garmin Connect")
        self.user_label.setText(f"👤 {display_name}")

    def _on_builder_upload(self, file_path: str) -> None:
        """Handle upload request from builder."""
        # Switch to upload tab and load the file
        upload_index = self.tabs.indexOf(self.upload_tab)
        self.tabs.setCurrentIndex(upload_index)

        # If upload_widget has a method to load a file, call it
        if hasattr(self.upload_tab, "load_file"):
            self.upload_tab.load_file(file_path)

    def _setup_upload_tab(self) -> None:
        """Set up the upload tab after login."""
        # Remove placeholder
        old_index = self.tabs.indexOf(self.upload_tab)

        # Create real upload widget
        self.upload_widget = UploadWidget(self.service)
        self.upload_widget.upload_started.connect(
            lambda: self.status_bar.showMessage("Uploading...")
        )
        self.upload_widget.upload_finished.connect(
            lambda r: self.status_bar.showMessage(
                f"Upload complete: {r.uploaded} uploaded, {r.failed} failed"
            )
        )

        # Replace tab
        self.tabs.removeTab(old_index)
        self.tabs.insertTab(old_index, self.upload_widget, "📤 Upload Plan")
        self.upload_tab = self.upload_widget

    def _setup_calendar_tab(self) -> None:
        """Set up the calendar tab after login."""
        # Remove placeholder
        old_index = self.tabs.indexOf(self.calendar_tab)

        # Create real calendar widget
        self.calendar_widget_view = CalendarWidget(self.service)

        # Replace tab
        self.tabs.removeTab(old_index)
        self.tabs.insertTab(old_index, self.calendar_widget_view, "📅 Calendar")
        self.calendar_tab = self.calendar_widget_view

    def _setup_download_tab(self) -> None:
        """Set up the download tab after login."""
        # Remove placeholder
        old_index = self.tabs.indexOf(self.download_tab)

        # Create real download widget
        self.download_widget = DownloadWidget(self.service)
        self.download_widget.download_started.connect(
            lambda: self.status_bar.showMessage("Downloading activities...")
        )
        self.download_widget.download_finished.connect(
            lambda r: self.status_bar.showMessage(
                f"Download complete: {r.downloaded} downloaded, {r.failed} failed"
            )
        )

        # Replace tab
        self.tabs.removeTab(old_index)
        self.tabs.insertTab(old_index, self.download_widget, "📥 Download")
        self.download_tab = self.download_widget

    def _setup_templates_tab(self) -> None:
        """Set up the templates tab after login."""
        # Remove placeholder
        old_index = self.tabs.indexOf(self.templates_tab)

        # Create real templates widget
        self.templates_widget = TemplatesWidget(self.service)

        # Replace tab
        self.tabs.removeTab(old_index)
        self.tabs.insertTab(old_index, self.templates_widget, "📚 Templates")
        self.templates_tab = self.templates_widget

    def _on_logout(self) -> None:
        """Handle logout."""
        result = QMessageBox.question(
            self,
            "Logout",
            "Are you sure you want to logout?\n\n"
            "This will clear your saved session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self.session.logout()
            self.service = None

            # Switch back to login view
            self.stacked_widget.setCurrentWidget(self.login_widget)
            self.status_bar.showMessage("Logged out")
            self.user_label.setText("")

    def _show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Garmin Plan Uploader",
            "<h3>Garmin Plan Uploader</h3>"
            "<p>Version 1.0.0</p>"
            "<p>Upload CSV training plans to Garmin Connect.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Workout Builder with templates</li>"
            "<li>CSV-based training plans</li>"
            "<li>Calendar view of scheduled workouts</li>"
            "<li>Bulk upload and delete</li>"
            "<li>Activity download</li>"
            "<li>Template management</li>"
            "</ul>"
            "<p><a href='https://github.com/tylerelias/garmin-connect-workout'>"
            "GitHub Repository</a></p>",
        )


def main() -> None:
    """Main entry point for the GUI application."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Garmin Plan Uploader")
    app.setOrganizationName("GarminPlanUploader")

    # Apply macOS-style theme
    settings = load_settings()
    theme_name = settings.get("theme", DEFAULT_THEME)
    if theme_name not in THEME_OPTIONS:
        theme_name = DEFAULT_THEME
    try:
        apply_theme(app, theme_name)
        logger.info(f"Applied theme: {theme_name}")
    except Exception as e:
        logger.warning(f"Failed to apply theme {theme_name}: {e}")
        app.setStyle("Fusion")

    # Create and show main window
    window = MainWindow(app)
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
