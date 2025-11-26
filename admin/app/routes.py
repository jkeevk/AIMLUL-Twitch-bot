"""FastAPI route handlers for Docker container management."""

import logging
import time
import uuid
from datetime import datetime

from app.config import settings
from app.dependencies import get_client_ip, get_current_user_optional, verify_token
from app.models import SSHConnectionRequest
from app.security import create_token, login_attempts
from app.ssh_client import SSHClientWrapper, ssh_command_context
from app.websocket_manager import websocket_manager
from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse, response_model=None)  # type: ignore[misc]
async def root(request: Request) -> RedirectResponse | HTMLResponse:
    """Main application page.

    Args:
        request: FastAPI request object.

    Returns:
        RedirectResponse or HTMLResponse: Redirect to login or rendered index page.
    """
    user = get_current_user_optional(request)
    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "default_host": settings.default_ssh_host,
            "default_username": settings.default_ssh_username,
            "default_container": settings.default_container,
            "has_default_password": bool(settings.default_ssh_password),
        },
    )


@router.get("/login", response_class=HTMLResponse)  # type: ignore[misc]
async def login_page(request: Request) -> HTMLResponse:
    """Render login page.

    Args:
        request: FastAPI request object.

    Returns:
        HTMLResponse: Rendered login page.
    """
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_model=None)  # type: ignore[misc]
async def login_post(
    request: Request, username: str = Form(...), password: str = Form(...)
) -> RedirectResponse | HTMLResponse:
    """Authenticate user and set session cookie.

    Args:
        request: FastAPI request object.
        username: Login username.
        password: Login password.

    Returns:
        RedirectResponse or HTMLResponse: Redirect to index on success, login page on failure.
    """
    client_ip = get_client_ip(request)

    if int(time.time()) % 300 == 0:
        login_attempts.cleanup_old_attempts()

    if login_attempts.is_blocked(username, client_ip):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Too many failed login attempts. Please try again in 15 minutes."},
        )

    if username == settings.auth_username and password == settings.auth_password:
        login_attempts.clear_attempts(username, client_ip)
        token = create_token(username)
        resp = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
        resp.set_cookie(
            "session", token, httponly=True, secure=False, samesite="lax", max_age=settings.session_timeout_minutes * 60
        )
        return resp

    login_attempts.failed_attempt(username, client_ip)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})


@router.get("/logout")  # type: ignore[misc]
async def logout() -> RedirectResponse:
    """Logout user by clearing session cookie.

    Returns:
        RedirectResponse: Redirect to login page.
    """
    resp = RedirectResponse("/login")
    resp.delete_cookie("session")
    return resp


@router.post("/logs", response_class=HTMLResponse)  # type: ignore[misc]
async def fetch_logs(
    request: Request,
    ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(""),
    container: str = Form(...),
    lines: int = Form(200),
    user: str = Depends(verify_token),
) -> HTMLResponse:
    """Fetch Docker container logs via SSH.

    Args:
        request: FastAPI request object.
        ip: SSH host IP address.
        username: SSH username.
        password: SSH password.
        container: Docker container name.
        lines: Number of log lines to fetch.
        user: Authenticated username.

    Returns:
        HTMLResponse: Rendered logs page with container logs.
    """
    try:
        SSHConnectionRequest(ip=ip, username=username, container=container)
    except ValueError as e:
        return templates.TemplateResponse(
            "logs.html",
            {
                "request": request,
                "logs": f"Validation error: {e}",
                "ip": ip,
                "container": container,
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    with ssh_command_context(ip, username, f"docker logs --tail {lines} {container}"):
        with SSHClientWrapper(ip, username, password) as ssh:
            logs = ssh.exec(f"docker logs --tail {lines} {container}")

    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "logs": logs,
            "ip": ip,
            "container": container,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


@router.post("/container/action")  # type: ignore[misc]
async def container_action(
    request: Request,
    ip: str = Form(...),
    username: str = Form(...),
    password: str = Form(""),
    container: str = Form(...),
    action: str = Form(...),
    user: str = Depends(verify_token),
) -> JSONResponse:
    """Execute Docker container actions via SSH.

    Args:
        request: FastAPI request object.
        ip: SSH host IP address.
        username: SSH username.
        password: SSH password.
        container: Docker container name.
        action: Action to perform (start, stop, restart, status, stats, logs, inspect).
        user: Authenticated username.

    Returns:
        JSONResponse: Action result with status and output data.
    """
    commands = {
        "start": f"docker start {container}",
        "stop": f"docker stop {container}",
        "restart": f"docker restart {container}",
        "status": f"docker ps -f name={container}",
        "stats": f"docker stats {container} --no-stream",
        "logs": f"docker logs --tail 50 {container}",
        "inspect": f"docker inspect {container}",
    }

    cmd = commands.get(action)
    if not cmd:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"status": "error", "result": "Unknown action"}
        )

    with ssh_command_context(ip, username, cmd):
        with SSHClientWrapper(ip, username, password) as ssh:
            result = ssh.exec(cmd)

    return JSONResponse({"status": "success", "result": result})


@router.websocket("/ws/logs")  # type: ignore[misc]
async def websocket_logs(websocket: WebSocket) -> None:
    """WebSocket endpoint for live Docker logs streaming.

    Args:
        websocket: WebSocket connection for real-time log streaming.
    """
    connection_id = str(uuid.uuid4())

    try:
        await websocket_manager.connect(websocket, connection_id)
        data = await websocket.receive_json()

        required_fields = ["ip", "username", "container"]
        for field in required_fields:
            if field not in data:
                await websocket.send_text(f"Missing required field: {field}")
                return

        websocket_manager.connection_info[connection_id].update(
            {"ip": data["ip"], "container": data["container"], "username": data["username"]}
        )

        logger.info("Starting log stream for %s on %s", data["container"], data["ip"])
        await websocket_manager.stream_docker_logs(connection_id, data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally: %s", connection_id)
    except Exception as exc:
        logger.error("WebSocket error %s: %s", connection_id, exc)
        try:
            await websocket.send_text(f"Connection error: {exc}")
        except Exception:
            pass
    finally:
        websocket_manager.disconnect(connection_id)


@router.get("/health")  # type: ignore[misc]
async def health_check() -> JSONResponse:
    """Health check endpoint for service monitoring.

    Returns:
        JSONResponse: Service status information with timestamp and version.
    """
    return JSONResponse(content={"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"})
