import asyncio
import logging
import sys

from src.bot.twitch_bot import TwitchBot
from src.utils.token_manager import TokenManager

CONFIG_PATH = "/app/settings.ini"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

logger = logging.getLogger("main")


async def main() -> None:
    """Main entry point for the bot: initializes token manager and starts bot."""
    try:
        token_manager = TokenManager(CONFIG_PATH)

        bot_token = await token_manager.get_access_token("BOT_TOKEN")
        logger.info("BOT token OK")

        if token_manager.has_streamer_token():
            await token_manager.get_access_token("STREAMER_TOKEN")
            logger.info("STREAMER token OK")

        bot = TwitchBot(token_manager, bot_token)
        await bot.start()

    except Exception as e:
        logger.critical(f"Startup error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
