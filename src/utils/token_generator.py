import configparser
import os
import sys
import threading
import urllib.parse as urlparse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.ini")


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        # Парсим параметры из URL
        query = urlparse.urlparse(self.path).query
        params = urlparse.parse_qs(query)

        if "code" in params:
            code = params["code"][0]
            self.server.auth_code = code
            self.wfile.write(
                b"""
                <html>
                <head><title>Twitch Auth Success</title></head>
                <body style="background-color: #9146FF; color: white; text-align: center; padding: 50px;">
                    <h1>Success!</h1>
                    <p>Authorization code received. You can close this window.</p>
                    <p>The token will be saved automatically.</p>
                </body>
                </html>
            """
            )
        elif "error" in params:
            error = params["error"][0]
            self.wfile.write(f"<h1>Error:</h1><p>{error}</p>".encode())

        threading.Thread(target=self.server.shutdown, daemon=True).start()


def save_tokens(access_token, refresh_token, client_id, client_secret):
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_section("TOKEN"):
        config.add_section("TOKEN")

    config.set("TOKEN", "token", access_token)
    config.set("TOKEN", "refresh_token", refresh_token)
    config.set("TOKEN", "client_id", client_id)
    config.set("TOKEN", "client_secret", client_secret)

    with open(CONFIG_PATH, "w") as configfile:
        config.write(configfile)

    print(f"✅ Токены сохранены в {CONFIG_PATH}")


def get_oauth_token():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_option("TOKEN", "client_id") or not config.has_option(
        "TOKEN", "client_secret"
    ):
        print("❌ Ошибка: client_id и client_secret должны быть указаны в settings.ini")
        return None

    client_id = config.get("TOKEN", "client_id")
    client_secret = config.get("TOKEN", "client_secret")
    scope = config.get("TOKEN", "scope")
    redirect_uri = "http://localhost:3000"

    server = HTTPServer(("localhost", 3000), CallbackHandler)
    server.auth_code = None

    auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&scope={scope}"
        "&force_verify=true"
    )

    print("Открываю браузер для авторизации...")
    webbrowser.open(auth_url)

    print("Ожидаю callback на http://localhost:3000...")
    print("После авторизации в Twitch, токен будет сохранен автоматически")
    server.serve_forever()

    if not server.auth_code:
        print("❌ Не удалось получить код авторизации")
        return None

    print(f"\n✅ Получен код авторизации")

    token_url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": server.auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    print("\n🔄 Обмениваю код на токен...")
    response = requests.post(token_url, data=data)

    if response.status_code == 200:
        token_data = response.json()
        print("\n✅ Успешно получен токен!")

        save_tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            client_id=client_id,
            client_secret=client_secret,
        )

        return token_data
    else:
        print(f"\n❌ Ошибка при получении токена: {response.status_code}")
        print(response.text)
        return None


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(" Twitch Token Generator".center(50))
    print("=" * 50 + "\n")

    if not os.path.exists(CONFIG_PATH):
        print(f"⚠️ Файл настроек не найден: {CONFIG_PATH}")
        print("Создаю базовый файл настроек...")

        config = configparser.ConfigParser()
        config["TOKEN"] = {
            "token": "",
            "client_id": "",
            "client_secret": "",
            "refresh_token": "",
        }
        config["INITIAL_CHANNELS"] = {"channels": ""}
        config["SETTINGS"] = {"command_delay_time": "30"}
        config["SETTINGS"] = {"refresh_token_delay_time": "14400"}

        with open(CONFIG_PATH, "w") as configfile:
            config.write(configfile)

        print(f"✅ Файл настроек создан: {CONFIG_PATH}")
        print(
            "Пожалуйста, добавьте client_id и client_secret из Twitch Developer Console"
        )
        print("Затем запустите скрипт снова")
        sys.exit(0)

    token_data = get_oauth_token()

    if token_data:
        print("\n🎉 Готово! Теперь вы можете запустить бота с новыми токенами")
    else:
        print("\n❌ Не удалось получить токен. Проверьте настройки и попробуйте снова")
