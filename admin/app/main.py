import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.config import settings
from app.routes import router
from app.ssh_client import ssh_pool
from app.templates import static_directory
from app.websocket_manager import websocket_manager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
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

    try:
        await asyncio.wait_for(websocket_manager.cleanup(), timeout=5)
    except TimeoutError:
        logger.warning("WebSocket cleanup timeout! Some tasks might still be running.")

    try:
        await asyncio.wait_for(ssh_pool.close_all(), timeout=5)
    except TimeoutError:
        logger.warning("SSH pool cleanup timeout! Some connections might remain open.")

    logger.info("Application shutdown completed")


app = FastAPI(
    title="Docker Container Manager",
    description="Web UI for managing Docker containers via SSH",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=static_directory), name="static")
app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    """Log FastAPI startup."""
    logger.info("Starting FastAPI app...")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Close all WebSocket and SSH connections on shutdown."""
    logger.info("Shutting down FastAPI app...")

    try:
        await asyncio.wait_for(websocket_manager.cleanup(), timeout=5)
    except TimeoutError:
        logger.warning("WebSocket cleanup timeout!")

    try:
        await asyncio.wait_for(ssh_pool.close_all(), timeout=5)
    except TimeoutError:
        logger.warning("SSH pool cleanup timeout!")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True, log_level="info")
