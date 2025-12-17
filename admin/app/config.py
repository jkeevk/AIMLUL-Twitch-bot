import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):  # type: ignore[misc]
    """
    Application configuration loaded from environment variables.

    Attributes:
        auth_username (str): Admin username for authentication.
        auth_password (str): Admin password for authentication.
        max_login_attempts (int): Maximum login attempts before lockout.
        session_duration_minutes (int): Session duration in minutes.
        lockout_duration_minutes: Lockout duration in minutes.
        default_ssh_host (str): Default SSH host.
        default_ssh_username (str): Default SSH username.
        default_ssh_password (str): Default SSH password.
        default_container (str): Default Docker container name.
        secret_key (str): JWT secret key.
        jwt_algorithm (str): JWT signing algorithm.
    """

    auth_username: str = "admin"
    auth_password: str = "password"
    max_login_attempts: int = 5
    session_duration_minutes: int = 30
    lockout_duration_minutes: int = 15

    default_ssh_host: str = "localhost"
    default_ssh_username: str = "root"
    default_ssh_password: str = ""

    default_container: str = "bot"

    secret_key: str = "SUPER_SECRET_KEY_CHANGE_ME"
    jwt_algorithm: str = "HS256"

    class Config:
        """Pydantic configuration for environment variable loading."""

        env_file = ".env"
        extra = "ignore"

    @field_validator("secret_key")
    def validate_secret_key(cls, v: str) -> str:
        """
        Warn if the default secret key is used.

        Args:
            v (str): Secret key value.

        Returns:
            str: Validated secret key.
        """
        if v == "SUPER_SECRET_KEY_CHANGE_ME":
            logger.warning("Using default secret key - change in production!")
        return v


settings = Settings()
