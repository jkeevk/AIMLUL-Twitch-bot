import configparser
import pathlib
from datetime import time as dtime
from typing import Any


def load_settings(config_path: str | None = None) -> dict[str, Any]:
    """
    Load bot configuration settings from the INI file.

    Creates a default configuration file if it doesn't exist and returns
    parsed settings with appropriate data types.

    Args:
        config_path: Path to the configuration file (None for auto-detection)

    Returns:
        Dictionary containing all bot settings with proper typing
    """
    config = configparser.ConfigParser()

    final_config_path: str

    if config_path is None:
        possible_paths = [
            "settings.ini",
            "/app/settings.ini",
            str(pathlib.Path(__file__).parent.parent.parent / "settings.ini"),
        ]

        for path in possible_paths:
            if pathlib.Path(path).exists():
                final_config_path = path
                break
        else:
            final_config_path = "settings.ini"
    else:
        final_config_path = config_path

    config_path_obj = pathlib.Path(final_config_path)

    if not config_path_obj.exists():
        config["SETTINGS"] = {
            "command_delay_time": "45",
            "refresh_token_delay_time": "7200",
        }
        config["INITIAL_CHANNELS"] = {"channels": ""}
        config["DATABASE"] = {"dsn": "postgresql+asyncpg://bot:botpassword@db/twitch_bot"}
        config["ADMINS"] = {"admins": "", "privileged": ""}

        config_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with config_path_obj.open("w") as configfile:
            config.write(configfile)

    config.read(final_config_path)
    schedule_enabled = config.getboolean("SCHEDULE", "enabled", fallback=False)

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
        "schedule": {
            "enabled": schedule_enabled,
            "timezone": config.get("SCHEDULE", "timezone", fallback="Europe/Moscow"),
            "offline_from": _parse_time(config.get("SCHEDULE", "offline_from", fallback=None)),
            "offline_to": _parse_time(config.get("SCHEDULE", "offline_to", fallback=None)),
        },
    }

    return settings


def _parse_time(value: str | None) -> dtime | None:
    """
    Convert a string in "HH:MM" format to a datetime.time object.

    Args:
        value: A string representing the time in "HH:MM" format, or None.

    Returns:
        A datetime.time object if the input string is valid, otherwise None.
    """
    if not value:
        return None
    hour, minute = map(int, value.split(":"))
    return dtime(hour, minute)
