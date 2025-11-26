import ipaddress
from datetime import datetime

from pydantic import BaseModel, validator


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

    @validator("ip")
    def validate_ip(cls, v: str) -> str:
        """
        Validate IP address format.

        Args:
            v (str): IP address string.

        Returns:
            str: Validated IP address.

        Raises:
            ValueError: If IP address format is invalid.
        """
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError("Invalid IP address format") from None


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
    timestamp: str = datetime.utcnow().isoformat()
