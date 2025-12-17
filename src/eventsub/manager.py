import logging
import asyncio
from typing import TYPE_CHECKING, Optional

from twitchio.errors import Unauthorized
from twitchio.ext import eventsub

if TYPE_CHECKING:
    from src.bot.twitch_bot import TwitchBot

logger = logging.getLogger(__name__)


class EventSubManager:
    """
    Manager for Twitch EventSub WebSocket subscriptions.

    Handles the lifecycle of EventSub subscriptions for channel point redemptions
    and monitors the underlying WebSocket connection health.
    """

    def __init__(self, bot: "TwitchBot") -> None:
        """
        Initialize the EventSub manager.

        Args:
            bot: The parent TwitchBot instance. Used for API calls and token management.
        """
        self.bot: "TwitchBot" = bot
        self.client: Optional[eventsub.EventSubWSClient] = None
        self.broadcaster_id: Optional[str] = None
        self.subscribed: bool = False
        self._reconnect_lock: asyncio.Lock = asyncio.Lock()

    async def setup(self) -> None:
        """
        Perform initial setup for EventSub.

        Fetches the broadcaster ID and attempts to create the initial subscription.
        This method should be called once when the bot starts.
        """
        if not self.bot.token_manager.has_streamer_token():
            logger.info("No streamer token available; EventSub is disabled.")
            return

        try:
            channel_list: list[str] = self.bot.config.get("channels") or []
            if not channel_list:
                logger.warning("No channels configured; EventSub setup skipped.")
                return

            streamer_name: str = channel_list[0]
            users = await self.bot.fetch_users(names=[streamer_name])
            if not users:
                logger.error("Streamer not found: %s", streamer_name)
                return

            self.broadcaster_id = users[0].id
            await self._subscribe_once()

        except Exception as exc:
            logger.error("EventSub setup failed: %s", exc, exc_info=True)

    async def ensure_alive(self) -> None:
        """
        Check the health of the EventSub WebSocket connection and recover if needed.

        This method is intended to be called periodically. It checks if the internal
        WebSocket sockets are present and connected. If not, it performs a full
        cleanup and recreates the subscription.
        """
        if not self.subscribed or not self.client:
            logger.warning("EventSub is not subscribed; attempting to subscribe.")
            await self._subscribe_once()
            return

        sockets = getattr(self.client, "_sockets", [])
        if not sockets:
            logger.warning("No active EventSub sockets detected; recreating subscription.")
            await self._cleanup()
            await self._subscribe_once()
            return

        if not any(getattr(socket, "is_connected", False) for socket in sockets):
            logger.warning("All EventSub sockets are disconnected; recreating subscription.")
            await self._cleanup()
            await self._subscribe_once()

    async def close(self) -> None:
        """
        Shut down the EventSub manager and clean up all resources.

        This should be called when the bot is shut down to ensure
        proper cleanup of the internal EventSub client state.
        """
        await self._cleanup()
        logger.info("EventSub manager closed.")

    async def _subscribe_once(self) -> None:
        """
        Internal method to create a single EventSub subscription.

        Uses a lock to prevent concurrent subscription attempts. If a valid
        subscription already exists, this method returns early.
        """
        async with self._reconnect_lock:
            if self.subscribed and self.client:
                logger.debug("EventSub is already subscribed.")
                return

            token = await self.bot.token_manager.get_streamer_token()
            if not token or not self.broadcaster_id:
                logger.warning("Unable to subscribe to EventSub due to missing credentials.")
                return

            try:
                self.client = eventsub.EventSubWSClient(self.bot)
                await self.client.subscribe_channel_points_redeemed(
                    self.broadcaster_id,
                    token,
                )
                self.subscribed = True
                logger.info("EventSub subscription successfully registered.")
                # Note: The WebSocket connection is managed internally by TwitchIO
                # and will be established automatically.

            except Unauthorized:
                logger.warning(
                    "EventSub subscription failed: broadcaster is not an Affiliate or Partner, "
                    "or the token is invalid."
                )
                await self._cleanup()

            except Exception as exc:
                logger.warning("Failed to register EventSub subscription: %s", exc)
                await self._cleanup()

    async def _cleanup(self) -> None:
        """
        Internal method to reset the manager's state.

        Clears references to the current client and subscription status.
        The brief sleep allows any pending asynchronous operations to settle
        before a potential re-subscription.
        """
        self.client = None
        self.subscribed = False
        await asyncio.sleep(0.5)
        logger.debug("EventSub internal state has been cleared.")
