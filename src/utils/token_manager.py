import configparser
import os
import requests
import logging
from typing import Optional, Dict, Any

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TokenManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self._token = self.config.get("TOKEN", "token", fallback=None)
        self.client_id = self.config.get("TOKEN", "client_id")
        self.client_secret = self.config.get("TOKEN", "client_secret")
        self.refresh_token = self.config.get("TOKEN", "refresh_token")
        self.scope = self.config.get("TOKEN", "scope", fallback="")

    @property
    def token(self) -> Optional[str]:
        return self._token

    def _save_config(self):
        """Сохраняет текущую конфигурацию в файл."""
        with open(self.config_path, "w") as configfile:
            self.config.write(configfile)

    async def validate_token(self, token: str) -> bool:
        """Проверяет валидность токена."""
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {token}"}

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ Токен валиден. Scopes: {data.get('scopes', [])}")
            return True
        except requests.RequestException as e:
            logger.error(f"🚨 Ошибка при валидации токена: {e}")
            return False

    async def refresh_access_token(self) -> str:
        """Обновляет access token с помощью refresh token и возвращает его."""
        logger.info("🔄 Начинаю обновление токена...")
        logger.info(
            f"ℹ️ Использую refresh_token: {self.refresh_token[:5]}...{self.refresh_token[-5:]}"
        )
        logger.info(f"ℹ️ client_id: {self.client_id}")

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        logger.info("🌐 Отправляю запрос на обновление токена...")
        response = requests.post(url, params=params)
        if response.status_code == 200:
            data = response.json()
            new_token = data["access_token"]
            new_refresh_token = data.get("refresh_token", self.refresh_token)

            self.config.set("TOKEN", "token", new_token)
            self.config.set("TOKEN", "refresh_token", new_refresh_token)
            self._token = new_token
            self.refresh_token = new_refresh_token

            self._save_config()

            logger.info("🔔 Получен ответ: 200")
            logger.info("✅ Токен успешно обновлен!")
            logger.info(f"💾 Конфигурация сохранена")
            logger.info(f"🔑 Новый access_token: {new_token[:5]}...{new_token[-5:]}")
            logger.info(
                f"🔐 Новый refresh_token: {new_refresh_token[:5]}...{new_refresh_token[-5:]}"
            )

            # Валидация нового токена
            if not await self.validate_token(new_token):
                logger.error("❌ Не удалось верифицировать новый токен")
                raise RuntimeError("Token validation failed after refresh")

            return new_token
        else:
            logger.error(f"🚨 Ошибка при обновлении токена: {response.status_code}")
            logger.error(f"🚨 Ответ: {response.text}")
            raise Exception(f"Ошибка обновления токена: {response.status_code}")

    async def get_access_token(self) -> str:
        """Возвращает текущий токен. Если токен не установлен, вызывает обновление."""
        if not self.token:
            return await self.refresh_access_token()
        return self.token
