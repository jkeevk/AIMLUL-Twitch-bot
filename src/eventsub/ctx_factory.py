import logging
from typing import Any

logger = logging.getLogger("CtxFactory")


async def create_fake_context(bot: Any, username: str, channel_name: str, user_id: str) -> Any:
    """
    Create a fake Context object simulating a Chatter for EventSub rewards.

    Args:
        bot: TwitchBot instance.
        username: Name of the user who redeemed the reward.
        channel_name: Name of the channel where reward was redeemed.
        user_id: Twitch user ID of the redeemer.

    Returns:
        Context-like object with `author`, `send`, and `channel` attributes.
    """
    channel = bot.get_channel(channel_name)
    if not channel:
        channel = await bot.fetch_channel(channel_name)

    is_broadcaster = username.lower() == channel_name.lower()

    chatter_like = type(
        "ChatterLike",
        (),
        {
            "name": username,
            "display_name": username,
            "id": user_id,
            "is_mod": False,
            "is_vip": False,
            "is_broadcaster": is_broadcaster,
            "is_subscriber": False,
            "is_turbo": False,
            "badges": [],
            "color": "",
            "channel": channel_name,
        },
    )()

    ctx = type(
        "Context",
        (),
        {"channel": channel, "author": chatter_like, "send": channel.send},
    )()

    return ctx
