from typing import Any

from twitchio import Chatter

from src.core.config_loader import load_settings

PRIVILEGED_USERS = load_settings()["privileged"]


def is_privileged(chatter: Chatter) -> bool:
    """
    Check if user has privileged status (moderator, broadcaster, or configured privileged user).

    Args:
        chatter: Twitch chatter object to check

    Returns:
        True if user has privileged status, False otherwise
    """
    return chatter.is_mod or chatter.is_broadcaster or chatter.name in PRIVILEGED_USERS


def is_admin(bot: Any, username: str) -> bool:
    """
    Check if a user is configured as an admin.

    Args:
        bot: TwitchBot instance.
        username: Twitch username to check.

    Returns:
        True if user is an admin, False otherwise.
    """
    return username.lower() in bot.config.get("admins", [])
