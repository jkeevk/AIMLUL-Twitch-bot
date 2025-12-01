import asyncio
import contextlib
import logging
import time
from asyncio.subprocess import Process
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Optional

import asyncssh
from app.config import settings

logger = logging.getLogger(__name__)


class SSHConnectionPool:
    """Pool for managing and reusing SSH connections."""

    def __init__(self, idle_timeout: int = 300):
        self._connections: dict[str, asyncssh.SSHClientConnection] = {}
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

        async with self._connection_semaphore:
            async with self._lock:
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

    async def _cleanup(self) -> None:
        now = time.time()
        keys_to_remove = [k for k, t in self._last_access.items() if now - t > self._idle_timeout]
        for key in keys_to_remove:
            conn = self._connections.pop(key, None)
            self._last_access.pop(key, None)
            self._healthcheck_cache.pop(key, None)
            if conn:
                try:
                    conn.close()
                    await conn.wait_closed()
                    logger.debug(f"Closed idle SSH connection: {key}")
                except Exception:
                    pass

    async def close_all(self) -> None:
        """Close all SSH connections in the pool."""
        async with self._lock:
            for key, conn in list(self._connections.items()):
                self._connections.pop(key, None)
                self._last_access.pop(key, None)
                self._healthcheck_cache.pop(key, None)
                try:
                    conn.close()
                    await asyncio.wait_for(conn.wait_closed(), timeout=5)
                except Exception:
                    pass


ssh_pool = SSHConnectionPool()


class AsyncSSHWrapper:
    """Wrapper for executing SSH commands using the connection pool."""

    def __init__(self, host: str, username: str, password: str):
        self.host = host
        self.username = username
        self.password = settings.default_ssh_password if password == "" else password
        self.client: asyncssh.SSHClientConnection | None = None

    async def __aenter__(self) -> "AsyncSSHWrapper":
        """
        Enter the async context manager.

        Returns:
            AsyncSSHWrapper: The SSH wrapper instance.
        """
        self.client = await ssh_pool.get_client(self.host, self.username, self.password)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Optional["TracebackType"],
    ) -> None:
        """
        Exit the async context manager.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        if exc_type is not None and self.client:
            logger.error(f"SSH connection error: {exc_val}")
            key = f"{self.host}:{self.username}:{self.password}"
            if key in ssh_pool._healthcheck_cache:
                ssh_pool._healthcheck_cache[key] = (time.time(), False)

    async def exec(self, command: str) -> str:
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
            timeout = 30 if command.startswith("docker") else 10
            result = await self.client.run(command, check=False, timeout=timeout)
            return (result.stdout or "") + (result.stderr or "")
        except TimeoutError:
            logger.warning(f"Command timeout: {command[:50]}...")
            return f"Error: Command timeout after {timeout} seconds"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return f"Error: {e}"

    @contextlib.asynccontextmanager
    async def get_process(self, command: str) -> AsyncIterator[Process]:
        """
        Context manager for streaming command output.

        Args:
            command: Command string.

        Yields:
            AsyncSSH process.
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")

        process: Process | None = None
        try:
            process = await self.client.create_process(command, stdin=asyncssh.DEVNULL, term_type=None)
            yield process
        finally:
            pass
