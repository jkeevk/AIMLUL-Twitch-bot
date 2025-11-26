import logging

from pydantic import validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):  # type: ignore[misc]
    """
    Application configuration loaded from environment variables.

    Attributes:
        auth_username (str): Admin username for authentication.
        auth_password (str): Admin password for authentication.
        password_attempts_limit (int): Maximum login attempts before lockout.
        session_timeout_minutes (int): Session timeout in minutes.
        default_ssh_host (str): Default SSH host.
        default_ssh_username (str): Default SSH username.
        default_ssh_password (str): Default SSH password.
        default_container (str): Default Docker container name.
        secret_key (str): JWT secret key.
        jwt_algorithm (str): JWT signing algorithm.
        ssh_pool_max_connections (int): Max SSH connections in pool.
        ssh_pool_timeout (int): SSH pool timeout in seconds.
        log_level (str): Logging level.
    """

    auth_username: str = "admin"
    auth_password: str = "password"
    password_attempts_limit: int = 5
    session_timeout_minutes: int = 30

    default_ssh_host: str = "localhost"
    default_ssh_username: str = "root"
    default_ssh_password: str = ""

    default_container: str = "twitch-bot"

    secret_key: str = "SUPER_SECRET_KEY_CHANGE_ME"
    jwt_algorithm: str = "HS256"

    ssh_pool_max_connections: int = 5
    ssh_pool_timeout: int = 300  # seconds

    log_level: str = "INFO"

    class Config:
        """Pydantic configuration for environment variable loading."""

        env_file = ".env"
        extra = "ignore"

    @validator("secret_key")
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


# Global settings instance
settings = Settings()
