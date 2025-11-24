import logging
from typing import Any

from src.eventsub.ctx_factory import create_fake_context

logger = logging.getLogger(__name__)


async def twenty_one_handler(event: Any, bot: Any) -> None:
    """
    Handle 'очко' channel point reward redemption.

    Args:
        event: EventSub reward event object.
        bot: TwitchBot instance.
    """
    user_name = event.data.user.name
    channel_name = event.data.broadcaster.name.lower()
    logger.info(f"Reward 'очко' redeemed by {user_name}")

    ctx = await create_fake_context(bot, username=user_name, channel_name=channel_name, user_id=event.data.user.id)
    if bot.active:
        await bot.command_handler.handle_twenty_one(ctx)


reward_handlers: dict[str, Any] = {
    "очко": twenty_one_handler,
}
