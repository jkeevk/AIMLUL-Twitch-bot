import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.services.ssh_client import AsyncSSHWrapper

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections and their metadata."""

    def __init__(self) -> None:
        """Initialize WebSocket manager."""
        self.active_connections: dict[str, WebSocket] = {}
        self.processes: dict[str, Any] = {}

    async def connect(self, websocket: WebSocket, connection_id: str) -> None:
        """Register new WebSocket connection.

        Args:
            websocket: WebSocket connection.
            connection_id: Unique connection identifier.
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    def disconnect(self, connection_id: str) -> None:
        """Remove WebSocket connection.

        Args:
            connection_id: Unique connection identifier.
        """
        self.active_connections.pop(connection_id, None)
        self.processes.pop(connection_id, None)

    async def stream_logs(self, connection_id: str, data: dict[str, Any]) -> None:
        """
        Stream Docker container logs via WebSocket.

        Args:
            connection_id: Unique connection identifier.
            data: Docker container logs data.

        Returns:
            Optional[Dict[str, Any]]: Connection info or None if not found.
        """
        websocket = self.active_connections.get(connection_id)
        if not websocket:
            return
        ip = data["ip"]
        user = data["username"]
        pwd = data.get("password", "")
        container = data["container"]

        process = None
        try:
            async with AsyncSSHWrapper(ip, user, pwd) as ssh:
                history = await ssh.exec(f"docker logs --tail 50 {container} 2>&1")
                await websocket.send_text(f"=== Last 50 lines ===\n{history}\n=== Live Stream Started ===\n")

                cmd = f"docker logs -f --tail 0 {container} 2>&1"
                async with ssh.get_process(cmd) as process:
                    self.processes[connection_id] = process

                    while True:
                        try:
                            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                        except TimeoutError:
                            await websocket.send_text("")
                            continue

                        if not line:
                            break

                        try:
                            await websocket.send_text(line)
                        except Exception:
                            break

        except (WebSocketDisconnect, ConnectionError):
            logger.info(f"WebSocket {connection_id} disconnected")
        except Exception as e:
            logger.error(f"Log stream error {connection_id}: {e}")
            if websocket:
                try:
                    await websocket.send_text(f"ERROR: {e}")
                except Exception:
                    pass
        finally:
            if process:
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    await asyncio.shield(asyncio.wait_for(process.wait(), timeout=2))
                except Exception:
                    pass
            self.disconnect(connection_id)
            if websocket:
                try:
                    await websocket.close()
                except Exception:
                    pass

    async def cleanup(self) -> None:
        """Close all WebSocket connections and SSH processes during shutdown."""
        for connection_id in list(self.active_connections.keys()):
            websocket = self.active_connections[connection_id]
            process = self.processes.get(connection_id)
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait_closed(), timeout=3)
                except Exception:
                    pass
            try:
                await websocket.close()
            except Exception:
                pass
        self.active_connections.clear()
        self.processes.clear()


websocket_manager = WebSocketManager()
