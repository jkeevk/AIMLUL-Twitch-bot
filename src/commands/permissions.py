from typing import Any

from twitchio import Chatter

from src.commands.models.chatters import ChatterData
from src.core.config_loader import load_settings

PRIVILEGED_USERS = load_settings()["privileged"]


def is_privileged(chatter: Chatter | ChatterData | str) -> bool:
    """
    Check if user has privileged status (moderator, broadcaster, or configured privileged user).

    Works for both twitchio Chatter objects and ChatterData dataclasses.

    Args:
        chatter: Twitch Chatter object or ChatterData dataclass

    Returns:
        True if the user has privileged status, False otherwise
    """
    if isinstance(chatter, Chatter):
        return chatter.is_mod or chatter.is_broadcaster or chatter.name.lower() in (u.lower() for u in PRIVILEGED_USERS)
    elif isinstance(chatter, ChatterData):
        return chatter.name.lower() in (u.lower() for u in PRIVILEGED_USERS)
    elif isinstance(chatter, str):
        return chatter.lower() in (u.lower() for u in PRIVILEGED_USERS)
    return False


def is_admin(bot: Any, username: str) -> bool:
    """
    Check if a user is configured as an admin.

    Args:
        bot: TwitchBot instance.
        username: Twitch username to check.

    Returns:
        True if the user is an admin, False otherwise.
    """
    return username.lower() in bot.config.get("admins", [])
