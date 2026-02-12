from typing import Any

GNOME_KEYWORDS: list[str] = [
    "gnome",
    "aimlulgnom",
    "gnomerge",
]

APPLECAT_KEYWORDS: list[str] = [
    "applecatpanik",
    "applecatgun",
    "applecatrun",
]


def build_triggers(bot: Any) -> dict[str, Any]:
    """
    Build a dictionary of text triggers for the bot.

    Each trigger maps keywords to a handler function that processes
    the corresponding messages.

    Args:
        bot: The main bot instance with a command_handler.

    Returns:
        A dictionary containing:
            - "gnome_keywords": List of keywords for gnome triggers.
            - "apple_keywords": List of keywords for applecat triggers.
            - "handlers": Mapping of trigger names to their handler functions.
    """
    return {
        "gnome_keywords": GNOME_KEYWORDS,
        "apple_keywords": APPLECAT_KEYWORDS,
        "handlers": {
            "gnome": lambda message: bot.command_handler.handle_gnome(message),
            "apple": lambda message: bot.command_handler.handle_applecat(message),
        },
    }
