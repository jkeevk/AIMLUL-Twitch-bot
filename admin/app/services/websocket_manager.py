import asyncio
import logging
from typing import Any

import asyncssh
from app.services.ssh_client import AsyncSSHWrapper
from asyncssh import SSHClientProcess
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections and their associated SSH processes."""

    def __init__(self) -> None:
        """Initialize WebSocket manager."""
        self.active_connections: dict[str, WebSocket] = {}
        self.processes: dict[str, asyncssh.SSHClientProcess] = {}

    async def connect(self, websocket: WebSocket, connection_id: str) -> None:
        """
        Register a new WebSocket connection.

        Args:
            websocket: WebSocket connection instance.
            connection_id: Unique identifier for this connection.
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    def disconnect(self, connection_id: str) -> None:
        """
        Remove a WebSocket connection and its associated process.

        Args:
            connection_id: Unique identifier for this connection.
        """
        self.active_connections.pop(connection_id, None)
        self.processes.pop(connection_id, None)

    @staticmethod
    async def _send_keepalive(websocket: WebSocket, interval: float = 10.0) -> None:
        """
        Send periodic empty messages to keep the WebSocket connection alive.

        Args:
            websocket: WebSocket connection to ping.
            interval: Time interval between pings in seconds.
        """
        try:
            while True:
                await asyncio.sleep(interval)
                await websocket.send_text("")  # keepalive ping
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    async def stream_logs(self, connection_id: str, data: dict[str, Any]) -> None:
        """
        Stream Docker container logs via WebSocket.

        Args:
            connection_id: Unique connection identifier.
            data: Dictionary containing Docker container info:
                  - ip: SSH host
                  - username: SSH username
                  - password: SSH password (optional)
                  - container: Container name
        """
        websocket = self.active_connections.get(connection_id)
        if not websocket:
            return

        ip = data["ip"]
        user = data["username"]
        pwd = data.get("password", "")
        container = data["container"]

        process: SSHClientProcess | None = None
        keepalive_task: asyncio.Task[Any] | None = None

        try:
            async with AsyncSSHWrapper(ip, user, pwd) as ssh:
                # Получаем последние 50 строк логов
                history = await ssh.exec(f"docker logs --tail 50 {container} 2>&1")
                await websocket.send_text(f"=== Last 50 lines ===\n{history}\n=== Live Stream Started ===\n")

                cmd = f"docker logs -f --tail 0 {container} 2>&1"
                async with ssh.get_process(cmd) as process:
                    self.processes[connection_id] = process

                    stdout = getattr(process, "stdout", None)
                    if stdout is None:
                        logger.error(f"No stdout for process {connection_id}")
                        return

                    keepalive_task = asyncio.create_task(self._send_keepalive(websocket))

                    while True:
                        try:
                            line_bytes = await asyncio.wait_for(stdout.readline(), timeout=1.0)
                        except TimeoutError:
                            continue

                        if not line_bytes:
                            break

                        line = line_bytes.rstrip()
                        try:
                            await websocket.send_text(line)
                        except (WebSocketDisconnect, ConnectionError):
                            logger.info(f"WebSocket {connection_id} disconnected during log streaming")
                            break

        except WebSocketDisconnect:
            logger.info(f"WebSocket {connection_id} disconnected")
        except ConnectionError as e:
            logger.warning(f"SSH connection error for {connection_id}: {e}")
        except TimeoutError as e:
            logger.warning(f"Timeout while reading logs for {connection_id}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error while streaming logs {connection_id}: {e}")
            if websocket:
                try:
                    await websocket.send_text(f"ERROR: {e}")
                except (WebSocketDisconnect, ConnectionError):
                    pass
        finally:
            if process:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.warning(f"Error killing process {connection_id}: {e}")

                try:
                    await asyncio.shield(asyncio.wait_for(process.wait(), timeout=2))
                except TimeoutError:
                    logger.warning(f"Process {connection_id} did not exit in time")
                except Exception as e:
                    logger.warning(f"Error waiting for process {connection_id}: {e}")

            if keepalive_task:
                keepalive_task.cancel()
                try:
                    await keepalive_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"Keepalive task error for {connection_id}: {e}")

            self.disconnect(connection_id)
            if websocket:
                try:
                    await websocket.close()
                except (WebSocketDisconnect, ConnectionError):
                    pass
                except Exception as e:
                    logger.warning(f"Error closing websocket {connection_id}: {e}")

    async def cleanup(self) -> None:
        """Close all WebSocket connections and SSH processes during shutdown."""
        for connection_id in list(self.active_connections.keys()):
            websocket = self.active_connections[connection_id]
            process = self.processes.get(connection_id)
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait_closed(), timeout=3)
                except Exception as e:
                    logger.warning(f"Error terminating process {connection_id}: {e}")
                    pass
            try:
                await websocket.close()
            except Exception as e:
                logger.warning(f"Error closing websocket {connection_id}: {e}")
                pass
        self.active_connections.clear()
        self.processes.clear()


websocket_manager = WebSocketManager()
