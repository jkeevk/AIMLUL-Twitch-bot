import asyncio
import logging
import threading
import time
from datetime import datetime
from threading import Lock
from typing import Any

from app.ssh_client import SSHClientWrapper
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections and their metadata."""

    def __init__(self) -> None:
        """Initialize WebSocket manager."""
        self.active_connections: dict[str, WebSocket] = {}
        self.connection_info: dict[str, dict[str, Any]] = {}
        self.lock = Lock()

    async def connect(self, websocket: WebSocket, connection_id: str) -> None:
        """Register new WebSocket connection.

        Args:
            websocket: WebSocket connection.
            connection_id: Unique connection identifier.
        """
        await websocket.accept()
        with self.lock:
            self.active_connections[connection_id] = websocket
            self.connection_info[connection_id] = {
                "connected_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
            }
        logger.info(f"WebSocket connected: {connection_id}")

    def disconnect(self, connection_id: str) -> None:
        """Remove WebSocket connection.

        Args:
            connection_id: Unique connection identifier.
        """
        with self.lock:
            self.active_connections.pop(connection_id, None)
            info = self.connection_info.pop(connection_id, None)
            if info:
                duration = (datetime.utcnow() - info["connected_at"]).total_seconds()
                logger.info(
                    f"WebSocket disconnected: {connection_id}, "
                    f"duration: {duration:.2f}s, "
                    f"container: {info.get('container', 'unknown')}"
                )

    def update_activity(self, connection_id: str) -> None:
        """Update last activity timestamp for connection.

        Args:
            connection_id: Unique connection identifier.
        """
        with self.lock:
            if connection_id in self.connection_info:
                self.connection_info[connection_id]["last_activity"] = datetime.utcnow()

    def get_connection_info(self, connection_id: str) -> dict[str, Any] | None:
        """Get connection information.

        Args:
            connection_id: Unique connection identifier.

        Returns:
            Optional[Dict[str, Any]]: Connection info or None if not found.
        """
        with self.lock:
            return self.connection_info.get(connection_id)

    def cleanup(self) -> None:
        """Clean up all WebSocket connections."""
        with self.lock:
            for connection_id in list(self.active_connections.keys()):
                self.disconnect(connection_id)

    async def stream_docker_logs(self, connection_id: str, data: dict[str, Any]) -> None:
        """Stream Docker logs to a WebSocket connection.

        Args:
            connection_id: WebSocket connection identifier.
            data: Connection data containing SSH and container info.
        """
        logger.info(f"Starting log streaming for container {data['container']} on {data['ip']}")

        async def send_message(message: str) -> None:
            """Send a message to the WebSocket connection."""
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(message)
                except Exception as e:
                    logger.error(f"Failed to send message to {connection_id}: {e}")
                    self.disconnect(connection_id)
                    raise

        def ssh_worker() -> None:
            """Worker thread for SSH log streaming."""
            try:
                with SSHClientWrapper(data["ip"], data["username"], data.get("password", "")) as ssh:
                    cmd = f"docker logs --tail 50 -f {data['container']}"
                    stdin, stdout, stderr = ssh.client.exec_command(cmd)

                    asyncio.run_coroutine_threadsafe(
                        send_message(f"=== Live logs from {data['container']} on {data['ip']} ===\n"), loop
                    )

                    while connection_id in self.active_connections:
                        if stdout.channel.recv_ready():
                            chunk = stdout.channel.recv(1024).decode("utf-8", "replace")
                            if chunk:
                                asyncio.run_coroutine_threadsafe(send_message(chunk), loop)

                        if stdout.channel.recv_stderr_ready():
                            err_chunk = stdout.channel.recv_stderr(1024).decode("utf-8", "replace")
                            if err_chunk:
                                asyncio.run_coroutine_threadsafe(send_message(f"ERROR: {err_chunk}"), loop)

                        if stdout.channel.exit_status_ready():
                            exit_code = stdout.channel.recv_exit_status()
                            asyncio.run_coroutine_threadsafe(
                                send_message(f"\n=== Stream ended (exit code: {exit_code}) ===\n"), loop
                            )
                            break

                        time.sleep(0.1)

            except Exception as exc:
                logger.error(f"SSH worker error for {connection_id}: {exc}")
                asyncio.run_coroutine_threadsafe(send_message(f"Stream error: {exc}"), loop)
            finally:
                logger.info(f"SSH worker finished for {connection_id}")

        try:
            loop = asyncio.get_event_loop()
            thread = threading.Thread(target=ssh_worker, daemon=True)
            thread.start()

            while connection_id in self.active_connections:
                try:
                    message = await asyncio.wait_for(
                        self.active_connections[connection_id].receive_text(), timeout=30.0
                    )
                    self.update_activity(connection_id)
                    if message == "ping":
                        await send_message("pong")
                except TimeoutError:
                    try:
                        await send_message("ping")
                    except Exception:
                        break
                except WebSocketDisconnect:
                    break

        except Exception as exc:
            logger.error(f"WebSocket stream error for {connection_id}: {exc}")
            await send_message(f"WebSocket error: {exc}")


# Global WebSocket manager
websocket_manager: WebSocketManager = WebSocketManager()
