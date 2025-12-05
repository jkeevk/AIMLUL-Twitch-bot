import logging
from typing import TYPE_CHECKING

from twitchio.errors import Unauthorized
from twitchio.ext import eventsub

if TYPE_CHECKING:
    from src.bot.twitch_bot import TwitchBot

logger = logging.getLogger(__name__)


class EventSubManager:
    """
    Manager for Twitch EventSub subscriptions.

    Handles initialization and subscription to channel point redemptions
    for a given Twitch bot instance.
    """

    def __init__(self, bot: "TwitchBot") -> None:
        """
        Initialize EventSub manager.

        Args:
            bot: TwitchBot instance.
        """
        self.bot = bot
        self.client: eventsub.EventSubWSClient | None = None

    async def setup(self) -> None:
        """
        Set up EventSub subscription for channel point redemptions.

        If the streamer is not an Affiliate or Partner, subscription
        will be skipped with a warning.
        """
        if not self.bot.token_manager.has_streamer_token():
            logger.info("No STREAMER token → EventSub disabled")
            return

        try:
            self.client = eventsub.EventSubWSClient(self.bot)
            streamer_token = await self.bot.token_manager.get_streamer_token()
            channel_list = self.bot.config["channels"]

            if not channel_list:
                logger.warning("Channel list is empty in config. EventSub setup skipped.")
                return
            channel_name = channel_list[0]

            users = await self.bot.fetch_users(names=[channel_name])
            if not users:
                logger.error(f"Streamer not found: {channel_name}")
                return

            broadcaster_id = users[0].id

            try:
                await self.client.subscribe_channel_points_redeemed(
                    broadcaster_id,
                    streamer_token,
                )
                logger.info("EventSub started successfully (channel points)")
            except Unauthorized:
                logger.warning("Streamer is not Affiliate/Partner — channel points EventSub disabled.")

        except Exception as e:
            logger.error(f"EventSub setup failed: {e}", exc_info=True)

    async def close(self) -> None:
        """
        Close the EventSub WebSocket connection.

        Args:
            None.
        """
        if self.client:
            try:
                ws = getattr(self.client, "_websocket", None)

                if ws and not ws.closed:
                    await ws.close()
                    logger.info("EventSub WebSocket closed")
                else:
                    logger.info("EventSub WebSocket already closed")

            except Exception as e:
                logger.exception(f"Error closing EventSub WebSocket: {e}", exc_info=True)

            finally:
                self.client = None

        else:
            logger.info("EventSub WebSocket was never created")
