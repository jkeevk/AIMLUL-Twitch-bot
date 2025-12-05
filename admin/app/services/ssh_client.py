import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncGenerator
from types import TracebackType

import asyncssh
from app.config import settings
from asyncssh import SSHClientConnection

logger = logging.getLogger(__name__)


class SSHConnectionPool:
    """Pool for managing and reusing SSH connections."""

    def __init__(self, idle_timeout: int = 300):
        """
        Initialize SSH connection pool.

        Args:
            idle_timeout: Time in seconds after which idle connections are closed.
        """
        self._connections: dict[str, SSHClientConnection] = {}
        self._last_access: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout = idle_timeout
        self._healthcheck_cache: dict[str, tuple[float, bool]] = {}
        self._healthcheck_ttl = 30
        self._connection_semaphore = asyncio.Semaphore(3)

    async def get_client(self, host: str, username: str, password: str) -> asyncssh.SSHClientConnection:
        """
        Get an SSH client from the pool or establish a new connection.

        Args:
            host: SSH host.
            username: SSH username.
            password: SSH password.

        Returns:
            SSHClientConnection instance.
        """
        key = f"{host}:{username}:{password}"

        async with self._connection_semaphore, self._lock:
            await self._cleanup()
            client = self._connections.get(key)
            current_time = time.time()

            if client and key in self._healthcheck_cache:
                last_check_time, is_healthy = self._healthcheck_cache[key]
                if current_time - last_check_time < self._healthcheck_ttl and is_healthy:
                    self._last_access[key] = current_time
                    return client

            if client:
                try:
                    await asyncio.wait_for(client.run("echo healthcheck", timeout=2), timeout=3)
                    self._healthcheck_cache[key] = (current_time, True)
                except (TimeoutError, asyncssh.ConnectionLost, asyncssh.ChannelOpenError, Exception) as e:
                    logger.warning(f"Health check failed for {key}: {e}")
                    client.close()
                    with contextlib.suppress(Exception):
                        await client.wait_closed()
                    self._connections.pop(key, None)
                    self._last_access.pop(key, None)
                    self._healthcheck_cache.pop(key, None)
                    client = None

            if client is None:
                try:
                    client = await asyncio.wait_for(
                        asyncssh.connect(
                            host,
                            username=username,
                            password=password,
                            known_hosts=None,
                            client_keys=None,
                            options=asyncssh.SSHClientConnectionOptions(
                                keepalive_interval=30,
                                keepalive_count_max=3,
                                connect_timeout=15,
                            ),
                        ),
                        timeout=15,
                    )
                    self._connections[key] = client
                    self._last_access[key] = current_time
                    self._healthcheck_cache[key] = (current_time, True)
                    logger.info(f"SSH connection established to {host}")
                except Exception as e:
                    logger.error(f"Failed to connect to {key}: {e}")
                    raise

            self._last_access[key] = current_time
            return client

    async def mark_unhealthy(self, host: str, username: str, password: str) -> None:
        """
        Mark SSH connection as unhealthy.

        Args:
            host: SSH host.
            username: SSH username.
            password: SSH password.
        """
        key = f"{host}:{username}:{password}"
        async with self._lock:
            self._healthcheck_cache[key] = (time.time(), False)

    async def _cleanup(self) -> None:
        """Close idle SSH connections exceeding the idle timeout."""
        now = time.time()
        keys_to_remove = [k for k, t in self._last_access.items() if now - t > self._idle_timeout]
        for key in keys_to_remove:
            conn = self._connections.pop(key, None)
            self._last_access.pop(key, None)
            self._healthcheck_cache.pop(key, None)
            if conn:
                conn.close()
                with contextlib.suppress(Exception):
                    await conn.wait_closed()
                logger.debug(f"Closed idle SSH connection: {key}")

    async def close_all(self) -> None:
        """Close all SSH connections in the pool."""
        async with self._lock:
            for key, conn in list(self._connections.items()):
                self._connections.pop(key, None)
                self._last_access.pop(key, None)
                self._healthcheck_cache.pop(key, None)
                if conn:
                    conn.close()
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(conn.wait_closed(), timeout=5)


ssh_pool = SSHConnectionPool()


class AsyncSSHWrapper:
    """Wrapper for executing SSH commands using the connection pool."""

    def __init__(self, host: str, username: str, password: str):
        """
        Initialize SSH wrapper.

        Args:
            host: SSH host.
            username: SSH username.
            password: SSH password (falls back to default if empty).
        """
        self.host = host
        self.username = username
        self.password = settings.default_ssh_password if password == "" else password
        self.client: asyncssh.SSHClientConnection | None = None

    async def __aenter__(self) -> "AsyncSSHWrapper":
        """Enter async context manager and acquire SSH connection."""
        self.client = await ssh_pool.get_client(self.host, self.username, self.password)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager and mark connection unhealthy on error."""
        if exc_type is not None and self.client:
            logger.error(f"SSH connection error: {exc_val}")
            await ssh_pool.mark_unhealthy(self.host, self.username, self.password)

    async def exec(self, command: str) -> str:
        """
        Execute an SSH command and return its output.

        Args:
            command: Command to execute.

        Returns:
            Command output as a string or error message.

        Raises:
            RuntimeError: If an SSH client is not initialized.
        """
        if not self.client:
            raise RuntimeError("SSH client not initialized")

        timeout = 30 if command.startswith("docker") else 10
        try:
            result = await self.client.run(command, check=False, timeout=timeout)
            return (result.stdout or "") + (result.stderr or "")
        except TimeoutError:
            logger.warning(f"Command timeout: {command[:50]}...")
            return f"Error: Command timeout after {timeout} seconds"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return f"Error: {e}"

    @contextlib.asynccontextmanager
    async def get_process(self, command: str) -> AsyncGenerator[asyncssh.SSHClientProcess]:
        """
        Context manager for streaming SSH command output.

        Args:
            command: Command string.

        Yields:
            SSHClientProcess instance.
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")

        process: asyncssh.SSHClientProcess = await self.client.create_process(
            command, stdin=asyncssh.DEVNULL, term_type=None
        )
        try:
            yield process
        finally:
            process.close()
            with contextlib.suppress(Exception):
                await process.wait_closed()
