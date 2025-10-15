import configparser
import os
from typing import Dict, Any


def load_settings(config_path: str = "settings.ini") -> Dict[str, Any]:
    """Загружает настройки бота из INI-файла"""
    config = configparser.ConfigParser()

    # Создаем конфиг по умолчанию, если файл не существует
    if not os.path.exists(config_path):
        config["SETTINGS"] = {
            "command_delay_time": "30",
            "refresh_token_delay_time": "14400",
        }
        config["INITIAL_CHANNELS"] = {"channels": ""}
        config["DATABASE"] = {
            "dsn": "postgresql+asyncpg://bot:botpassword@db/twitch_bot"
        }
        config["ADMINS"] = {"admins": ""}
        config["ADMINS"] = {"privileged": ""}
        with open(config_path, "w") as configfile:
            config.write(configfile)

    config.read(config_path)

    settings = {
        "command_delay_time": int(
            config.get("SETTINGS", "command_delay_time", fallback=30)
        ),
        "refresh_token_delay_time": int(
            config.get("SETTINGS", "refresh_token_delay_time", fallback=14400)
        ),
        "channels": [
            channel.strip()
            for channel in config.get(
                "INITIAL_CHANNELS", "channels", fallback=""
            ).split(",")
            if channel.strip()
        ],
        "database": {"dsn": config.get("DATABASE", "dsn", fallback=None)},
        "admins": [
            admin.strip().lower()
            for admin in config.get("ADMINS", "admins", fallback="").split(",")
            if admin.strip()
        ],
        "privileged": {
            privileged.strip().lower()
            for privileged in config.get("ADMINS", "privileged", fallback="").split(",")
            if privileged.strip()
        },
    }

    return settings
