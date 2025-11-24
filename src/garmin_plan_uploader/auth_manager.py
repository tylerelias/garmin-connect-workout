"""Authentication manager for Garmin Connect with token caching.

This module handles Garmin Connect authentication using the garminconnect
library with persistent token caching to prevent rate limiting/banning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from garminconnect import Garmin, GarminConnectAuthenticationError

if TYPE_CHECKING:
    from garth import Client as GarthClient

logger = logging.getLogger(__name__)

# Default token storage location
DEFAULT_TOKEN_DIR = Path.home() / ".garminconnect"


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class MFARequiredError(Exception):
    """Raised when MFA is required to complete login."""

    def __init__(self, message: str, garmin_client: Garmin, mfa_context: str):
        super().__init__(message)
        self.garmin_client = garmin_client
        self.mfa_context = mfa_context


class GarminSession:
    """Manages Garmin Connect authentication with token caching.

    This class handles:
    - Initial login with username/password
    - MFA (Multi-Factor Authentication) support
    - Token caching to disk (~/.garminconnect)
    - Token refresh/reload on subsequent runs

    Usage:
        session = GarminSession()

        # Try to login (will use cached tokens if available)
        try:
            session.login(email, password)
        except MFARequiredError as e:
            mfa_code = input("Enter MFA code: ")
            session.complete_mfa(e.mfa_context, mfa_code)

        # Now use session.client to make API calls
        workouts = session.client.get_workouts()
    """

    def __init__(self, token_dir: Path | str | None = None):
        """Initialize the session manager.

        Args:
            token_dir: Directory for storing authentication tokens.
                       Defaults to ~/.garminconnect
        """
        self.token_dir = Path(token_dir) if token_dir else DEFAULT_TOKEN_DIR
        self._client: Garmin | None = None
        self._is_authenticated = False

    @property
    def client(self) -> Garmin:
        """Get the authenticated Garmin client.

        Raises:
            AuthenticationError: If not authenticated
        """
        if not self._is_authenticated or self._client is None:
            raise AuthenticationError("Not authenticated. Call login() first.")
        return self._client

    @property
    def garth(self) -> "GarthClient":
        """Get the underlying Garth client for direct API calls.

        Raises:
            AuthenticationError: If not authenticated
        """
        return self.client.garth

    @property
    def is_authenticated(self) -> bool:
        """Check if session is authenticated."""
        return self._is_authenticated

    def _ensure_token_dir(self) -> None:
        """Create token directory if it doesn't exist."""
        self.token_dir.mkdir(parents=True, exist_ok=True)

    def _has_cached_tokens(self) -> bool:
        """Check if valid cached tokens exist."""
        oauth1_file = self.token_dir / "oauth1_token.json"
        oauth2_file = self.token_dir / "oauth2_token.json"
        return oauth1_file.exists() and oauth2_file.exists()

    def _save_tokens(self) -> None:
        """Save current tokens to disk."""
        if self._client is None:
            return

        self._ensure_token_dir()
        try:
            self._client.garth.dump(str(self.token_dir))
            logger.info(f"Tokens saved to {self.token_dir}")
        except Exception as e:
            logger.warning(f"Failed to save tokens: {e}")

    def _load_cached_tokens(self) -> bool:
        """Attempt to load and validate cached tokens.

        Returns:
            True if tokens were loaded successfully, False otherwise
        """
        if not self._has_cached_tokens():
            logger.debug("No cached tokens found")
            return False

        try:
            # Create a new client and use login with tokenstore to load cached tokens
            # This properly initializes the client with the cached session
            self._client = Garmin()
            self._client.login(tokenstore=str(self.token_dir))
            self._is_authenticated = True
            logger.info("Successfully loaded cached tokens")
            return True

        except Exception as e:
            logger.warning(f"Cached tokens invalid or expired: {e}")
            self._client = None
            self._is_authenticated = False
            return False

    def login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        force_new_login: bool = False,
    ) -> bool:
        """Authenticate with Garmin Connect.

        This method first attempts to use cached tokens. If they don't exist
        or are invalid, it performs a fresh login with email/password.

        Args:
            email: Garmin Connect email (required for fresh login)
            password: Garmin Connect password (required for fresh login)
            force_new_login: Skip token cache and force fresh login

        Returns:
            True if login successful, False if MFA is required
            (in which case MFARequiredError is raised)

        Raises:
            MFARequiredError: If MFA is required. Call complete_mfa() with the code.
            AuthenticationError: If authentication fails
        """
        # Try cached tokens first (unless force_new_login)
        if not force_new_login and self._load_cached_tokens():
            return True

        # Need fresh login - check credentials
        if not email or not password:
            raise AuthenticationError(
                "No valid cached tokens found. Email and password required for fresh login."
            )

        logger.info("Performing fresh login to Garmin Connect...")

        # Ensure token directory exists before login
        self._ensure_token_dir()

        try:
            # Create client with MFA support
            self._client = Garmin(email=email, password=password)

            # For fresh login, don't pass tokenstore - it tries to load tokens first
            # We'll save tokens manually after successful login
            result = self._client.login()

            # Check if MFA is required
            # The login() method returns different things based on MFA status
            if isinstance(result, tuple) and len(result) == 2:
                status, mfa_context = result
                if status == "needs_mfa":
                    raise MFARequiredError(
                        "Multi-Factor Authentication required. Please provide the MFA code.",
                        garmin_client=self._client,
                        mfa_context=mfa_context,
                    )

            # Login successful
            self._is_authenticated = True
            self._save_tokens()
            logger.info("Login successful")
            return True

        except GarminConnectAuthenticationError as e:
            self._client = None
            self._is_authenticated = False
            raise AuthenticationError(f"Authentication failed: {e}") from e

        except MFARequiredError:
            # Re-raise MFA error
            raise

        except Exception as e:
            self._client = None
            self._is_authenticated = False
            raise AuthenticationError(f"Unexpected error during login: {e}") from e

    def complete_mfa(self, garmin_client: Garmin, mfa_context: str, mfa_code: str) -> None:
        """Complete MFA authentication.

        Args:
            garmin_client: The Garmin client from MFARequiredError
            mfa_context: The MFA context from MFARequiredError
            mfa_code: The MFA code from the user

        Raises:
            AuthenticationError: If MFA verification fails
        """
        try:
            self._ensure_token_dir()
            self._client = garmin_client
            # Don't pass tokenstore for MFA completion either
            self._client.login(mfa_code=mfa_code)
            self._is_authenticated = True
            self._save_tokens()
            logger.info("MFA verification successful")

        except GarminConnectAuthenticationError as e:
            self._client = None
            self._is_authenticated = False
            raise AuthenticationError(f"MFA verification failed: {e}") from e

        except Exception as e:
            self._client = None
            self._is_authenticated = False
            raise AuthenticationError(f"Unexpected error during MFA: {e}") from e

    def logout(self) -> None:
        """Clear the session and remove cached tokens."""
        self._client = None
        self._is_authenticated = False

        # Remove cached token files
        if self.token_dir.exists():
            for token_file in self.token_dir.glob("*.json"):
                try:
                    token_file.unlink()
                    logger.debug(f"Removed token file: {token_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove {token_file}: {e}")

        logger.info("Logged out and cleared cached tokens")

    def get_display_name(self) -> str:
        """Get the display name of the authenticated user.

        Returns:
            User's full name or display name

        Raises:
            AuthenticationError: If not authenticated
        """
        try:
            full_name = self.client.get_full_name()
            if full_name:
                return full_name
        except Exception:
            pass
        return str(self.client.display_name)
