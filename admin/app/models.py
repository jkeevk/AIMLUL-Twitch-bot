import ipaddress
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class SSHConnectionRequest(BaseModel):
    """
    Model representing an SSH connection request.

    Attributes:
        ip (str): IP address of the SSH host.
        username (str): SSH username.
        password (str, optional): SSH password. Defaults to "".
        container (str): Docker container name to manage.
    """

    ip: str
    username: str
    password: str = ""
    container: str

    @field_validator("ip")
    def validate_ip(cls, value: str) -> str:
        """
        Validate IP address format.

        Args:
            value (str): IP address string.

        Returns:
            str: Validated IP address.

        Raises:
            ValueError: If IP address format is invalid.
        """
        try:
            ipaddress.ip_address(value)
        except ValueError:
            raise ValueError("Invalid IP address format") from None
        return value


class ErrorResponse(BaseModel):
    """
    Standardized error response model.

    Attributes:
        error (str): Error message.
        details (Optional[str]): Optional detailed description.
        timestamp (str): ISO formatted UTC timestamp of the error.
    """

    error: str
    details: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
