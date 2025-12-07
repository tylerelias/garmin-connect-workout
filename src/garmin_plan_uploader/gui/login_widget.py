"""Login widget with MFA support."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..auth_manager import GarminSession
from .workers import LoginWorker, MFAWorker, run_worker

if TYPE_CHECKING:
    from garminconnect import Garmin

logger = logging.getLogger(__name__)


class MFADialog(QDialog):
    """Dialog for entering MFA code."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Two-Factor Authentication")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel(
            "Enter the verification code from your\n"
            "authenticator app or email:"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # Code input
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Enter 6-digit code")
        self.code_input.setMaxLength(10)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.returnPressed.connect(self.accept)
        layout.addWidget(self.code_input)

        # Buttons
        button_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.verify_btn = QPushButton("Verify")
        self.verify_btn.setDefault(True)
        self.verify_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.verify_btn)
        layout.addLayout(button_layout)

    def get_code(self) -> str:
        """Get the entered MFA code."""
        return self.code_input.text().strip()


class LoginWidget(QWidget):
    """Login form with Garmin Connect authentication."""

    # Signals
    login_success = Signal(str)  # display_name
    login_started = Signal()
    login_failed = Signal(str)  # error message

    def __init__(
        self,
        session: GarminSession,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.session = session
        self._worker = None
        self._thread = None
        self._pending_mfa_client = None
        self._pending_mfa_context = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the login form UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Title
        title = QLabel("Garmin Connect Login")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Status label (for cached token login)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("opacity: 0.7;")
        layout.addWidget(self.status_label)

        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@example.com")
        self.email_input.setMinimumWidth(250)
        form_layout.addRow("Email:", self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("••••••••")
        self.password_input.returnPressed.connect(self._on_login_clicked)
        form_layout.addRow("Password:", self.password_input)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()

        self.login_btn = QPushButton("Login")
        self.login_btn.setMinimumHeight(35)
        self.login_btn.clicked.connect(self._on_login_clicked)
        button_layout.addWidget(self.login_btn)

        self.cached_login_btn = QPushButton("Use Saved Session")
        self.cached_login_btn.setMinimumHeight(35)
        self.cached_login_btn.clicked.connect(self._on_cached_login_clicked)
        button_layout.addWidget(self.cached_login_btn)

        layout.addLayout(button_layout)

        # Stretch at bottom
        layout.addStretch()

        # Check if cached tokens exist
        self._update_cached_token_ui()

    def _update_cached_token_ui(self) -> None:
        """Update UI based on whether cached tokens exist."""
        has_cached = self.session._has_cached_tokens()
        self.cached_login_btn.setEnabled(has_cached)

        if has_cached:
            self.status_label.setText("Saved session found. Click 'Use Saved Session' for quick login.")
        else:
            self.status_label.setText("Enter your Garmin Connect credentials.")

    def _on_login_clicked(self) -> None:
        """Handle login button click."""
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(
                self,
                "Missing Credentials",
                "Please enter both email and password.",
            )
            return

        self._start_login(email, password, force_new=True)

    def _on_cached_login_clicked(self) -> None:
        """Handle cached login button click."""
        self._start_login(None, None, force_new=False)

    def _start_login(
        self,
        email: str | None,
        password: str | None,
        force_new: bool,
    ) -> None:
        """Start the login process in a background thread."""
        self._set_loading(True)
        self.login_started.emit()

        self._worker = LoginWorker(
            self.session,
            email=email,
            password=password,
            force_new=force_new,
        )
        self._worker.success.connect(self._on_login_success)
        self._worker.mfa_required.connect(self._on_mfa_required)
        self._worker.error.connect(self._on_login_error)
        self._worker.finished.connect(lambda: self._set_loading(False))

        self._thread = run_worker(self._worker)

    def _set_loading(self, loading: bool) -> None:
        """Enable/disable form during login."""
        self.email_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.login_btn.setEnabled(not loading)
        self.cached_login_btn.setEnabled(not loading)

        if loading:
            self.login_btn.setText("Logging in...")
            self.status_label.setText("Connecting to Garmin Connect...")
        else:
            self.login_btn.setText("Login")
            self._update_cached_token_ui()

    def _on_login_success(self, display_name: str) -> None:
        """Handle successful login."""
        logger.info(f"Login successful: {display_name}")
        self.status_label.setText(f"Logged in as: {display_name}")
        self.login_success.emit(display_name)

    def _on_mfa_required(self, garmin_client: "Garmin", mfa_context: str) -> None:
        """Handle MFA required."""
        logger.info("MFA required")
        self._pending_mfa_client = garmin_client
        self._pending_mfa_context = mfa_context

        # Show MFA dialog
        dialog = MFADialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            mfa_code = dialog.get_code()
            if mfa_code:
                self._complete_mfa(mfa_code)
            else:
                self.status_label.setText("MFA code required")
                self.login_failed.emit("No MFA code entered")
        else:
            self.status_label.setText("Login cancelled")
            self.login_failed.emit("MFA cancelled by user")

    def _complete_mfa(self, mfa_code: str) -> None:
        """Complete MFA authentication."""
        self._set_loading(True)
        self.status_label.setText("Verifying MFA code...")

        self._worker = MFAWorker(
            self.session,
            self._pending_mfa_client,
            self._pending_mfa_context,
            mfa_code,
        )
        self._worker.success.connect(self._on_login_success)
        self._worker.error.connect(self._on_login_error)
        self._worker.finished.connect(lambda: self._set_loading(False))

        self._thread = run_worker(self._worker)

    def _on_login_error(self, error: str) -> None:
        """Handle login error."""
        logger.error(f"Login failed: {error}")
        self.status_label.setText("Login failed")
        self.login_failed.emit(error)

        QMessageBox.critical(
            self,
            "Login Failed",
            f"Could not log in to Garmin Connect:\n\n{error}",
        )
