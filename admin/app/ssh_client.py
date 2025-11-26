import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock
from typing import Any

import paramiko
from app.config import settings

logger = logging.getLogger(__name__)


class SSHConnection:
    """SSH connection wrapper with usage tracking.

    Attributes:
        client: Paramiko SSH client.
        last_used: Timestamp of last usage.
        in_use: Whether connection is currently in use.
        usage_count: Total number of times connection has been used.
    """

    def __init__(self, client: paramiko.SSHClient):
        """
        Initialize SSH connection.

        Args:
            client: Paramiko SSH client.
        """
        self.client = client
        self.last_used: float = time.time()
        self.in_use: bool = False
        self.usage_count: int = 0


class SSHConnectionPool:
    """Pool for managing and reusing SSH connections."""

    def __init__(self, max_connections: int = 5, timeout: int = 300):
        """
        Initialize connection pool.

        Args:
            max_connections: Maximum number of connections in pool.
            timeout: Connection timeout in seconds.
        """
        self.max_connections = max_connections
        self.timeout = timeout
        self.connections: dict[str, SSHConnection] = {}
        self.lock = Lock()

    def get_connection(self, host: str, username: str, password: str) -> paramiko.SSHClient | None:
        """
        Get SSH connection from pool or create a new one.

        Args:
            host: SSH host address.
            username: SSH username.
            password: SSH password.

        Returns:
            Optional[paramiko.SSHClient]: SSH client or None if connection failed.
        """
        with self.lock:
            key = f"{host}:{username}"
            self._cleanup()

            if key in self.connections and not self.connections[key].in_use:
                conn = self.connections[key]
                conn.in_use = True
                conn.last_used = time.time()
                conn.usage_count += 1
                return conn.client

            if len(self.connections) < self.max_connections:
                try:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(host, username=username, password=password, timeout=8)

                    self.connections[key] = SSHConnection(client=client)
                    self.connections[key].in_use = True
                    self.connections[key].usage_count = 1
                    return client
                except Exception as e:
                    logger.error(f"SSH connection failed to {host}: {e}")
                    return None
            return None

    def release_connection(self, host: str, username: str) -> None:
        """
        Release a connection back to the pool.

        Args:
            host: SSH host address.
            username: SSH username.
        """
        key = f"{host}:{username}"
        with self.lock:
            if key in self.connections:
                self.connections[key].in_use = False

    def _cleanup(self) -> None:
        """Clean up stale and inactive connections."""
        current_time = time.time()
        to_remove: list[str] = []

        for key, conn in self.connections.items():
            transport = conn.client.get_transport()
            if (current_time - conn.last_used > self.timeout) or not transport or not transport.is_active():
                conn.client.close()
                to_remove.append(key)

        for key in to_remove:
            del self.connections[key]

    def get_pool_stats(self) -> dict[str, Any]:
        """
        Get connection pool statistics.

        Returns:
            Dict[str, Any]: Pool statistics.
        """
        with self.lock:
            active = sum(1 for conn in self.connections.values() if conn.in_use)
            return {
                "total_connections": len(self.connections),
                "active_connections": active,
                "idle_connections": len(self.connections) - active,
            }


class SSHClientWrapper:
    """
    Thread-safe SSH client wrapper with connection pooling.

    Supports:
    - Command execution with connection reuse
    - Docker logs streaming
    - Automatic connection cleanup
    """

    def __init__(self, host: str, username: str, password: str):
        """
        Initialize SSH client wrapper.

        Args:
            host: SSH host address.
            username: SSH username.
            password: SSH password.
        """
        self.host = host
        self.username = username
        self.password = password.strip() or settings.default_ssh_password
        self.client: paramiko.SSHClient | None = None
        self.from_pool: bool = False

    def __enter__(self) -> "SSHClientWrapper":
        """Enter context manager and establish SSH connection."""
        self.client = ssh_pool.get_connection(self.host, self.username, self.password)
        self.from_pool = self.client is not None

        if not self.from_pool:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=self.host, username=self.username, password=self.password, timeout=8)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None
    ) -> bool | None:
        """
        Exit context manager and release or close SSH connection.

        Args:
            exc_type: Exception type if raised.
            exc_val: Exception instance if raised.
            exc_tb: Traceback object if exception raised.

        Returns:
            Optional[bool]: True to suppress exception, None otherwise.
        """
        if self.client:
            if self.from_pool:
                ssh_pool.release_connection(self.host, self.username)
            else:
                self.client.close()
        return None

    def exec(self, command: str) -> str:
        """
        Execute an SSH command and return its output.

        Args:
            command: Command to execute.

        Returns:
            str: Command output or error message.

        Raises:
            RuntimeError: If SSH client is not initialized.
        """
        if not self.client:
            raise RuntimeError("SSH client not initialized")

        try:
            _, stdout, stderr = self.client.exec_command(command)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            return err if err and not out else out or "Command executed successfully"
        except Exception as exc:
            logger.error(f"SSH command failed: {exc}")
            return f"SSH Error: {exc}"


@contextmanager
def ssh_command_context(ip: str, username: str, command: str) -> Generator[None]:
    """
    Context manager for SSH command execution with logging.

    Args:
        ip: SSH host IP.
        username: SSH username.
        command: Command to execute.
    """
    start_time = time.time()
    success = False

    try:
        yield
        success = True
    except Exception as e:
        logger.error("SSH command failed: %s", e)
        raise
    finally:
        duration = time.time() - start_time
        logger.info(
            f"SSH Command: {command[:50]}... | "
            f"IP: {ip} | User: {username} | "
            f"Success: {success} | Duration: {duration:.2f}s"
        )


ssh_pool = SSHConnectionPool(max_connections=settings.ssh_pool_max_connections, timeout=settings.ssh_pool_timeout)
