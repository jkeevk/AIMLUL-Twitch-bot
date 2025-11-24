import asyncio
import logging
from typing import Any

logger = logging.getLogger("TokenRefresh")


async def periodic_refresh(bot: Any) -> None:
    """
    Periodically refresh BOT and STREAMER tokens.

    Args:
        bot: TwitchBot instance.
    """
    delay = bot.config["refresh_token_delay_time"]
    logger.info("Token refresh task started")

    while True:
        try:
            await asyncio.sleep(delay)

            new_bot_token = await bot.token_manager.refresh_access_token("BOT_TOKEN")
            bot._http.token = new_bot_token
            await bot.api.refresh_headers()

            if bot.token_manager.has_streamer_token():
                await bot.token_manager.refresh_access_token("STREAMER_TOKEN")
        except Exception as e:
            logger.error(f"Token refresh failed: {e}", exc_info=True)
            await asyncio.sleep(60)
