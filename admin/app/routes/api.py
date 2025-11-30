import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import settings
from app.dependencies import get_client_ip, get_current_user_optional, verify_token
from app.models import SSHConnectionRequest
from app.security import create_token, login_attempts
from app.services.websocket_manager import websocket_manager
from app.services.ssh_client import AsyncSSHWrapper
from app.utils.jinja_setup import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """
    Main application page.

    Args:
        request: FastAPI request object.

    Returns:
        RedirectResponse or HTMLResponse: Redirect to login or rendered index page.
    """
    user = await get_current_user_optional(request)
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
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    """
    Authenticate user and set session cookie.

    Args:
        request: FastAPI request object.
        username: Login username.
        password: Login password.

    Returns:
        RedirectResponse or HTMLResponse: Redirect to index on success, login page on failure.
    """
    client_ip = get_client_ip(request)
    await login_attempts.cleanup_old_attempts()

    if await login_attempts.is_blocked(client_ip):
        async with login_attempts.lock:
            attempt = login_attempts.attempts.get(client_ip, {})
            blocked_until = attempt.get("blocked_until", 0)
            remaining_sec = max(int(blocked_until - time.time()), 0)
            minutes, seconds = divmod(remaining_sec, 60)

        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Too many failed login attempts. Try again in {minutes} min {seconds} sec.",
                "username": username,
                "lock_seconds": remaining_sec,
            },
        )

    if username == settings.auth_username and password == settings.auth_password:
        await login_attempts.clear_attempts(client_ip)
        token = await create_token(username)
        resp = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
        resp.set_cookie(
            "session",
            token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=settings.session_timeout_minutes * 60,
        )
        return resp

    await login_attempts.failed_attempt(client_ip)
    remaining_attempts = max(
        0, settings.password_attempts_limit - login_attempts.attempts.get(client_ip, {}).get("count", 0)
    )
    error_msg = "Invalid username or password."
    if remaining_attempts > 0:
        error_msg += f" Remaining attempts: {remaining_attempts}"
    else:
        error_msg += " This was your last attempt before temporary lock."

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": error_msg,
            "username": username,
            "lock_seconds": 0,
        },
    )


@router.get("/logout")  # type: ignore[misc]
async def logout() -> RedirectResponse:
    """Logout user by clearing session cookie.

    Returns:
        RedirectResponse: Redirect to login page.
    """
    await websocket_manager.cleanup()
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

    cmd = f"docker logs --tail {lines} {container} 2>&1"
    try:
        async with AsyncSSHWrapper(ip, username, password) as ssh:
            logs = await ssh.exec(cmd)
    except Exception as e:
        logs = f"SSH Connection Error: {e}"

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

    try:
        async with AsyncSSHWrapper(ip, username, password) as ssh:
            result = await ssh.exec(cmd)
        return JSONResponse({"status": "success", "result": result})
    except Exception as e:
        return JSONResponse({"status": "error", "result": str(e)}, status_code=500)


@router.websocket("/ws/logs")  # type: ignore[misc]
async def websocket_logs(websocket: WebSocket) -> None:
    """WebSocket endpoint for live Docker logs streaming.

    Args:
        websocket: WebSocket connection for real-time log streaming.
    """
    connection_id = str(uuid.uuid4())
    await websocket_manager.connect(websocket, connection_id)

    try:
        data = await websocket.receive_json()
        for field in ["ip", "username", "container"]:
            if field not in data:
                await websocket.send_text(f"Missing required field: {field}")
                return
        await websocket_manager.stream_logs(connection_id, data)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    except Exception as exc:
        logger.error(f"WebSocket error {connection_id}: {exc}")
        try:
            await websocket.send_text(f"Connection error: {exc}")
        except Exception:
            pass
    finally:
        websocket_manager.disconnect(connection_id)
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/health")  # type: ignore[misc]
async def health_check() -> JSONResponse:
    """Health check endpoint for service monitoring.

    Returns:
        JSONResponse: Service status information with timestamp and version.
    """
    return JSONResponse(content={"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"})
