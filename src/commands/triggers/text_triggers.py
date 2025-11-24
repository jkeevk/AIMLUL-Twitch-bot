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
    """Create a dictionary of text triggers for the bot."""
    return {
        "gnome_keywords": GNOME_KEYWORDS,
        "apple_keywords": APPLECAT_KEYWORDS,
        "handlers": {
            "gnome": lambda message: bot.command_handler.handle_gnome(message),
            "apple": lambda message: bot.command_handler.handle_applecat(message),
        },
    }
