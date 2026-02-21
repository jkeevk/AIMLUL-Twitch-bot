"""
Central configuration for Twitch bot commands.

This file contains a single dictionary, `COMMANDS`, that maps
internal command identifiers to their actual chat trigger strings.

Usage:
    from src.bot.commands_config import COMMANDS

    # Access command name
    print(COMMANDS["bot_sleep"]) # e.g., "ботзаткнись"

    # Use in a decorator
    @commands.command(name=COMMANDS["bot_sleep"])
    async def bot_sleep(ctx):
        ...
"""

COMMANDS = {
    # Admin commands
    "bot_sleep": "ботзаткнись",
    "bot_wake": "ботговори",
    # Game commands
    "butt": "жопа",
    "club": "дрын",
    "me": "я",
    "leaders": "топ",
    "voteban": "voteban",
    "twenty_one": "очко",
}
