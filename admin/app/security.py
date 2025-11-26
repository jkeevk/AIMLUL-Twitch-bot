import hashlib
import secrets
import time
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

import jwt
from app.config import settings


class Security:
    """Utilities for password hashing and secret key generation."""

    @staticmethod
    def generate_secret_key() -> str:
        """
        Generate a secure secret key for JWT tokens.

        Returns:
            str: URL-safe base64-encoded random bytes.
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using SHA-256.

        Args:
            password: Plain text password.

        Returns:
            str: SHA-256 hash of the password.
        """
        return hashlib.sha256(password.encode()).hexdigest()


class LoginAttempts:
    """Track login attempts for brute-force protection."""

    def __init__(self) -> None:
        """Initialize login attempts tracker."""
        self.attempts: dict[str, dict[str, Any]] = {}
        self.lock = Lock()

    def failed_attempt(self, username: str, ip: str) -> None:
        """
        Record a failed login attempt.

        Args:
            username: Username used in attempt.
            ip: Client IP address.
        """
        with self.lock:
            key = f"{username}:{ip}"
            if key not in self.attempts:
                self.attempts[key] = {"count": 0, "first_attempt": time.time(), "last_attempt": time.time()}
            self.attempts[key]["count"] += 1
            self.attempts[key]["last_attempt"] = time.time()

    def is_blocked(self, username: str, ip: str) -> bool:
        """
        Check if login is blocked due to too many failed attempts.

        Args:
            username: Username to check.
            ip: Client IP address.

        Returns:
            bool: True if blocked, False otherwise.
        """
        with self.lock:
            key = f"{username}:{ip}"
            if key in self.attempts:
                attempts = self.attempts[key]
                if (
                    attempts["count"] >= settings.password_attempts_limit
                    and time.time() - attempts["first_attempt"] < 900
                ):
                    return True
            return False

    def clear_attempts(self, username: str, ip: str) -> None:
        """
        Clear login attempts for a specific user and IP.

        Args:
            username: Username to clear.
            ip: Client IP address.
        """
        with self.lock:
            key = f"{username}:{ip}"
            self.attempts.pop(key, None)

    def cleanup_old_attempts(self) -> None:
        """Remove old login attempts older than 1 hour."""
        with self.lock:
            current_time = time.time()
            to_remove = [key for key, attempt in self.attempts.items() if current_time - attempt["last_attempt"] > 3600]
            for key in to_remove:
                del self.attempts[key]


def create_token(username: str) -> str:
    """
    Create a JWT token for an authenticated user.

    Args:
        username: Username to include in token.

    Returns:
        str: JWT token string.
    """
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(minutes=settings.session_timeout_minutes),
        "iat": datetime.utcnow(),
    }
    token: str = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    return token


def decode_token(token: str) -> str | None:
    """
    Decode a JWT token and return the username.

    Args:
        token: JWT token string.

    Returns:
        Optional[str]: Username if token is valid, None otherwise.
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# Global login attempts tracker
login_attempts = LoginAttempts()
