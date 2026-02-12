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
    """Main entry point for the bot: initializes token manager and starts bot."""
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
