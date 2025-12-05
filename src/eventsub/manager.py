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
        self.broadcaster_id: str | None = None
        self.subscribed = False

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
            channel_list = self.bot.config.get("channels") or []
            if not channel_list:
                logger.warning("Channel list is empty in config. EventSub setup skipped.")
                return

            users = await self.bot.fetch_users(names=[channel_list[0]])
            if not users:
                logger.error(f"Streamer not found: {channel_list[0]}")
                return
            self.broadcaster_id = users[0].id

            await self._start_client()

        except Exception as e:
            logger.error(f"EventSub setup failed: {e}", exc_info=True)

    async def _start_client(self) -> None:
        """Create the EventSub WebSocket client and subscribe to channel point redemptions."""
        if not self.client:
            self.client = eventsub.EventSubWSClient(self.bot)

        token = await self.bot.token_manager.get_streamer_token()
        if not token:
            logger.warning("Cannot get streamer token → EventSub disabled")
            return

        try:
            if not self.subscribed and self.broadcaster_id:
                await self.client.subscribe_channel_points_redeemed(self.broadcaster_id, token)
                self.subscribed = True
                logger.info("EventSub WS client created and subscribed successfully")
        except Unauthorized:
            logger.warning("Streamer is not Affiliate/Partner — channel points EventSub disabled")
        except Exception as e:
            logger.warning(f"Failed to subscribe to channel points: {e}")

    async def ensure_alive(self) -> None:
        """
        Ensure the EventSub WebSocket client is active.

        If disconnected or uninitialized, attempts to recreate and resubscribe.

        """
        try:
            if self.client is None or self.subscribed is False:
                logger.warning("EventSub client not initialized → starting client")
                await self._start_client()
            else:
                sockets = getattr(self.client, "_sockets", [])
                if not any(getattr(sock, "is_connected", False) for sock in sockets):
                    logger.warning("EventSub sockets disconnected → reconnecting")
                    await self._start_client()
        except Exception as e:
            logger.warning(f"Failed to ensure EventSub WS alive: {e}")

    async def close(self) -> None:
        """Reset and clear the EventSub WebSocket client."""
        if self.client:
            self.client = None
            self.subscribed = False
            logger.info("EventSub client cleared")
