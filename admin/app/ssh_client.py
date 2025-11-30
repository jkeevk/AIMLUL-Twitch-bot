import asyncio
import contextlib
import logging
import time

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
        async with self._lock:
            await self._cleanup()
            client = self._connections.get(key)

            if client:
                try:
                    await asyncio.wait_for(client.run("echo healthcheck", timeout=3), timeout=5)
                except (TimeoutError, asyncssh.ConnectionLost, asyncssh.ChannelOpenError, Exception):
                    client.close()
                    with contextlib.suppress(Exception):
                        await client.wait_closed()
                    self._connections.pop(key, None)
                    self._last_access.pop(key, None)
                    client = None

            if client is None:
                try:
                    client = await asyncio.wait_for(
                        asyncssh.connect(
                            host,
                            username=username,
                            password=password,
                            known_hosts=None,
                            options=asyncssh.SSHClientConnectionOptions(keepalive_interval=30, keepalive_count_max=3),
                        ),
                        timeout=10,
                    )
                    self._connections[key] = client
                except Exception as e:
                    logger.error(f"Failed to connect to {key}: {e}")
                    raise

            self._last_access[key] = time.time()
            return client

    async def _cleanup(self) -> None:
        now = time.time()
        keys_to_remove = [k for k, t in self._last_access.items() if now - t > self._idle_timeout]
        for key in keys_to_remove:
            conn = self._connections.pop(key, None)
            self._last_access.pop(key, None)
            if conn:
                try:
                    await conn.wait_closed()
                except Exception:
                    pass

    async def close_all(self) -> None:
        """Close all SSH connections in the pool."""
        async with self._lock:
            for key, conn in list(self._connections.items()):
                self._connections.pop(key, None)
                self._last_access.pop(key, None)
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

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit the async context manager.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        if exc_type is not None and self.client:
            self.client.close()
            await self.client.wait_closed()
            key = f"{self.host}:{self.username}:{self.password}"
            async with ssh_pool._lock:
                ssh_pool._connections.pop(key, None)
                ssh_pool._last_access.pop(key, None)

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
            result = await self.client.run(command, check=False)
            return (result.stdout or "") + (result.stderr or "")
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return f"Error: {e}"

    @contextlib.asynccontextmanager
    async def get_process(self, command: str):
        """
        Context manager for streaming command output.

        Args:
            command: Command string.

        Yields:
            AsyncSSH process.
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")

        process = None

        try:
            process = await self.client.create_process(command, stdin=asyncssh.DEVNULL, term_type=None)
            yield process

        finally:

            if process:
                with contextlib.suppress(Exception):
                    process.close()

                with contextlib.suppress(Exception):
                    await asyncio.wait_for(process.wait(), timeout=1)
