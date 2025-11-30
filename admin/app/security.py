import asyncio
import hashlib
import secrets
import time
from datetime import datetime, timedelta
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
        self.lock = asyncio.Lock()

    async def failed_attempt(self, ip: str) -> None:
        """Record a failed login attempt."""
        async with self.lock:
            now = time.time()
            if ip not in self.attempts:
                self.attempts[ip] = {"count": 0, "last_attempt": now}
            attempt = self.attempts[ip]
            attempt["count"] += 1
            attempt["last_attempt"] = now

            if attempt["count"] >= settings.password_attempts_limit:
                attempt["blocked_until"] = now + settings.session_timeout_minutes * 60

    async def is_blocked(self, ip: str) -> bool:
        """Check if login is blocked due to too many failed attempts."""
        async with self.lock:
            attempt = self.attempts.get(ip)
            if not attempt:
                return False
            blocked_until: float = attempt.get("blocked_until", 0)
            return time.time() < blocked_until

    async def clear_attempts(self, ip: str) -> None:
        """Clear login attempts for a specific IP."""
        async with self.lock:
            self.attempts.pop(ip, None)

    async def cleanup_old_attempts(self) -> None:
        """Remove old login attempts older than 1 hour."""
        async with self.lock:
            current_time = time.time()
            to_remove = [ip for ip, attempt in self.attempts.items() if current_time - attempt["last_attempt"] > 3600]
            for ip in to_remove:
                del self.attempts[ip]


async def create_token(username: str) -> str:
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


async def decode_token(token: str) -> str | None:
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


login_attempts = LoginAttempts()
