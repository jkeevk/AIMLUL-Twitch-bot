"""
Main FastAPI application for Docker container management.

Features:
- JWT authentication (cookie-based)
- SSH command execution via Paramiko with connection pooling
- Live Docker logs streaming via WebSocket (thread → async safe)
- Rate limiting and brute force protection
- Comprehensive error handling and validation
- Web UI for remote container management
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import paramiko
from app.config import settings
from app.models import ErrorResponse
from app.routes import router
from app.templates import static_directory
from app.websocket_manager import websocket_manager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

logging.getLogger("paramiko").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manage application lifecycle events.

    Args:
        app (FastAPI): FastAPI application instance.
    """
    logger.info("Docker Container Manager starting up...")

    if settings.secret_key == "SUPER_SECRET_KEY_CHANGE_ME":
        from app.security import Security

        generated_key = Security.generate_secret_key()
        logger.warning(f"Generated secret key for development: {generated_key}")

    logger.info("Application startup completed")

    yield

    logger.info("Shutting down Docker Container Manager...")
    websocket_manager.cleanup()
    logger.info("Application shutdown completed")


app = FastAPI(
    title="Docker Container Manager",
    description="Web UI for managing Docker containers via SSH",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.include_router(router)


@app.exception_handler(paramiko.ssh_exception.SSHException)  # type: ignore[misc]
async def ssh_exception_handler(request: Request, exc: paramiko.ssh_exception.SSHException) -> JSONResponse:
    """
    Handle SSH connection exceptions.

    Args:
        request (Request): FastAPI request object.
        exc (SSHException): SSH exception.

    Returns:
        JSONResponse: Error response.
    """
    return JSONResponse(status_code=502, content=ErrorResponse(error="SSH connection failed", details=str(exc)).dict())


@app.exception_handler(TimeoutError)  # type: ignore[misc]
async def timeout_handler(request: Request, exc: TimeoutError) -> JSONResponse:
    """
    Handle timeout exceptions.

    Args:
        request (Request): FastAPI request object.
        exc (TimeoutError): Timeout exception.

    Returns:
        JSONResponse: Error response.
    """
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(error="Connection timeout", details="The operation took too long to complete").dict(),
    )


@app.exception_handler(RequestValidationError)  # type: ignore[misc]
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors.

    Args:
        request (Request): FastAPI request object.
        exc (RequestValidationError): Validation exception.

    Returns:
        JSONResponse: Error response.
    """
    return JSONResponse(status_code=422, content=ErrorResponse(error="Validation error", details=str(exc)).dict())


@app.exception_handler(500)  # type: ignore[misc]
async def internal_server_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle internal server errors.

    Args:
        request (Request): FastAPI request object.
        exc (Exception): Internal server error.

    Returns:
        JSONResponse: Error response.
    """
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal server error", details="An unexpected error occurred").dict(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True, log_level="info")
