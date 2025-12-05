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


async def beer_barrel_handler(event: Any, bot: Any) -> None:
    """
    Handle 'вскрыть пивную кегу' channel point reward redemption.

    Args:
        event: EventSub reward event object.
        bot: TwitchBot instance.
    """
    user_name = event.data.user.name
    channel_name = event.data.broadcaster.name.lower()
    logger.info(f"Reward 'вскрыть пивную кегу' redeemed by {user_name}")

    await bot.command_handler.handle_beer_barrel(user_name, channel_name)


async def beer_challenge_handler(event: Any, bot: Any) -> None:
    """
    Handle 'испытание пивом' channel point reward redemption.

    Args:
        event: EventSub reward event object.
        bot: TwitchBot instance.
    """
    user_name = event.data.user.name
    channel_name = event.data.broadcaster.name.lower()
    user_input = event.data.input
    logger.info(f"Reward 'испытание пивом' redeemed by {user_name}")

    await bot.command_handler.handle_beer_challenge(user_name, user_input, channel_name)


reward_handlers: dict[str, Any] = {
    "очко": twenty_one_handler,
    "вскрыть пивную кегу": beer_barrel_handler,
    "испытание пивом": beer_challenge_handler,
}
