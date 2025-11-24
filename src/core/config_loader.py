import configparser
import pathlib
from typing import Any


def load_settings(config_path: str = "settings.ini") -> dict[str, Any]:
    """
    Load bot configuration settings from INI file.

    Creates default configuration file if it doesn't exist and returns
    parsed settings with appropriate data types.

    Args:
        config_path: Path to the configuration file

    Returns:
        Dictionary containing all bot settings with proper typing
    """
    config = configparser.ConfigParser()

    if not pathlib.Path(config_path).exists():
        config["SETTINGS"] = {
            "command_delay_time": "45",
            "refresh_token_delay_time": "7200",
        }
        config["INITIAL_CHANNELS"] = {"channels": ""}
        config["DATABASE"] = {"dsn": "postgresql+asyncpg://bot:botpassword@db/twitch_bot"}
        config["ADMINS"] = {"admins": "", "privileged": ""}
        with pathlib.Path(config_path).open("w") as configfile:
            config.write(configfile)

    config.read(config_path)

    settings = {
        "command_delay_time": int(config.get("SETTINGS", "command_delay_time", fallback=45)),
        "refresh_token_delay_time": int(config.get("SETTINGS", "refresh_token_delay_time", fallback=7200)),
        "channels": [
            channel.strip()
            for channel in config.get("INITIAL_CHANNELS", "channels", fallback="").split(",")
            if channel.strip()
        ],
        "database": {"dsn": config.get("DATABASE", "dsn", fallback=None)},
        "admins": [
            admin.strip().lower() for admin in config.get("ADMINS", "admins", fallback="").split(",") if admin.strip()
        ],
        "privileged": [
            user.strip().lower() for user in config.get("ADMINS", "privileged", fallback="").split(",") if user.strip()
        ],
    }

    return settings
