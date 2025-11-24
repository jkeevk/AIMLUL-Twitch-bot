import logging
from typing import Any

from src.eventsub.reward_handlers import reward_handlers

logger = logging.getLogger(__name__)


async def handle_eventsub_reward(event: Any, bot: Any) -> None:
    """
    Dispatch EventSub reward to the appropriate handler.

    Args:
        event: EventSub reward event object.
        bot: TwitchBot instance.
    """
    try:
        reward_name = event.data.reward.title.lower()
        handler = reward_handlers.get(reward_name)
        if handler:
            await handler(event, bot)
        else:
            logger.info(f"Ignored reward: {reward_name}")
    except Exception as e:
        logger.error(f"EventSub processing error: {e}", exc_info=True)
