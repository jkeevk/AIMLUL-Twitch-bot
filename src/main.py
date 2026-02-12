import asyncio
import logging
import sys

from src.bot.manager import BotManager
from src.core.redis_client import create_redis
from src.utils.token_manager import TokenManager

CONFIG_PATH = "/app/settings.ini"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger("main")


async def main() -> None:
    """
    Main entry point for the Twitch bot application.

    This coroutine performs the following steps:
    1. Initializes the TokenManager with the configuration file (handles bot and streamer tokens).
    2. Creates an asynchronous Redis client for caching and state persistence.
    3. Instantiates the BotManager with the token manager and Redis client.
    4. Starts the BotManager, which in turn:
       - Launches the TwitchBot instance
       - Starts background tasks: token refresh, watchdog monitoring, and scheduled activity
       - Runs an internal health server on port 8081
    5. Monitors for exceptions, logs critical errors, and ensures proper shutdown.
    6. Stops the BotManager and all associated background tasks on exit.

    Logging:
        All events, errors, and token refresh activity are logged using the standard logging module.

    Notes:
        - On Windows, sets the appropriate asyncio event loop policy.
        - The bot automatically refreshes tokens before expiration and
          can restart itself if the Twitch WebSocket becomes unhealthy.
    """
    manager = None
    try:
        logger.info("Starting bot...")
        token_manager = TokenManager(CONFIG_PATH)
        redis = create_redis()
        manager = BotManager(token_manager, redis=redis)

        await manager.start()
    except Exception as e:
        logger.exception(f"Bot crashed!: {e}")
    finally:
        if manager:
            await manager.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
